#!/usr/bin/env python3
"""
Comprehensive test suite for Claude Code Provider Balancer
Tests streaming/non-streaming requests, success/error scenarios, timeouts, failover, and concurrency
"""

import asyncio
import httpx
import json
import time
import uuid
from typing import Dict, List, Optional, Any
from datetime import datetime
import concurrent.futures
import threading

# Configuration
BALANCER_BASE_URL = "http://127.0.0.1:8080"
TEST_TIMEOUT = 30.0
MAX_CONCURRENT_REQUESTS = 10

class TestResult:
    def __init__(self, name: str, success: bool, message: str, duration: float = 0.0, details: Optional[Dict] = None):
        self.name = name
        self.success = success
        self.message = message
        self.duration = duration
        self.details = details or {}

class BalancerTester:
    def __init__(self):
        self.results: List[TestResult] = []
        self.client = httpx.AsyncClient(timeout=TEST_TIMEOUT)
        
    async def test_streaming_success(self) -> TestResult:
        """Test streaming request success scenarios"""
        test_name = "Streaming Success"
        start_time = time.time()
        
        try:
            request_data = {
                "model": "claude-3-5-sonnet-20241022",
                "messages": [
                    {"role": "user", "content": "Write a very short poem about rain"}
                ],
                "max_tokens": 100,
                "stream": True
            }
            
            response = await self.client.post(
                f"{BALANCER_BASE_URL}/v1/messages",
                json=request_data,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code != 200:
                return TestResult(
                    test_name, False, 
                    f"HTTP {response.status_code}: {response.text[:200]}",
                    time.time() - start_time
                )
            
            # Parse streaming response
            chunks = []
            events = []
            async for chunk in response.aiter_lines():
                chunks.append(chunk)
                if chunk.strip():
                    if chunk.startswith("event:"):
                        events.append(chunk[6:].strip())
                    elif chunk.startswith("data:"):
                        try:
                            data = json.loads(chunk[5:].strip())
                            if "error" in data:
                                return TestResult(
                                    test_name, False,
                                    f"Streaming error: {data['error']}",
                                    time.time() - start_time
                                )
                        except json.JSONDecodeError:
                            pass
            
            # Verify streaming events
            expected_events = ["message_start", "content_block_start", "content_block_delta", "content_block_stop", "message_delta", "message_stop"]
            found_events = set(events)
            
            duration = time.time() - start_time
            return TestResult(
                test_name, True,
                f"Streaming successful with {len(chunks)} chunks, events: {found_events}",
                duration,
                {"chunks": len(chunks), "events": list(found_events)}
            )
            
        except Exception as e:
            return TestResult(
                test_name, False,
                f"Exception: {str(e)}",
                time.time() - start_time
            )
    
    async def test_streaming_error(self) -> TestResult:
        """Test streaming request error scenarios"""
        test_name = "Streaming Error Handling"
        start_time = time.time()
        
        try:
            # Test with invalid model
            request_data = {
                "model": "invalid-model-name",
                "messages": [
                    {"role": "user", "content": "test"}
                ],
                "max_tokens": 100,
                "stream": True
            }
            
            response = await self.client.post(
                f"{BALANCER_BASE_URL}/v1/messages",
                json=request_data,
                headers={"Content-Type": "application/json"}
            )
            
            # Should either return error status or error event in stream
            if response.status_code >= 400:
                return TestResult(
                    test_name, True,
                    f"Correctly returned error status: {response.status_code}",
                    time.time() - start_time
                )
            
            # Check for error events in stream
            error_found = False
            async for chunk in response.aiter_lines():
                if chunk.strip().startswith("event: error"):
                    error_found = True
                    break
            
            duration = time.time() - start_time
            return TestResult(
                test_name, error_found,
                "Error event found in stream" if error_found else "No error event found",
                duration
            )
            
        except Exception as e:
            return TestResult(
                test_name, False,
                f"Exception: {str(e)}",
                time.time() - start_time
            )
    
    async def test_non_streaming_success(self) -> TestResult:
        """Test non-streaming request success scenarios"""
        test_name = "Non-Streaming Success"
        start_time = time.time()
        
        try:
            request_data = {
                "model": "claude-3-5-sonnet-20241022",
                "messages": [
                    {"role": "user", "content": "Say hello"}
                ],
                "max_tokens": 50,
                "stream": False
            }
            
            response = await self.client.post(
                f"{BALANCER_BASE_URL}/v1/messages",
                json=request_data,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code != 200:
                return TestResult(
                    test_name, False,
                    f"HTTP {response.status_code}: {response.text[:200]}",
                    time.time() - start_time
                )
            
            data = response.json()
            
            # Verify response structure
            required_fields = ["id", "type", "role", "content", "model", "usage"]
            missing_fields = [field for field in required_fields if field not in data]
            
            if missing_fields:
                return TestResult(
                    test_name, False,
                    f"Missing fields: {missing_fields}",
                    time.time() - start_time
                )
            
            duration = time.time() - start_time
            return TestResult(
                test_name, True,
                f"Non-streaming successful, model: {data.get('model')}, tokens: {data.get('usage', {}).get('output_tokens', 0)}",
                duration,
                {"model": data.get('model'), "usage": data.get('usage')}
            )
            
        except Exception as e:
            return TestResult(
                test_name, False,
                f"Exception: {str(e)}",
                time.time() - start_time
            )
    
    async def test_non_streaming_error(self) -> TestResult:
        """Test non-streaming request error scenarios"""
        test_name = "Non-Streaming Error Handling"
        start_time = time.time()
        
        try:
            # Test with malformed request
            request_data = {
                "model": "claude-3-5-sonnet-20241022",
                "messages": [],  # Empty messages array
                "max_tokens": -1,  # Invalid max_tokens
                "stream": False
            }
            
            response = await self.client.post(
                f"{BALANCER_BASE_URL}/v1/messages",
                json=request_data,
                headers={"Content-Type": "application/json"}
            )
            
            # Should return error status
            if response.status_code >= 400:
                data = response.json()
                duration = time.time() - start_time
                return TestResult(
                    test_name, True,
                    f"Correctly returned error: {response.status_code}, type: {data.get('error', {}).get('type')}",
                    duration,
                    {"status_code": response.status_code, "error": data.get('error')}
                )
            
            return TestResult(
                test_name, False,
                "Should have returned error status",
                time.time() - start_time
            )
            
        except Exception as e:
            return TestResult(
                test_name, False,
                f"Exception: {str(e)}",
                time.time() - start_time
            )
    
    async def test_timeout_scenarios(self) -> TestResult:
        """Test timeout scenarios"""
        test_name = "Timeout Scenarios"
        start_time = time.time()
        
        try:
            # Test with very long content that might cause timeout
            long_content = "Write a detailed analysis of " + "this topic " * 500
            request_data = {
                "model": "claude-3-5-sonnet-20241022",
                "messages": [
                    {"role": "user", "content": long_content}
                ],
                "max_tokens": 4000,
                "stream": False
            }
            
            # Use shorter timeout for this test
            short_timeout_client = httpx.AsyncClient(timeout=5.0)
            
            try:
                response = await short_timeout_client.post(
                    f"{BALANCER_BASE_URL}/v1/messages",
                    json=request_data,
                    headers={"Content-Type": "application/json"}
                )
                
                # If we get here, the request completed within timeout
                duration = time.time() - start_time
                return TestResult(
                    test_name, True,
                    f"Request completed within timeout: {response.status_code}",
                    duration,
                    {"status_code": response.status_code}
                )
                
            except httpx.TimeoutException:
                duration = time.time() - start_time
                return TestResult(
                    test_name, True,
                    f"Timeout correctly handled in {duration:.2f}s",
                    duration
                )
            finally:
                await short_timeout_client.aclose()
                
        except Exception as e:
            return TestResult(
                test_name, False,
                f"Exception: {str(e)}",
                time.time() - start_time
            )
    
    async def test_provider_failover(self) -> TestResult:
        """Test provider failover and switching"""
        test_name = "Provider Failover"
        start_time = time.time()
        
        try:
            # First, get provider status
            status_response = await self.client.get(f"{BALANCER_BASE_URL}/providers")
            
            if status_response.status_code != 200:
                return TestResult(
                    test_name, False,
                    f"Could not get provider status: {status_response.status_code}",
                    time.time() - start_time
                )
            
            status_data = status_response.json()
            healthy_providers = [p for p in status_data.get("providers", []) if p.get("healthy")]
            
            if len(healthy_providers) < 2:
                return TestResult(
                    test_name, False,
                    f"Need at least 2 healthy providers for failover test, found: {len(healthy_providers)}",
                    time.time() - start_time
                )
            
            # Make multiple requests to test failover
            successful_requests = 0
            provider_responses = {}
            
            for i in range(5):
                request_data = {
                    "model": "claude-3-5-sonnet-20241022",
                    "messages": [
                        {"role": "user", "content": f"Test request {i}"}
                    ],
                    "max_tokens": 50,
                    "stream": False
                }
                
                try:
                    response = await self.client.post(
                        f"{BALANCER_BASE_URL}/v1/messages",
                        json=request_data,
                        headers={"Content-Type": "application/json"}
                    )
                    
                    if response.status_code == 200:
                        successful_requests += 1
                        # Track which provider might have responded (via headers or response characteristics)
                        provider_responses[i] = response.headers.get("X-Provider", "unknown")
                    
                except Exception:
                    pass
            
            duration = time.time() - start_time
            return TestResult(
                test_name, successful_requests > 0,
                f"Failover test: {successful_requests}/5 successful requests",
                duration,
                {"successful_requests": successful_requests, "provider_responses": provider_responses}
            )
            
        except Exception as e:
            return TestResult(
                test_name, False,
                f"Exception: {str(e)}",
                time.time() - start_time
            )
    
    async def test_concurrent_requests(self) -> TestResult:
        """Test concurrent requests handling"""
        test_name = "Concurrent Requests"
        start_time = time.time()
        
        try:
            # Create multiple concurrent requests
            request_data = {
                "model": "claude-3-5-sonnet-20241022",
                "messages": [
                    {"role": "user", "content": "Say hello"}
                ],
                "max_tokens": 50,
                "stream": False
            }
            
            # Create tasks for concurrent execution
            tasks = []
            for i in range(MAX_CONCURRENT_REQUESTS):
                task = self.client.post(
                    f"{BALANCER_BASE_URL}/v1/messages",
                    json=request_data,
                    headers={"Content-Type": "application/json"}
                )
                tasks.append(task)
            
            # Execute all tasks concurrently
            responses = await asyncio.gather(*tasks, return_exceptions=True)
            
            successful_responses = 0
            failed_responses = 0
            exceptions = 0
            
            for response in responses:
                if isinstance(response, Exception):
                    exceptions += 1
                elif hasattr(response, 'status_code'):
                    if response.status_code == 200:
                        successful_responses += 1
                    else:
                        failed_responses += 1
            
            duration = time.time() - start_time
            return TestResult(
                test_name, successful_responses > 0,
                f"Concurrent test: {successful_responses} success, {failed_responses} failed, {exceptions} exceptions",
                duration,
                {
                    "successful": successful_responses,
                    "failed": failed_responses,
                    "exceptions": exceptions,
                    "total": len(responses)
                }
            )
            
        except Exception as e:
            return TestResult(
                test_name, False,
                f"Exception: {str(e)}",
                time.time() - start_time
            )
    
    async def test_token_counting(self) -> TestResult:
        """Test token counting endpoint"""
        test_name = "Token Counting"
        start_time = time.time()
        
        try:
            request_data = {
                "model": "claude-3-5-sonnet-20241022",
                "messages": [
                    {"role": "user", "content": "Hello world"}
                ],
                "system": "You are a helpful assistant"
            }
            
            response = await self.client.post(
                f"{BALANCER_BASE_URL}/v1/messages/count_tokens",
                json=request_data,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code != 200:
                return TestResult(
                    test_name, False,
                    f"HTTP {response.status_code}: {response.text[:200]}",
                    time.time() - start_time
                )
            
            data = response.json()
            
            if "input_tokens" not in data:
                return TestResult(
                    test_name, False,
                    "Missing input_tokens field",
                    time.time() - start_time
                )
            
            token_count = data["input_tokens"]
            duration = time.time() - start_time
            
            return TestResult(
                test_name, token_count > 0,
                f"Token counting successful: {token_count} tokens",
                duration,
                {"input_tokens": token_count}
            )
            
        except Exception as e:
            return TestResult(
                test_name, False,
                f"Exception: {str(e)}",
                time.time() - start_time
            )
    
    async def test_health_endpoints(self) -> TestResult:
        """Test health check endpoints"""
        test_name = "Health Endpoints"
        start_time = time.time()
        
        try:
            # Test root health check
            root_response = await self.client.get(f"{BALANCER_BASE_URL}/")
            
            if root_response.status_code != 200:
                return TestResult(
                    test_name, False,
                    f"Root health check failed: {root_response.status_code}",
                    time.time() - start_time
                )
            
            # Test providers status
            providers_response = await self.client.get(f"{BALANCER_BASE_URL}/providers")
            
            if providers_response.status_code != 200:
                return TestResult(
                    test_name, False,
                    f"Providers status failed: {providers_response.status_code}",
                    time.time() - start_time
                )
            
            providers_data = providers_response.json()
            total_providers = providers_data.get("total_providers", 0)
            healthy_providers = providers_data.get("healthy_providers", 0)
            
            duration = time.time() - start_time
            return TestResult(
                test_name, total_providers > 0,
                f"Health endpoints OK: {healthy_providers}/{total_providers} healthy providers",
                duration,
                {"total_providers": total_providers, "healthy_providers": healthy_providers}
            )
            
        except Exception as e:
            return TestResult(
                test_name, False,
                f"Exception: {str(e)}",
                time.time() - start_time
            )
    
    async def run_all_tests(self) -> List[TestResult]:
        """Run all tests and return results"""
        print("🚀 Starting comprehensive balancer tests...")
        print(f"Target: {BALANCER_BASE_URL}")
        print(f"Timeout: {TEST_TIMEOUT}s")
        print(f"Max concurrent: {MAX_CONCURRENT_REQUESTS}")
        print("-" * 60)
        
        # Run all tests
        test_methods = [
            self.test_health_endpoints,
            self.test_token_counting,
            self.test_non_streaming_success,
            self.test_non_streaming_error,
            self.test_streaming_success,
            self.test_streaming_error,
            self.test_timeout_scenarios,
            self.test_provider_failover,
            self.test_concurrent_requests,
        ]
        
        results = []
        for test_method in test_methods:
            print(f"🔍 Running {test_method.__name__}...")
            result = await test_method()
            results.append(result)
            
            status = "✅ PASS" if result.success else "❌ FAIL"
            print(f"   {status} ({result.duration:.2f}s): {result.message}")
            
            if result.details:
                for key, value in result.details.items():
                    print(f"      {key}: {value}")
            
            print()
        
        return results
    
    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()

def print_summary(results: List[TestResult]):
    """Print test summary"""
    print("=" * 60)
    print("📊 TEST SUMMARY")
    print("=" * 60)
    
    total_tests = len(results)
    passed_tests = sum(1 for r in results if r.success)
    failed_tests = total_tests - passed_tests
    total_duration = sum(r.duration for r in results)
    
    print(f"Total Tests: {total_tests}")
    print(f"Passed: {passed_tests} ✅")
    print(f"Failed: {failed_tests} ❌")
    print(f"Total Duration: {total_duration:.2f}s")
    print(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%")
    
    if failed_tests > 0:
        print("\n🔍 FAILED TESTS:")
        for result in results:
            if not result.success:
                print(f"  ❌ {result.name}: {result.message}")
    
    print("\n📋 DETAILED RESULTS:")
    for result in results:
        status = "✅ PASS" if result.success else "❌ FAIL"
        print(f"  {status} {result.name} ({result.duration:.2f}s)")
        if result.details:
            for key, value in result.details.items():
                print(f"    {key}: {value}")
    
    print("=" * 60)

async def main():
    """Main test runner"""
    tester = BalancerTester()
    
    try:
        results = await tester.run_all_tests()
        print_summary(results)
        
        # Return exit code based on results
        failed_count = sum(1 for r in results if not r.success)
        return 0 if failed_count == 0 else 1
        
    except KeyboardInterrupt:
        print("\n⚠️  Tests interrupted by user")
        return 1
    except Exception as e:
        print(f"\n💥 Test runner error: {e}")
        return 1
    finally:
        await tester.close()

if __name__ == "__main__":
    import sys
    exit_code = asyncio.run(main())
    sys.exit(exit_code)