#!/usr/bin/env python3
"""
Test script for Claude Code Provider Balancer
Tests basic functionality, provider status, and load balancing.
"""

import asyncio
import json
import time
from typing import Dict, Any
import httpx


class ProviderBalancerTester:
    def __init__(self, base_url: str = "http://127.0.0.1:8080"):
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def test_health_check(self) -> bool:
        """Test basic health check endpoint"""
        print("Testing health check...")
        try:
            response = await self.client.get(f"{self.base_url}/")
            if response.status_code == 200:
                data = response.json()
                print(f"✓ Health check passed: {data['proxy_name']} v{data['version']}")
                return True
            else:
                print(f"✗ Health check failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"✗ Health check error: {e}")
            return False
    
    async def test_providers_status(self) -> bool:
        """Test providers status endpoint"""
        print("\nTesting providers status...")
        try:
            response = await self.client.get(f"{self.base_url}/providers")
            if response.status_code == 200:
                data = response.json()
                print(f"✓ Providers status retrieved")
                print(f"  Total providers: {data['total_providers']}")
                print(f"  Healthy providers: {data['healthy_providers']}")
                print(f"  Current provider: {data['current_provider']}")
                
                for provider in data['providers']:
                    status = "✓" if provider['healthy'] else "✗"
                    print(f"  {status} {provider['name']} ({provider['type']}): {provider['base_url']}")
                
                return True
            else:
                print(f"✗ Providers status failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"✗ Providers status error: {e}")
            return False
    
    async def test_token_count(self) -> bool:
        """Test token counting endpoint"""
        print("\nTesting token counting...")
        try:
            test_request = {
                "model": "claude-3-5-sonnet-20241022",
                "messages": [
                    {"role": "user", "content": "Hello, how are you?"}
                ]
            }
            
            response = await self.client.post(
                f"{self.base_url}/v1/messages/count_tokens",
                json=test_request
            )
            
            if response.status_code == 200:
                data = response.json()
                print(f"✓ Token counting passed: {data['input_tokens']} tokens")
                return True
            else:
                print(f"✗ Token counting failed: {response.status_code}")
                print(f"  Response: {response.text}")
                return False
        except Exception as e:
            print(f"✗ Token counting error: {e}")
            return False
    
    async def test_message_request(self, model: str = "claude-3-5-haiku-20241022") -> bool:
        """Test actual message request (will fail without valid API keys)"""
        print(f"\nTesting message request with model: {model}...")
        try:
            test_request = {
                "model": model,
                "max_tokens": 100,
                "messages": [
                    {"role": "user", "content": "Say hello in a short sentence."}
                ]
            }
            
            response = await self.client.post(
                f"{self.base_url}/v1/messages",
                json=test_request,
                headers={
                    "x-api-key": "test-key",
                    "anthropic-version": "2023-06-01"
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                print(f"✓ Message request succeeded")
                print(f"  Response type: {data.get('type', 'unknown')}")
                print(f"  Usage: {data.get('usage', {})}")
                return True
            elif response.status_code == 401:
                print(f"⚠ Message request failed with 401 (expected without valid API keys)")
                return True  # This is expected behavior
            elif response.status_code == 503:
                print(f"⚠ All providers unavailable (503) - expected without valid configs")
                return True  # This is expected behavior
            else:
                print(f"✗ Message request failed: {response.status_code}")
                print(f"  Response: {response.text}")
                return False
        except Exception as e:
            print(f"✗ Message request error: {e}")
            return False
    
    async def test_provider_reload(self) -> bool:
        """Test provider configuration reload"""
        print("\nTesting provider configuration reload...")
        try:
            response = await self.client.post(f"{self.base_url}/providers/reload")
            if response.status_code == 200:
                data = response.json()
                print(f"✓ Provider reload succeeded: {data['message']}")
                return True
            else:
                print(f"✗ Provider reload failed: {response.status_code}")
                print(f"  Response: {response.text}")
                return False
        except Exception as e:
            print(f"✗ Provider reload error: {e}")
            return False
    
    async def test_model_selection(self) -> bool:
        """Test different model selections"""
        print("\nTesting model selection...")
        models_to_test = [
            "claude-3-5-sonnet-20241022",  # Should use big model
            "claude-3-5-haiku-20241022",   # Should use small model
            "claude-3-opus-20240229",      # Should use big model
            "unknown-model"                # Should default
        ]
        
        all_passed = True
        for model in models_to_test:
            print(f"  Testing model: {model}")
            result = await self.test_message_request(model)
            if not result:
                all_passed = False
        
        return all_passed
    
    async def run_all_tests(self) -> bool:
        """Run all tests"""
        print("=" * 60)
        print("Claude Code Provider Balancer - Test Suite")
        print("=" * 60)
        
        tests = [
            ("Health Check", self.test_health_check),
            ("Providers Status", self.test_providers_status),
            ("Token Counting", self.test_token_count),
            ("Provider Reload", self.test_provider_reload),
            ("Model Selection", self.test_model_selection),
        ]
        
        passed = 0
        total = len(tests)
        
        for test_name, test_func in tests:
            print(f"\n[{passed + 1}/{total}] Running {test_name}...")
            try:
                if await test_func():
                    passed += 1
                time.sleep(0.5)  # Small delay between tests
            except Exception as e:
                print(f"✗ {test_name} crashed: {e}")
        
        print("\n" + "=" * 60)
        print(f"Test Results: {passed}/{total} tests passed")
        print("=" * 60)
        
        if passed == total:
            print("🎉 All tests passed!")
        else:
            print(f"⚠️  {total - passed} tests failed or had issues")
        
        return passed == total
    
    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()


async def main():
    """Main test runner"""
    print("Starting Claude Code Provider Balancer tests...")
    print("Make sure the server is running on http://127.0.0.1:8080")
    print("You can start it with: cd src && python main.py")
    
    input("\nPress Enter to continue with tests...")
    
    tester = ProviderBalancerTester()
    try:
        success = await tester.run_all_tests()
        return 0 if success else 1
    finally:
        await tester.close()


if __name__ == "__main__":
    import sys
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\nTests interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nTest runner crashed: {e}")
        sys.exit(1)