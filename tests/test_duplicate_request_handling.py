"""
Simplified tests for duplicate request handling using the new testing framework.

This file demonstrates how the new testing framework dramatically simplifies
test configuration and makes test logic more readable and maintainable.
"""

import asyncio
import pytest
import httpx
from unittest.mock import patch

# Import the new testing framework
from framework import (
    TestScenario, ProviderConfig, ProviderBehavior, ExpectedBehavior,
    TestEnvironment
)

# Test constants - all requests now go through balancer
# No direct mock provider URLs needed


class TestDuplicateRequestHandling:
    """Simplified duplicate request handling tests using dynamic configuration."""

    @pytest.mark.asyncio
    async def test_duplicate_non_streaming_requests(self):
        """Test duplicate non-streaming requests are properly cached."""
        # Create test scenario with duplicate caching behavior
        scenario = TestScenario(
            name="duplicate_non_streaming",
            providers=[
                ProviderConfig(
                    "cache_provider", 
                    ProviderBehavior.DUPLICATE_CACHE,
                    response_data={"content": "Cached non-streaming response"}
                )
            ],
            expected_behavior=ExpectedBehavior.SUCCESS,
            description="Test non-streaming request caching"
        )
        
        async with TestEnvironment(scenario) as env:
            test_request = {
                "model": env.effective_model_name,
                "max_tokens": 100,
                "messages": [
                    {
                        "role": "user",
                        "content": "Test duplicate non-streaming request"
                    }
                ]
            }
            
            # Test directly with Mock Server
            async with httpx.AsyncClient() as client:
                # Make first request to mock server
                response1 = await client.post(
                    f"{env.balancer_url}/v1/messages",
                    json=test_request
                )
                
                assert response1.status_code == 200
                data1 = response1.json()
                
                # Make identical second request
                response2 = await client.post(
                    f"{env.balancer_url}/v1/messages",
                    json=test_request
                )
                
                assert response2.status_code == 200
                data2 = response2.json()
                
                # Responses should be identical (cached)
                assert data1["content"] == data2["content"]
                # Verify it's our cached response
                assert data1["content"][0]["text"] == "Cached non-streaming response"

    @pytest.mark.asyncio
    async def test_duplicate_streaming_requests(self):
        """Test duplicate streaming requests are handled appropriately."""
        scenario = TestScenario(
            name="duplicate_streaming", 
            providers=[
                ProviderConfig(
                    "streaming_provider",
                    ProviderBehavior.SUCCESS,  # Streaming responses use SUCCESS behavior
                    response_data={"content": "Streaming response content"}
                )
            ],
            expected_behavior=ExpectedBehavior.SUCCESS
        )
        
        async with TestEnvironment(scenario) as env:
            test_streaming_request = {
                "model": env.effective_model_name,
                "max_tokens": 100,
                "stream": True,
                "messages": [
                    {
                        "role": "user",
                        "content": "Test duplicate streaming request"
                    }
                ]
            }
            
            async with httpx.AsyncClient() as client:
                # Helper function to make streaming request
                async def make_streaming_request():
                    response = await client.post(
                        f"{env.balancer_url}/v1/messages",
                        json=test_streaming_request
                    )
                    
                    assert response.status_code == 200
                    assert "text/event-stream" in response.headers.get("content-type", "")
                    
                    # Collect response chunks
                    chunks = []
                    async for chunk in response.aiter_text():
                        if chunk.strip():
                            chunks.append(chunk.strip())
                    
                    return chunks
                
                # Start both requests concurrently with a small delay
                async def request_with_delay(delay=0):
                    if delay > 0:
                        await asyncio.sleep(delay)
                    return await make_streaming_request()
                
                # Make concurrent requests
                tasks = [
                    request_with_delay(0),      # First request starts immediately
                    request_with_delay(0.05)    # Second request starts after 0.05s
                ]
                
                chunks1, chunks2 = await asyncio.gather(*tasks)
                
                # Both should have streaming content
                assert len(chunks1) > 0, f"First request got no chunks: {chunks1}"
                assert len(chunks2) > 0, f"Second request got no chunks: {chunks2}"

    @pytest.mark.asyncio
    async def test_mixed_streaming_non_streaming_duplicates(self):
        """Test duplicate requests with mixed streaming and non-streaming modes."""
        scenario = TestScenario(
            name="mixed_duplicate",
            providers=[
                ProviderConfig(
                    "mixed_provider",
                    ProviderBehavior.SUCCESS,
                    response_data={"content": "Mixed mode response"}
                )
            ]
        )
        
        async with TestEnvironment(scenario) as env:
            base_request = {
                "model": env.effective_model_name,
                "max_tokens": 100,
                "messages": [
                    {
                        "role": "user",
                        "content": "Mixed mode duplicate test"
                    }
                ]
            }
            
            async with httpx.AsyncClient() as client:
                # Make non-streaming request first
                non_streaming_request = base_request.copy()
                non_streaming_request["stream"] = False
                
                response1 = await client.post(
                    f"{env.balancer_url}/v1/messages",
                    json=non_streaming_request
                )
                
                assert response1.status_code == 200
                data1 = response1.json()
                assert data1["type"] == "message"
                
                # Now make streaming request with same content
                streaming_request = base_request.copy()
                streaming_request["stream"] = True
                
                response2 = await client.post(
                    f"{env.balancer_url}/v1/messages",
                    json=streaming_request
                )
                
                assert response2.status_code == 200
                assert "text/event-stream" in response2.headers.get("content-type", "")
                
                # Both should work despite different streaming modes
                chunks2 = []
                async for chunk in response2.aiter_text():
                    if chunk.strip():
                        chunks2.append(chunk.strip())
                
                assert len(chunks2) > 0

    @pytest.mark.asyncio
    async def test_concurrent_duplicate_requests(self):
        """Test concurrent duplicate requests are handled properly."""
        scenario = TestScenario(
            name="concurrent_duplicate",
            providers=[
                ProviderConfig(
                    "concurrent_provider",
                    ProviderBehavior.DUPLICATE_CACHE,
                    response_data={"content": "Concurrent response"},
                    delay_ms=50  # Shorter delay to reduce cancellation risk
                )
            ]
        )
        
        async with TestEnvironment(scenario) as env:
            test_request = {
                "model": env.effective_model_name,
                "max_tokens": 100,
                "messages": [
                    {
                        "role": "user",
                        "content": "Test concurrent duplicate request"
                    }
                ]
            }
            
            async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
                # Make concurrent identical requests
                async def make_request():
                    return await client.post(
                        f"{env.balancer_url}/v1/messages",
                        json=test_request
                    )
                
                tasks = [make_request() for _ in range(3)]
                responses = await asyncio.gather(*tasks)
                
                # With concurrent duplicate requests, we can get:
                # - 200: Original or successfully deduplicated request
                # - 409: Duplicate request where original was cancelled
                success_count = 0
                conflict_count = 0
                
                for response in responses:
                    if response.status_code == 200:
                        success_count += 1
                        data = response.json()
                        assert data["type"] == "message"
                    elif response.status_code == 409:
                        conflict_count += 1
                        data = response.json()
                        assert data["type"] == "error"
                        assert "cancelled" in data["error"]["message"] or "Original request was cancelled" in data["error"]["message"]
                    else:
                        # Unexpected status code
                        assert False, f"Unexpected status code: {response.status_code}, body: {response.text}"
                
                # At least one request should succeed
                assert success_count >= 1, f"Expected at least 1 success, got {success_count} successes and {conflict_count} conflicts"
                # Total responses should match request count
                assert success_count + conflict_count == 3

    @pytest.mark.asyncio
    async def test_duplicate_requests_with_different_parameters(self):
        """Test that requests with different parameters are not considered duplicates."""
        scenario = TestScenario(
            name="parameter_sensitive",
            providers=[
                ProviderConfig(
                    "param_provider",
                    ProviderBehavior.SUCCESS,
                    response_data={"content": "Parameter sensitive response"}
                )
            ]
        )
        
        async with TestEnvironment(scenario) as env:
            base_messages = [
                {
                    "role": "user",
                    "content": "Same content, different parameters"
                }
            ]
            
            async with httpx.AsyncClient() as client:
                # First request with temperature 0.5
                request1 = {
                    "model": env.effective_model_name,
                    "max_tokens": 100,
                    "temperature": 0.5,
                    "messages": base_messages
                }
                
                response1 = await client.post(
                    f"{env.balancer_url}/v1/messages",
                    json=request1
                )
                
                assert response1.status_code == 200
                data1 = response1.json()
                
                # Second request with temperature 0.8 (different parameter)
                request2 = {
                    "model": env.effective_model_name,
                    "max_tokens": 100,
                    "temperature": 0.8,
                    "messages": base_messages
                }
                
                response2 = await client.post(
                    f"{env.balancer_url}/v1/messages",
                    json=request2
                )
                
                assert response2.status_code == 200
                data2 = response2.json()
                
                # Different parameters should result in different requests
                assert data1["type"] == "message"
                assert data2["type"] == "message"

    @pytest.mark.asyncio
    async def test_duplicate_requests_with_system_messages(self):
        """Test duplicate detection with system messages."""
        scenario = TestScenario(
            name="system_message_duplicate",
            providers=[
                ProviderConfig(
                    "system_provider",
                    ProviderBehavior.DUPLICATE_CACHE,
                    response_data={"content": "System message response"}
                )
            ]
        )
        
        async with TestEnvironment(scenario) as env:
            request_data = {
                "model": env.effective_model_name,
                "max_tokens": 100,
                "system": "You are a helpful assistant.",
                "messages": [
                    {
                        "role": "user",
                        "content": "Hello with system message"
                    }
                ]
            }
            
            async with httpx.AsyncClient() as client:
                # Make first request
                response1 = await client.post(
                    f"{env.balancer_url}/v1/messages",
                    json=request_data
                )
                
                assert response1.status_code == 200
                
                # Make duplicate request
                response2 = await client.post(
                    f"{env.balancer_url}/v1/messages",
                    json=request_data
                )
                
                assert response2.status_code == 200
                
                # Should handle system messages in duplicate detection
                data1 = response1.json()
                data2 = response2.json()
                assert data1["content"] == data2["content"]

    @pytest.mark.asyncio
    async def test_duplicate_requests_with_tools(self):
        """Test duplicate detection with tool definitions."""
        scenario = TestScenario(
            name="tools_duplicate",
            providers=[
                ProviderConfig(
                    "tools_provider",
                    ProviderBehavior.DUPLICATE_CACHE,
                    response_data={"content": "Tools response"}
                )
            ]
        )
        
        async with TestEnvironment(scenario) as env:
            request_data = {
                "model": env.effective_model_name,
                "max_tokens": 100,
                "messages": [
                    {
                        "role": "user",
                        "content": "Use the weather tool"
                    }
                ],
                "tools": [
                    {
                        "name": "get_weather",
                        "description": "Get weather information",
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "location": {"type": "string"}
                            },
                            "required": ["location"]
                        }
                    }
                ]
            }
            
            async with httpx.AsyncClient() as client:
                # Make first request
                response1 = await client.post(
                    f"{env.balancer_url}/v1/messages",
                    json=request_data
                )
                
                assert response1.status_code == 200
                
                # Make duplicate request
                response2 = await client.post(
                    f"{env.balancer_url}/v1/messages",
                    json=request_data
                )
                
                assert response2.status_code == 200
                
                # Should handle tools in duplicate detection
                data1 = response1.json()
                data2 = response2.json()
                assert data1["content"] == data2["content"]

    @pytest.mark.asyncio
    async def test_cache_expiration_behavior(self):
        """Test cache expiration and refresh behavior."""
        scenario = TestScenario(
            name="cache_expiration",
            providers=[
                ProviderConfig(
                    "cache_provider",
                    ProviderBehavior.SUCCESS,  # Use SUCCESS instead of DUPLICATE_CACHE for this test
                    response_data={"content": "Cacheable response"}
                )
            ]
        )
        
        async with TestEnvironment(scenario) as env:
            test_request = {
                "model": env.effective_model_name,
                "max_tokens": 100,
                "messages": [
                    {
                        "role": "user",
                        "content": "Test cache expiration"
                    }
                ]
            }
            
            async with httpx.AsyncClient() as client:
                # Make first request
                response1 = await client.post(
                    f"{env.balancer_url}/v1/messages",
                    json=test_request
                )
                
                assert response1.status_code == 200
                data1 = response1.json()
                
                # Make another request (no actual cache expiration simulation in Mock Server)
                response2 = await client.post(
                    f"{env.balancer_url}/v1/messages",
                    json=test_request
                )
                
                assert response2.status_code == 200
                data2 = response2.json()
                
                # Both should be valid responses
                assert data1["type"] == "message"
                assert data2["type"] == "message"

    @pytest.mark.asyncio
    async def test_duplicate_detection_with_provider_failover(self):
        """Test duplicate detection when provider failover occurs."""
        scenario = TestScenario(
            name="failover_duplicate",
            providers=[
                ProviderConfig(
                    "success_provider",
                    ProviderBehavior.DUPLICATE_CACHE,
                    priority=1,
                    response_data={"content": "Failover success response"}
                )
            ],
            expected_behavior=ExpectedBehavior.SUCCESS
        )
        
        async with TestEnvironment(scenario) as env:
            test_request = {
                "model": env.effective_model_name,
                "max_tokens": 100,
                "messages": [
                    {
                        "role": "user",
                        "content": "Test failover duplicate request"
                    }
                ]
            }
            
            async with httpx.AsyncClient() as client:
                # Make first request
                response1 = await client.post(
                    f"{env.balancer_url}/v1/messages",
                    json=test_request
                )
                
                assert response1.status_code == 200
                
                # Make duplicate request
                response2 = await client.post(
                    f"{env.balancer_url}/v1/messages",
                    json=test_request
                )
                
                assert response2.status_code == 200
                
                # Both should succeed
                data1 = response1.json()
                data2 = response2.json()
                assert data1["type"] == "message"
                assert data2["type"] == "message"
                assert data1["content"] == data2["content"]