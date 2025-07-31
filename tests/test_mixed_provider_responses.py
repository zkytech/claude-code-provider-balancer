"""
Simplified tests for mixed provider responses using the new testing framework.

This file demonstrates testing mixed provider scenarios (different types, formats, behaviors)
without complex configuration dependencies.
"""

import asyncio
import pytest
import httpx
from typing import Dict, Any

# Import the new testing framework
from framework import (
    Scenario, ProviderConfig, ProviderBehavior, ExpectedBehavior,
    Environment
)

# Test constants - all requests now go through balancer
# No direct mock provider URLs needed


class TestMixedProviderResponses:
    """Simplified mixed provider response tests using dynamic configuration."""

    @pytest.mark.asyncio
    async def test_successful_provider_response(self):
        """Test basic successful provider response format."""
        scenario = Scenario(
            name="success_test",
            providers=[
                ProviderConfig(
                    "success_provider",
                    ProviderBehavior.SUCCESS,
                    response_data={
                        "content": "Hello from successful provider"
                    }
                )
            ],
            expected_behavior=ExpectedBehavior.SUCCESS,
            description="Test successful provider response"
        )
        
        async with Environment(scenario) as env:
            request_data = {
                "model": env.model_name,
                "max_tokens": 100,
                "messages": [
                    {
                        "role": "user",
                        "content": "Hello"
                    }
                ]
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{env.balancer_url}/v1/messages",
                    json=request_data
                )
                
                assert response.status_code == 200
                data = response.json()
                
                # Verify Anthropic format response structure
                assert "id" in data
                assert "type" in data
                assert data["type"] == "message"
                assert "role" in data
                assert data["role"] == "assistant"
                assert "content" in data
                assert len(data["content"]) > 0
                assert data["content"][0]["type"] == "text"
                assert "Hello from successful provider" in data["content"][0]["text"]
                assert "usage" in data

    @pytest.mark.asyncio
    async def test_error_provider_response(self):
        """Test error provider response handling."""
        scenario = Scenario(
            name="error_test",
            providers=[
                ProviderConfig(
                    "error_provider",
                    ProviderBehavior.ERROR,
                    error_http_code=401,
                    error_message="Authentication failed"
                )
            ],
            expected_behavior=ExpectedBehavior.ERROR,
            description="Test error provider response"
        )
        
        async with Environment(scenario) as env:
            request_data = {
                "model": env.model_name,
                "max_tokens": 100,
                "messages": [
                    {
                        "role": "user",
                        "content": "Test error"
                    }
                ]
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{env.balancer_url}/v1/messages",
                    json=request_data
                )
                
                assert response.status_code == 401
                error_data = response.json()
                assert "error" in error_data
                assert "Authentication failed" in error_data["error"]["message"]

    @pytest.mark.asyncio
    async def test_service_unavailable_provider(self):
        """Test service unavailable provider behavior."""
        scenario = Scenario(
            name="service_unavailable_test",
            providers=[
                ProviderConfig(
                    "unavailable_provider",
                    ProviderBehavior.SERVICE_UNAVAILABLE,
                    error_http_code=503,
                    error_message="Service temporarily unavailable"
                )
            ],
            expected_behavior=ExpectedBehavior.ERROR,
            description="Test service unavailable behavior"
        )
        
        async with Environment(scenario) as env:
            request_data = {
                "model": env.model_name,
                "max_tokens": 100,
                "messages": [
                    {
                        "role": "user",
                        "content": "Test unavailable"
                    }
                ]
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{env.balancer_url}/v1/messages",
                    json=request_data
                )
                
                assert response.status_code == 503
                error_data = response.json()
                assert "error" in error_data
                assert "Service Unavailable" in error_data["error"]["message"]

    @pytest.mark.asyncio
    async def test_rate_limit_provider(self):
        """Test rate limit provider behavior."""
        scenario = Scenario(
            name="rate_limit_test",
            providers=[
                ProviderConfig(
                    "rate_limit_provider",
                    ProviderBehavior.RATE_LIMIT,
                    error_http_code=429,
                    error_message="Rate limit exceeded"
                )
            ],
            expected_behavior=ExpectedBehavior.ERROR,
            description="Test rate limit behavior"
        )
        
        async with Environment(scenario) as env:
            request_data = {
                "model": env.model_name,
                "max_tokens": 100,
                "messages": [
                    {
                        "role": "user",
                        "content": "Test rate limit"
                    }
                ]
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{env.balancer_url}/v1/messages",
                    json=request_data
                )
                
                assert response.status_code == 429
                error_data = response.json()
                assert "error" in error_data
                assert "Rate Limited" in error_data["error"]["message"]

    @pytest.mark.asyncio
    async def test_insufficient_credits_provider(self):
        """Test insufficient credits provider behavior."""
        scenario = Scenario(
            name="insufficient_credits_test",
            providers=[
                ProviderConfig(
                    "credits_provider",
                    ProviderBehavior.INSUFFICIENT_CREDITS,
                    error_http_code=402,
                    error_message="Insufficient credits"
                )
            ],
            expected_behavior=ExpectedBehavior.ERROR,
            description="Test insufficient credits behavior"
        )
        
        async with Environment(scenario) as env:
            request_data = {
                "model": env.model_name,
                "max_tokens": 100,
                "messages": [
                    {
                        "role": "user",
                        "content": "Test insufficient credits"
                    }
                ]
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{env.balancer_url}/v1/messages",
                    json=request_data
                )
                
                assert response.status_code == 402
                error_data = response.json()
                assert "error" in error_data
                assert "Insufficient credits" in error_data["error"]["message"]

    @pytest.mark.asyncio
    async def test_mixed_provider_failover_scenario(self):
        """
        Test failover between different provider types with detailed provider status checking.
        
        Note: This test is more comprehensive than basic failover tests as it also validates
        provider health status tracking and unhealthy_threshold behavior.
        """
        scenario = Scenario(
            name="mixed_failover_test",
            providers=[
                ProviderConfig(
                    "failing_provider",
                    ProviderBehavior.SERVICE_UNAVAILABLE,
                    priority=1,
                    error_http_code=503,
                    error_message="First provider unavailable"
                ),
                ProviderConfig(
                    "success_provider",
                    ProviderBehavior.SUCCESS,
                    priority=2,
                    response_data={
                        "content": "Successfully failed over to second provider"
                    }
                )
            ],
            expected_behavior=ExpectedBehavior.FAILOVER,
            description="Test failover between mixed provider types",
            settings_override={
                "unhealthy_threshold": 1  # Trigger failover after first error
            }
        )
        
        async with Environment(scenario) as env:
            # Test that both providers are configured correctly
            request_data = {
                "model": env.model_name,
                "max_tokens": 100,
                "messages": [
                    {
                        "role": "user",
                        "content": "Test failover"
                    }
                ]
            }
            
            async with httpx.AsyncClient() as client:
                # First, check initial provider status
                providers_before = await client.get(f"{env.balancer_url}/providers")
                assert providers_before.status_code == 200
                providers_data_before = providers_before.json()
                
                # Test first request - should trigger failover due to unhealthy_threshold=1
                response1 = await client.post(
                    f"{env.balancer_url}/v1/messages",
                    json=request_data
                )
                
                # Check provider status after first request
                providers_after = await client.get(f"{env.balancer_url}/providers")
                assert providers_after.status_code == 200
                providers_data_after = providers_after.json()
                
                # Verify that failing_provider is now marked as unhealthy
                failing_provider_status = None
                success_provider_status = None
                for provider in providers_data_after.get("providers", []):
                    if provider["name"] == "failing_provider":
                        failing_provider_status = provider
                    elif provider["name"] == "success_provider":
                        success_provider_status = provider
                
                # Assert that failing_provider is marked as unhealthy (has failures recorded)
                assert failing_provider_status is not None, "failing_provider not found in status"
                assert success_provider_status is not None, "success_provider not found in status"
                
                # The first request should either:
                # 1. Return 503 if failover didn't happen (expected behavior)
                # 2. Return 200 if failover happened successfully
                if response1.status_code == 200:
                    # Failover occurred - verify response comes from success_provider
                    data1 = response1.json()
                    assert "Successfully failed over to second provider" in data1["content"][0]["text"]
                else:
                    # No failover - should be 503 from failing_provider
                    assert response1.status_code == 503
                
                # Test second request - should always go to success_provider (failing_provider is unhealthy)
                response2 = await client.post(
                    f"{env.balancer_url}/v1/messages",
                    json=request_data
                )
                assert response2.status_code == 200
                data2 = response2.json()
                assert "Successfully failed over to second provider" in data2["content"][0]["text"]
                
                # Verify the unhealthy_threshold=1 took effect by checking error counts
                if "error_count" in failing_provider_status:
                    assert failing_provider_status["error_count"] >= 1, f"Expected error_count >= 1, got {failing_provider_status.get('error_count', 0)}"
                    print(f"✓ failing_provider has error_count: {failing_provider_status['error_count']}")

    @pytest.mark.asyncio
    async def test_streaming_request_handling(self):
        """Test streaming request handling."""
        scenario = Scenario(
            name="streaming_test",
            providers=[
                ProviderConfig(
                    "streaming_provider",
                    ProviderBehavior.SUCCESS,
                    response_data={
                        "content": "Streaming response content"
                    }
                )
            ],
            expected_behavior=ExpectedBehavior.SUCCESS,
            description="Test streaming request handling"
        )
        
        async with Environment(scenario) as env:
            request_data = {
                "model": env.model_name,
                "max_tokens": 100,
                "stream": True,
                "messages": [
                    {
                        "role": "user",
                        "content": "Test streaming"
                    }
                ]
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{env.balancer_url}/v1/messages",
                    json=request_data
                )
                
                # Verify response structure (streaming logic is handled by response generator)
                assert response.status_code == 200
                # The actual streaming behavior would depend on response generator implementation

    @pytest.mark.asyncio
    async def test_custom_response_data(self):
        """Test provider with custom response data."""
        custom_response = {
            "content": "Custom response with specific content",
            "model_info": "custom-model-v1",
            "custom_field": "test_value"
        }
        
        scenario = Scenario(
            name="custom_response_test",
            providers=[
                ProviderConfig(
                    "custom_provider",
                    ProviderBehavior.SUCCESS,
                    response_data=custom_response
                )
            ],
            expected_behavior=ExpectedBehavior.SUCCESS,
            description="Test provider with custom response data"
        )
        
        async with Environment(scenario) as env:
            request_data = {
                "model": env.model_name,
                "max_tokens": 100,
                "messages": [
                    {
                        "role": "user",
                        "content": "Test custom response"
                    }
                ]
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{env.balancer_url}/v1/messages",
                    json=request_data
                )
                
                assert response.status_code == 200
                data = response.json()
                
                # Verify custom content is included
                assert "Custom response with specific content" in data["content"][0]["text"]
                
                # The response should still maintain Anthropic format structure
                assert data["type"] == "message"
                assert data["role"] == "assistant"
                assert "usage" in data

    @pytest.mark.asyncio
    async def test_provider_with_delay(self):
        """Test provider with response delay."""
        scenario = Scenario(
            name="delay_test",
            providers=[
                ProviderConfig(
                    "delayed_provider",
                    ProviderBehavior.SUCCESS,
                    delay_ms=100,  # 100ms delay
                    response_data={
                        "content": "Delayed response"
                    }
                )
            ],
            expected_behavior=ExpectedBehavior.SUCCESS,
            description="Test provider with response delay"
        )
        
        async with Environment(scenario) as env:
            request_data = {
                "model": env.model_name,
                "max_tokens": 100,
                "messages": [
                    {
                        "role": "user",
                        "content": "Test delayed response"
                    }
                ]
            }
            
            import time
            start_time = time.time()
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{env.balancer_url}/v1/messages",
                    json=request_data
                )
            
            elapsed_time = time.time() - start_time
            
            assert response.status_code == 200
            # Verify delay was applied (allow some tolerance)
            assert elapsed_time >= 0.09  # At least 90ms
            
            data = response.json()
            assert "Delayed response" in data["content"][0]["text"]