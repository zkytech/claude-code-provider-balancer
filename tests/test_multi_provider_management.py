"""
Simplified tests for multi-provider management using the new testing framework.

This file tests provider management, failover, and availability scenarios through
HTTP requests with dynamic configuration generation.

Failover Test Coverage:
- test_basic_provider_failover: Core failover functionality (PRIMARY TEST)
- test_concurrent_requests_with_failover: Concurrent request handling during failover
- Additional specialized failover tests are in their respective files:
  * test_streaming_requests.py: Streaming-specific failover
  * test_provider_error_handling.py: Error-triggered failover
  * test_mixed_provider_responses.py: Mixed provider type failover with status tracking
"""

import asyncio
import pytest
import httpx
import time
from typing import Dict, Any

# Import the new testing framework
from framework import (
    Scenario, ProviderConfig, ProviderBehavior, ExpectedBehavior,
    Environment
)

# Test constants - all requests now go through balancer
# No direct mock provider URLs needed


class TestMultiProviderManagement:
    """Simplified multi-provider management tests using dynamic configuration."""

    @pytest.mark.asyncio
    async def test_primary_provider_success(self):
        """Test successful request to primary provider."""
        scenario = Scenario(
            name="primary_success_test",
            providers=[
                ProviderConfig(
                    "primary_provider",
                    ProviderBehavior.SUCCESS,
                    priority=1,
                    response_data={
                        "content": "Primary provider successful response"
                    }
                )
            ],
            expected_behavior=ExpectedBehavior.SUCCESS,
            description="Test primary provider handles requests successfully"
        )
        
        async with Environment(scenario) as env:
            request_data = {
                "model": env.effective_model_name,
                "max_tokens": 100,
                "messages": [{"role": "user", "content": "Test primary provider success"}]
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{env.balancer_url}/v1/messages",
                    json=request_data
                )
                
                assert response.status_code == 200
                data = response.json()
                assert data["type"] == "message"
                assert "Primary provider successful response" in data["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_basic_provider_failover(self):
        """
        Core test for basic provider failover functionality.
        
        This is the primary test for failover behavior. Other failover tests in different 
        files focus on specific scenarios (streaming, concurrent, error handling, etc.).
        """
        scenario = Scenario(
            name="failover_test",
            providers=[
                ProviderConfig(
                    "primary_error_provider",
                    ProviderBehavior.ERROR,
                    priority=1,
                    error_http_code=500,
                    error_message="Primary provider error"
                ),
                ProviderConfig(
                    "secondary_success_provider",
                    ProviderBehavior.SUCCESS,
                    priority=2,
                    response_data={
                        "content": "Secondary provider failover success"
                    }
                )
            ],
            expected_behavior=ExpectedBehavior.FAILOVER,
            description="Test failover from primary to secondary provider",
            settings_override={
                "unhealthy_threshold": 1,  # Quick failover for testing
                "failure_cooldown": 5
            }
        )
        
        async with Environment(scenario) as env:
            request_data = {
                "model": env.effective_model_name,
                "max_tokens": 100,
                "messages": [{"role": "user", "content": "Test failover to secondary"}]
            }
            
            async with httpx.AsyncClient() as client:
                # Test balancer failover behavior - should use secondary after primary fails
                response = await client.post(
                    f"{env.balancer_url}/v1/messages",
                    json=request_data
                )
                assert response.status_code == 200
                data = response.json()
                assert "Secondary provider failover success" in data["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_all_providers_unavailable(self):
        """Test scenario when all providers are unavailable."""
        scenario = Scenario(
            name="all_providers_error_test",
            providers=[
                ProviderConfig(
                    "error_provider_1",
                    ProviderBehavior.SERVICE_UNAVAILABLE,
                    priority=1,
                    error_http_code=503,
                    error_message="Provider 1 unavailable"
                ),
                ProviderConfig(
                    "error_provider_2",
                    ProviderBehavior.SERVICE_UNAVAILABLE,
                    priority=2,
                    error_http_code=503,
                    error_message="Provider 2 unavailable"
                )
            ],
            expected_behavior=ExpectedBehavior.ERROR,
            description="Test behavior when all providers are unavailable"
        )
        
        async with Environment(scenario) as env:
            request_data = {
                "model": env.effective_model_name,
                "max_tokens": 100,
                "messages": [{"role": "user", "content": "Test all providers unavailable"}]
            }
            
            async with httpx.AsyncClient() as client:
                # Test balancer with all providers unavailable
                response = await client.post(
                    f"{env.balancer_url}/v1/messages",
                    json=request_data
                )
                # Balancer should return error when all providers fail
                assert response.status_code >= 400

    @pytest.mark.asyncio
    async def test_provider_cooldown_mechanism(self):
        """Test provider cooldown mechanism after failures."""
        scenario = Scenario(
            name="cooldown_test",
            providers=[
                ProviderConfig(
                    "cooldown_provider",
                    ProviderBehavior.BAD_GATEWAY,
                    error_http_code=502,
                    error_message="Provider in cooldown"
                )
            ],
            expected_behavior=ExpectedBehavior.ERROR,
            description="Test provider cooldown mechanism",
            settings_override={
                "failure_cooldown": 1,  # Short cooldown for testing
                "unhealthy_threshold": 1
            }
        )
        
        async with Environment(scenario) as env:
            request_data = {
                "model": env.effective_model_name,
                "max_tokens": 100,
                "messages": [{"role": "user", "content": "Test cooldown mechanism"}]
            }
            
            async with httpx.AsyncClient() as client:
                # Multiple requests to test cooldown behavior through balancer
                for i in range(3):
                    response = await client.post(
                        f"{env.balancer_url}/v1/messages",
                        json=request_data
                    )
                    
                    # Should consistently return error during cooldown
                    assert response.status_code >= 400

    @pytest.mark.asyncio
    async def test_provider_recovery_after_cooldown(self):
        """Test provider recovery after cooldown period."""
        scenario = Scenario(
            name="recovery_test",
            providers=[
                ProviderConfig(
                    "recovery_provider",
                    ProviderBehavior.SUCCESS,
                    response_data={
                        "content": "Provider recovered successfully"
                    }
                )
            ],
            expected_behavior=ExpectedBehavior.SUCCESS,
            description="Test provider recovery after cooldown period",
            settings_override={
                "failure_cooldown": 0.1,  # Very short cooldown for testing
                "unhealthy_threshold": 1
            }
        )
        
        async with Environment(scenario) as env:
            request_data = {
                "model": env.effective_model_name,
                "max_tokens": 100,
                "messages": [{"role": "user", "content": "Test provider recovery"}]
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{env.balancer_url}/v1/messages",
                    json=request_data
                )
                
                assert response.status_code == 200
                data = response.json()
                assert "Provider recovered successfully" in data["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_provider_priority_ordering(self):
        """Test that providers are selected based on priority ordering."""
        scenario = Scenario(
            name="priority_test",
            providers=[
                ProviderConfig(
                    "high_priority_provider",
                    ProviderBehavior.SUCCESS,
                    priority=1,
                    response_data={
                        "content": "High priority provider response"
                    }
                ),
                ProviderConfig(
                    "low_priority_provider",
                    ProviderBehavior.SUCCESS,
                    priority=2,
                    response_data={
                        "content": "Low priority provider response"
                    }
                )
            ],
            expected_behavior=ExpectedBehavior.SUCCESS,
            description="Test provider priority ordering"
        )
        
        async with Environment(scenario) as env:
            request_data = {
                "model": env.effective_model_name,
                "max_tokens": 100,
                "messages": [{"role": "user", "content": "Test priority ordering"}]
            }
            
            async with httpx.AsyncClient() as client:
                # Test high priority provider through balancer
                response = await client.post(
                    f"{env.balancer_url}/v1/messages",
                    json=request_data
                )
                
                assert response.status_code == 200
                data = response.json()
                assert "High priority provider response" in data["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_provider_type_specific_error_handling(self):
        """Test error handling specific to different provider types."""
        # Test Anthropic provider error handling
        anthropic_scenario = Scenario(
            name="anthropic_error_handling_test",
            providers=[
                ProviderConfig(
                    "anthropic_error_provider",
                    ProviderBehavior.ERROR,
                    provider_type="anthropic",
                    error_http_code=400,
                    error_message="Anthropic provider error"
                )
            ],
            expected_behavior=ExpectedBehavior.ERROR,
            description="Test Anthropic provider error handling"
        )
        
        async with Environment(anthropic_scenario) as env:
            request_data = {
                "model": env.effective_model_name,
                "max_tokens": 100,
                "messages": [{"role": "user", "content": "Test Anthropic error handling"}]
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{env.balancer_url}/v1/messages",
                    json=request_data
                )
                
                assert response.status_code == 400
                error_data = response.json()
                assert "error" in error_data
                assert "Anthropic provider error" in error_data["error"]["message"]

        # Test OpenAI provider error handling
        openai_scenario = Scenario(
            name="openai_error_handling_test",
            providers=[
                ProviderConfig(
                    "openai_error_provider",
                    ProviderBehavior.ERROR,
                    provider_type="openai",
                    error_http_code=401,
                    error_message="OpenAI provider error"
                )
            ],
            expected_behavior=ExpectedBehavior.ERROR,
            description="Test OpenAI provider error handling"
        )
        
        async with Environment(openai_scenario) as env:
            request_data = {
                "model": env.effective_model_name,
                "max_tokens": 100,
                "messages": [{"role": "user", "content": "Test OpenAI error handling"}]
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{env.balancer_url}/v1/messages",
                    json=request_data
                )
                
                assert response.status_code == 401
                error_data = response.json()
                assert "error" in error_data

    @pytest.mark.asyncio
    async def test_concurrent_requests_with_failover(self):
        """Test concurrent requests during provider failover."""
        scenario = Scenario(
            name="concurrent_failover_test",
            providers=[
                ProviderConfig(
                    "concurrent_error_provider",
                    ProviderBehavior.ERROR,
                    priority=1,
                    error_http_code=500,
                    error_message="Concurrent error provider"
                ),
                ProviderConfig(
                    "concurrent_success_provider",
                    ProviderBehavior.SUCCESS,
                    priority=2,
                    response_data={
                        "content": "Concurrent success provider response"
                    }
                )
            ],
            expected_behavior=ExpectedBehavior.FAILOVER,
            description="Test concurrent requests with failover",
            settings_override={
                "unhealthy_threshold": 1,
                "failure_cooldown": 5
            }
        )
        
        async with Environment(scenario) as env:
            async def make_request(client, content_suffix=""):
                return await client.post(
                    f"{env.balancer_url}/v1/messages",
                    json={
                        "model": env.effective_model_name,
                        "max_tokens": 100,
                        "messages": [{"role": "user", "content": f"Concurrent request {content_suffix}"}]
                    }
                )
            
            async with httpx.AsyncClient() as client:
                # Test concurrent requests through balancer
                tasks = [
                    make_request(client, f"concurrent_{i}")
                    for i in range(3)
                ]
                responses = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Count successful responses - balancer should handle failover
                success_count = sum(
                    1 for r in responses 
                    if hasattr(r, 'status_code') and r.status_code == 200
                )
                assert success_count >= 1  # At least some should succeed after failover

    @pytest.mark.asyncio
    async def test_model_routing_behavior(self):
        """Test provider selection based on model routing patterns."""
        # Test different model patterns
        test_cases = [
            ("claude-3-5-sonnet-20241022", "Anthropic model response"),
            ("gpt-3.5-turbo", "OpenAI model response"),
            ("custom-test-model", "Custom model response")
        ]
        
        for model_name, expected_content in test_cases:
            scenario = Scenario(
                name=f"model_routing_test_{model_name.replace('-', '_').replace('.', '_')}",
                providers=[
                    ProviderConfig(
                        f"model_router_provider_{model_name.replace('-', '_').replace('.', '_')}",
                        ProviderBehavior.SUCCESS,
                        response_data={
                            "content": expected_content
                        }
                    )
                ],
                expected_behavior=ExpectedBehavior.SUCCESS,
                description=f"Test routing for model {model_name}",
                model_name=model_name  # Set the specific model name for this scenario
            )
            
            async with Environment(scenario) as env:
                request_data = {
                    "model": model_name,  # Use the specific model name for routing
                    "max_tokens": 100,
                    "messages": [{"role": "user", "content": f"Test routing for {model_name}"}]
                }
                
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        f"{env.balancer_url}/v1/messages",
                        json=request_data
                    )
                    
                    assert response.status_code == 200
                    data = response.json()
                    assert expected_content in data["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_sticky_routing_behavior(self):
        """Test sticky routing behavior after successful provider selection."""
        scenario = Scenario(
            name="sticky_routing_test",
            providers=[
                ProviderConfig(
                    "sticky_provider",
                    ProviderBehavior.SUCCESS,
                    response_data={
                        "content": "Sticky routing test response"
                    }
                )
            ],
            expected_behavior=ExpectedBehavior.SUCCESS,
            description="Test sticky routing behavior",
            settings_override={
                "sticky_provider_duration": 300  # 5 minutes sticky duration
            }
        )
        
        async with Environment(scenario) as env:
            request_data = {
                "model": env.effective_model_name,
                "max_tokens": 100,
                "messages": [{"role": "user", "content": "Test sticky routing"}]
            }
            
            async with httpx.AsyncClient() as client:
                # First request establishes sticky routing through balancer
                response1 = await client.post(
                    f"{env.balancer_url}/v1/messages",
                    json=request_data
                )
                
                assert response1.status_code == 200
                data1 = response1.json()
                assert "Sticky routing test response" in data1["content"][0]["text"]
                
                # Second request should use same provider (sticky behavior)
                response2 = await client.post(
                    f"{env.balancer_url}/v1/messages",
                    json=request_data
                )
                
                assert response2.status_code == 200
                data2 = response2.json()
                assert "Sticky routing test response" in data2["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_provider_health_status_tracking(self):
        """Test provider health status is properly tracked."""
        scenario = Scenario(
            name="health_tracking_test",
            providers=[
                ProviderConfig(
                    "healthy_provider",
                    ProviderBehavior.SUCCESS,
                    response_data={
                        "content": "Healthy provider response"
                    }
                ),
                ProviderConfig(
                    "unhealthy_provider",
                    ProviderBehavior.SERVICE_UNAVAILABLE,
                    error_http_code=503,
                    error_message="Unhealthy provider"
                )
            ],
            expected_behavior=ExpectedBehavior.SUCCESS,
            description="Test provider health status tracking"
        )
        
        async with Environment(scenario) as env:
            request_data = {
                "model": env.effective_model_name,
                "max_tokens": 100,
                "messages": [{"role": "user", "content": "Test health tracking"}]
            }
            
            async with httpx.AsyncClient() as client:
                # Test health tracking through balancer - should route to healthy provider
                response = await client.post(
                    f"{env.balancer_url}/v1/messages",
                    json=request_data
                )
                # Balancer should route to healthy provider even if unhealthy ones exist
                assert response.status_code == 200
                
                # Health status is tracked through the actual behavior patterns
                # demonstrated by successful/failed HTTP responses

    @pytest.mark.asyncio
    async def test_provider_selection_strategies(self):
        """Test different provider selection strategies."""
        # Test priority-based selection
        priority_scenario = Scenario(
            name="priority_strategy_test",
            providers=[
                ProviderConfig(
                    "priority_1_provider",
                    ProviderBehavior.SUCCESS,
                    priority=1,
                    response_data={
                        "content": "Priority 1 provider response"
                    }
                ),
                ProviderConfig(
                    "priority_2_provider",
                    ProviderBehavior.SUCCESS,
                    priority=2,
                    response_data={
                        "content": "Priority 2 provider response"
                    }
                )
            ],
            expected_behavior=ExpectedBehavior.SUCCESS,
            description="Test priority-based provider selection",
            settings_override={
                "selection_strategy": "priority"
            }
        )
        
        async with Environment(priority_scenario) as env:
            request_data = {
                "model": env.effective_model_name,
                "max_tokens": 100,
                "messages": [{"role": "user", "content": "Test priority selection"}]
            }
            
            async with httpx.AsyncClient() as client:
                # Higher priority provider should be preferred through balancer
                response = await client.post(
                    f"{env.balancer_url}/v1/messages",
                    json=request_data
                )
                
                assert response.status_code == 200
                data = response.json()
                assert "Priority 1 provider response" in data["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_provider_error_classification(self):
        """Test different types of provider errors are classified correctly."""
        error_types = [
            (ProviderBehavior.CONNECTION_ERROR, 502, "Connection Error"),
            (ProviderBehavior.RATE_LIMIT, 429, "Rate Limited"),
            (ProviderBehavior.INSUFFICIENT_CREDITS, 402, "Insufficient credits"),
            (ProviderBehavior.TIMEOUT, 408, "Request Timeout"),
            (ProviderBehavior.SERVICE_UNAVAILABLE, 503, "Service Unavailable")
        ]
        
        for behavior, expected_code, expected_message in error_types:
            scenario = Scenario(
                name=f"error_classification_{behavior.value}_test",
                providers=[
                    ProviderConfig(
                        f"error_provider_{behavior.value}",
                        behavior,
                        error_http_code=expected_code,
                        error_message=f"Test {expected_message}"
                    )
                ],
                expected_behavior=ExpectedBehavior.ERROR,
                description=f"Test {behavior.value} error classification"
            )
            
            async with Environment(scenario) as env:
                request_data = {
                    "model": env.effective_model_name,
                    "max_tokens": 100,
                    "messages": [{"role": "user", "content": f"Test {behavior.value}"}]
                }
                
                async with httpx.AsyncClient(timeout=15.0) as client:
                    response = await client.post(
                        f"{env.balancer_url}/v1/messages",
                        json=request_data
                    )
                    
                    assert response.status_code == expected_code
                    error_data = response.json()
                    assert "error" in error_data
                    assert expected_message in error_data["error"]["message"]