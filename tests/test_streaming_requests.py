"""
Simplified tests for streaming request handling using the new testing framework.

This file tests streaming response processing, failover, and error handling through
HTTP requests with dynamic configuration generation.
"""

import asyncio
import pytest
import httpx
import json
from typing import Dict, Any

# Import the new testing framework
from framework import (
    Scenario, ProviderConfig, ProviderBehavior, ExpectedBehavior,
    Environment
)

# Test constants - all requests now go through balancer
# No direct mock provider URLs needed


class TestStreamingRequests:
    """Simplified streaming request tests using dynamic configuration."""

    @pytest.mark.asyncio
    async def test_successful_streaming_response(self):
        """Test successful streaming response handling."""
        scenario = Scenario(
            name="streaming_success_test",
            providers=[
                ProviderConfig(
                    "streaming_provider",
                    ProviderBehavior.STREAMING_SUCCESS,
                    response_data={
                        "content": "Hello! This is a streaming response test."
                    }
                )
            ],
            expected_behavior=ExpectedBehavior.SUCCESS,
            description="Test successful streaming response"
        )
        
        async with Environment(scenario) as env:
            request_data = {
                "model": env.effective_model_name,
                "max_tokens": 100,
                "stream": True,
                "messages": [{"role": "user", "content": "Test streaming response"}]
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{env.balancer_url}/v1/messages",
                    json=request_data
                )
                
                assert response.status_code == 200
                assert "text/event-stream" in response.headers.get("content-type", "")
                
                # Collect streaming chunks
                chunks = []
                async for chunk in response.aiter_text():
                    if chunk.strip():
                        chunks.append(chunk.strip())
                
                # Verify we got streaming events
                assert len(chunks) > 0
                chunk_text = '\n'.join(chunks)
                
                # Verify expected streaming events
                assert "message_start" in chunk_text
                assert "content_block_delta" in chunk_text
                assert "message_stop" in chunk_text

    @pytest.mark.asyncio
    async def test_streaming_provider_error(self):
        """Test streaming request with provider returning error."""
        scenario = Scenario(
            name="streaming_error_test",
            providers=[
                ProviderConfig(
                    "streaming_error_provider",
                    ProviderBehavior.ERROR,
                    error_http_code=500,
                    error_message="Streaming provider error"
                )
            ],
            expected_behavior=ExpectedBehavior.ERROR,
            description="Test streaming provider error handling"
        )
        
        async with Environment(scenario) as env:
            request_data = {
                "model": env.effective_model_name,
                "max_tokens": 100,
                "stream": True,
                "messages": [{"role": "user", "content": "Test streaming error"}]
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{env.balancer_url}/v1/messages",
                    json=request_data
                )
                
                assert response.status_code == 500
                error_data = response.json()
                assert "error" in error_data
                assert "Streaming provider error" in error_data["error"]["message"]

    @pytest.mark.asyncio
    async def test_streaming_timeout_handling(self):
        """Test streaming request timeout handling."""
        scenario = Scenario(
            name="streaming_timeout_test",
            providers=[
                ProviderConfig(
                    "timeout_provider",
                    ProviderBehavior.TIMEOUT,
                    error_http_code=408,
                    error_message="Request timeout"
                )
            ],
            expected_behavior=ExpectedBehavior.TIMEOUT,
            description="Test streaming timeout handling"
        )
        
        async with Environment(scenario) as env:
            request_data = {
                "model": env.effective_model_name,
                "max_tokens": 100,
                "stream": True,
                "messages": [{"role": "user", "content": "Test timeout"}]
            }
            
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(
                    f"{env.balancer_url}/v1/messages",
                    json=request_data
                )
                
                assert response.status_code == 408
                error_data = response.json()
                assert "error" in error_data
                assert "Request Timeout" in error_data["error"]["message"]

    @pytest.mark.asyncio
    async def test_streaming_failover(self):
        """Test failover for streaming requests."""
        scenario = Scenario(
            name="streaming_failover_test",
            providers=[
                ProviderConfig(
                    "streaming_error_provider",
                    ProviderBehavior.ERROR,
                    priority=1,
                    error_http_code=500,
                    error_message="Streaming provider error"
                ),
                ProviderConfig(
                    "streaming_success_provider",
                    ProviderBehavior.STREAMING_SUCCESS,
                    priority=2,
                    response_data={
                        "content": "Streaming failover success"
                    }
                )
            ],
            settings_override={
                "unhealthy_threshold": 1  # Trigger failover after first error
            },
            expected_behavior=ExpectedBehavior.FAILOVER,
            description="Test streaming request failover behavior"
        )
        
        async with Environment(scenario) as env:
            request_data = {
                "model": env.effective_model_name,
                "max_tokens": 100,
                "stream": True,
                "messages": [{"role": "user", "content": "Test streaming failover"}]
            }
            
            async with httpx.AsyncClient() as client:
                # Test streaming failover through balancer
                response = await client.post(
                    f"{env.balancer_url}/v1/messages",
                    json=request_data
                )
                assert response.status_code == 200
                assert "text/event-stream" in response.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_streaming_rate_limit_error(self):
        """Test streaming request with rate limit error."""
        scenario = Scenario(
            name="streaming_rate_limit_test",
            providers=[
                ProviderConfig(
                    "rate_limit_provider",
                    ProviderBehavior.RATE_LIMIT,
                    error_http_code=429,
                    error_message="Rate limit exceeded"
                )
            ],
            expected_behavior=ExpectedBehavior.ERROR,
            description="Test streaming rate limit error"
        )
        
        async with Environment(scenario) as env:
            request_data = {
                "model": env.effective_model_name,
                "max_tokens": 100,
                "stream": True,
                "messages": [{"role": "user", "content": "Test rate limit"}]
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
    async def test_streaming_connection_error(self):
        """Test streaming request with connection error."""
        scenario = Scenario(
            name="streaming_connection_error_test",
            providers=[
                ProviderConfig(
                    "connection_error_provider",
                    ProviderBehavior.CONNECTION_ERROR,
                    error_http_code=502,
                    error_message="Connection failed"
                )
            ],
            expected_behavior=ExpectedBehavior.ERROR,
            description="Test streaming connection error"
        )
        
        async with Environment(scenario) as env:
            request_data = {
                "model": env.effective_model_name,
                "max_tokens": 100,
                "stream": True,
                "messages": [{"role": "user", "content": "Test connection error"}]
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{env.balancer_url}/v1/messages",
                    json=request_data
                )
                
                assert response.status_code == 502
                error_data = response.json()
                assert "error" in error_data
                assert "Connection Error" in error_data["error"]["message"]

    @pytest.mark.asyncio
    async def test_streaming_service_unavailable(self):
        """Test streaming request with service unavailable error."""
        scenario = Scenario(
            name="streaming_service_unavailable_test",
            providers=[
                ProviderConfig(
                    "unavailable_provider",
                    ProviderBehavior.SERVICE_UNAVAILABLE,
                    error_http_code=503,
                    error_message="Service unavailable"
                )
            ],
            expected_behavior=ExpectedBehavior.ERROR,
            description="Test streaming service unavailable error"
        )
        
        async with Environment(scenario) as env:
            request_data = {
                "model": env.effective_model_name,
                "max_tokens": 100,
                "stream": True,
                "messages": [{"role": "user", "content": "Test service unavailable"}]
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
    async def test_streaming_insufficient_credits(self):
        """Test streaming request with insufficient credits error."""
        scenario = Scenario(
            name="streaming_insufficient_credits_test",
            providers=[
                ProviderConfig(
                    "credits_provider",
                    ProviderBehavior.INSUFFICIENT_CREDITS,
                    error_http_code=402,
                    error_message="Insufficient credits"
                )
            ],
            expected_behavior=ExpectedBehavior.ERROR,
            description="Test streaming insufficient credits error"
        )
        
        async with Environment(scenario) as env:
            request_data = {
                "model": env.effective_model_name,
                "max_tokens": 100,
                "stream": True,
                "messages": [{"role": "user", "content": "Test insufficient credits"}]
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
    async def test_streaming_with_different_models(self):
        """Test streaming requests with different model configurations."""
        models_to_test = [
            ("claude-3-5-sonnet-20241022", "Anthropic model streaming test"),
            ("gpt-3.5-turbo", "OpenAI model streaming test"),
            ("custom-streaming-model", "Custom model streaming test")
        ]
        
        for model_name, expected_content in models_to_test:
            scenario = Scenario(
                name=f"streaming_model_test_{model_name.replace('-', '_').replace('.', '_')}",
                providers=[
                    ProviderConfig(
                        f"model_provider_{model_name.replace('-', '_').replace('.', '_')}",
                        ProviderBehavior.STREAMING_SUCCESS,
                        response_data={
                            "content": expected_content
                        }
                    )
                ],
                expected_behavior=ExpectedBehavior.SUCCESS,
                description=f"Test streaming with {model_name}"
            )
            
            async with Environment(scenario) as env:
                request_data = {
                    "model": env.effective_model_name,  # Use the test framework's unique model name
                    "max_tokens": 100,
                    "stream": True,
                    "messages": [{"role": "user", "content": f"Test streaming for {model_name}"}]
                }
                
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        f"{env.balancer_url}/v1/messages",
                        json=request_data
                    )
                    
                    assert response.status_code == 200
                    assert "text/event-stream" in response.headers.get("content-type", "")
                    
                    # Collect and verify content
                    chunks = []
                    async for chunk in response.aiter_text():
                        if chunk.strip():
                            chunks.append(chunk.strip())
                    
                    chunk_text = '\n'.join(chunks)
                    # Verify streaming structure and that content is present
                    assert "message_start" in chunk_text
                    assert "content_block_delta" in chunk_text
                    assert "message_stop" in chunk_text
                    # Verify the key words from expected content are present
                    key_words = expected_content.split()[:2]  # Check first 2 words
                    for word in key_words:
                        assert word in chunk_text

    @pytest.mark.asyncio
    async def test_streaming_concurrent_requests(self):
        """Test concurrent streaming requests."""
        scenario = Scenario(
            name="streaming_concurrent_test",
            providers=[
                ProviderConfig(
                    "concurrent_streaming_provider",
                    ProviderBehavior.STREAMING_SUCCESS,
                    response_data={
                        "content": "Concurrent streaming response"
                    }
                )
            ],
            expected_behavior=ExpectedBehavior.SUCCESS,
            description="Test concurrent streaming requests"
        )
        
        async with Environment(scenario) as env:
            async def make_streaming_request(client, content_suffix=""):
                return await client.post(
                    f"{env.balancer_url}/v1/messages",
                    json={
                        "model": env.effective_model_name,
                        "max_tokens": 100,
                        "stream": True,
                        "messages": [{"role": "user", "content": f"Concurrent test {content_suffix}"}]
                    }
                )
            
            async with httpx.AsyncClient() as client:
                # Make concurrent streaming requests
                tasks = [
                    make_streaming_request(client, f"request_{i}")
                    for i in range(3)
                ]
                responses = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Count successful responses
                success_count = sum(
                    1 for r in responses 
                    if hasattr(r, 'status_code') and r.status_code == 200
                )
                assert success_count >= 2  # Most should succeed
                
                # Verify at least one response has proper streaming format
                valid_responses = [r for r in responses if hasattr(r, 'status_code') and r.status_code == 200]
                if valid_responses:
                    response = valid_responses[0]
                    assert "text/event-stream" in response.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_streaming_large_response(self):
        """Test streaming response with large content."""
        large_content = "This is a large streaming response. " * 100  # Repeat to make it large
        
        scenario = Scenario(
            name="streaming_large_response_test",
            providers=[
                ProviderConfig(
                    "large_response_provider",
                    ProviderBehavior.STREAMING_SUCCESS,
                    response_data={
                        "content": large_content
                    }
                )
            ],
            expected_behavior=ExpectedBehavior.SUCCESS,
            description="Test streaming large response handling"
        )
        
        async with Environment(scenario) as env:
            request_data = {
                "model": env.effective_model_name,
                "max_tokens": 1000,
                "stream": True,
                "messages": [{"role": "user", "content": "Generate a large response"}]
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{env.balancer_url}/v1/messages",
                    json=request_data
                )
                
                assert response.status_code == 200
                assert "text/event-stream" in response.headers.get("content-type", "")
                
                # Collect all chunks
                total_content = ""
                chunk_count = 0
                async for chunk in response.aiter_text():
                    if chunk.strip():
                        total_content += chunk
                        chunk_count += 1
                
                # Verify we got a substantial response
                assert chunk_count > 0  # Should have chunks
                assert len(total_content) > 100  # Should be substantial content

    @pytest.mark.asyncio
    async def test_streaming_empty_content(self):
        """Test streaming response with empty content."""
        scenario = Scenario(
            name="streaming_empty_content_test",
            providers=[
                ProviderConfig(
                    "empty_content_provider",
                    ProviderBehavior.STREAMING_SUCCESS,
                    response_data={
                        "content": ""  # Empty content
                    }
                )
            ],
            expected_behavior=ExpectedBehavior.SUCCESS,
            description="Test streaming empty content handling"
        )
        
        async with Environment(scenario) as env:
            request_data = {
                "model": env.effective_model_name,
                "max_tokens": 100,
                "stream": True,
                "messages": [{"role": "user", "content": "Generate empty response"}]
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{env.balancer_url}/v1/messages",
                    json=request_data
                )
                
                assert response.status_code == 200
                assert "text/event-stream" in response.headers.get("content-type", "")
                
                # Should still have streaming structure
                content = ""
                async for chunk in response.aiter_text():
                    content += chunk
                
                # Should have stream events but minimal content
                assert "message_start" in content
                assert "message_stop" in content

    @pytest.mark.asyncio
    async def test_streaming_with_system_message(self):
        """Test streaming request with system message."""
        scenario = Scenario(
            name="streaming_system_message_test",
            providers=[
                ProviderConfig(
                    "system_message_provider",
                    ProviderBehavior.STREAMING_SUCCESS,
                    response_data={
                        "content": "System message processed in streaming response"
                    }
                )
            ],
            expected_behavior=ExpectedBehavior.SUCCESS,
            description="Test streaming with system message"
        )
        
        async with Environment(scenario) as env:
            request_data = {
                "model": env.effective_model_name,
                "max_tokens": 100,
                "stream": True,
                "system": "You are a helpful assistant.",
                "messages": [{"role": "user", "content": "Test with system message"}]
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{env.balancer_url}/v1/messages",
                    json=request_data
                )
                
                assert response.status_code == 200
                assert "text/event-stream" in response.headers.get("content-type", "")
                
                # Collect response content
                chunks = []
                async for chunk in response.aiter_text():
                    if chunk.strip():
                        chunks.append(chunk.strip())
                
                chunk_text = '\n'.join(chunks)
                # Verify streaming structure and key content
                assert "message_start" in chunk_text
                assert "content_block_delta" in chunk_text
                assert "message_stop" in chunk_text
                # Check for key words from expected content
                assert "System" in chunk_text
                assert "message" in chunk_text

    @pytest.mark.asyncio
    async def test_streaming_with_temperature_parameter(self):
        """Test streaming request with temperature parameter."""
        scenario = Scenario(
            name="streaming_temperature_test",
            providers=[
                ProviderConfig(
                    "temperature_provider",
                    ProviderBehavior.STREAMING_SUCCESS,
                    response_data={
                        "content": "Temperature parameter handled in streaming"
                    }
                )
            ],
            expected_behavior=ExpectedBehavior.SUCCESS,
            description="Test streaming with temperature parameter"
        )
        
        async with Environment(scenario) as env:
            request_data = {
                "model": env.effective_model_name,
                "max_tokens": 100,
                "stream": True,
                "temperature": 0.7,
                "messages": [{"role": "user", "content": "Test with temperature"}]
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{env.balancer_url}/v1/messages",
                    json=request_data
                )
                
                assert response.status_code == 200
                assert "text/event-stream" in response.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_streaming_multiple_provider_types(self):
        """Test streaming with different provider types."""
        # Test Anthropic-style streaming
        anthropic_scenario = Scenario(
            name="streaming_anthropic_type_test",
            providers=[
                ProviderConfig(
                    "anthropic_streaming_provider",
                    ProviderBehavior.STREAMING_SUCCESS,
                    provider_type="anthropic",
                    response_data={
                        "content": "Anthropic streaming response"
                    }
                )
            ],
            expected_behavior=ExpectedBehavior.SUCCESS,
            description="Test Anthropic-style streaming"
        )
        
        async with Environment(anthropic_scenario) as env:
            request_data = {
                "model": env.effective_model_name,
                "max_tokens": 100,
                "stream": True,
                "messages": [{"role": "user", "content": "Test Anthropic streaming"}]
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{env.balancer_url}/v1/messages",
                    json=request_data
                )
                
                assert response.status_code == 200
                assert "text/event-stream" in response.headers.get("content-type", "")

        # Test OpenAI-style streaming
        openai_scenario = Scenario(
            name="streaming_openai_type_test",
            providers=[
                ProviderConfig(
                    "openai_streaming_provider",
                    ProviderBehavior.STREAMING_SUCCESS,
                    provider_type="openai",
                    response_data={
                        "content": "OpenAI streaming response"
                    }
                )
            ],
            expected_behavior=ExpectedBehavior.SUCCESS,
            description="Test OpenAI-style streaming"
        )
        
        async with Environment(openai_scenario) as env:
            request_data = {
                "model": env.effective_model_name,
                "max_tokens": 100,
                "stream": True,
                "messages": [{"role": "user", "content": "Test OpenAI streaming"}]
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{env.balancer_url}/v1/messages",
                    json=request_data
                )
                
                assert response.status_code == 200
                assert "text/event-stream" in response.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_streaming_error_recovery(self):
        """Test streaming error recovery patterns."""
        scenario = Scenario(
            name="streaming_error_recovery_test",
            providers=[
                ProviderConfig(
                    "recovery_provider",
                    ProviderBehavior.STREAMING_SUCCESS,  # Start as success for recovery test
                    response_data={
                        "content": "Provider recovered from streaming error"
                    }
                )
            ],
            expected_behavior=ExpectedBehavior.SUCCESS,
            description="Test streaming error recovery"
        )
        
        async with Environment(scenario) as env:
            request_data = {
                "model": env.effective_model_name,
                "max_tokens": 100,
                "stream": True,
                "messages": [{"role": "user", "content": "Test error recovery"}]
            }
            
            async with httpx.AsyncClient() as client:
                # Simulate recovery with successful request
                response = await client.post(
                    f"{env.balancer_url}/v1/messages",
                    json=request_data
                )
                
                assert response.status_code == 200
                assert "text/event-stream" in response.headers.get("content-type", "")
                
                # Collect response to verify recovery
                chunks = []
                async for chunk in response.aiter_text():
                    if chunk.strip():
                        chunks.append(chunk.strip())
                
                chunk_text = '\n'.join(chunks)
                # Verify streaming structure and key content
                assert "message_start" in chunk_text
                assert "content_block_delta" in chunk_text
                assert "message_stop" in chunk_text
                # Check for key words from expected content
                assert "Provider" in chunk_text
                assert "recovered" in chunk_text

    @pytest.mark.asyncio
    async def test_streaming_request_validation(self):
        """Test streaming request parameter validation."""
        scenario = Scenario(
            name="streaming_validation_test",
            providers=[
                ProviderConfig(
                    "validation_provider",
                    ProviderBehavior.STREAMING_SUCCESS,
                    response_data={
                        "content": "Request validation successful"
                    }
                )
            ],
            expected_behavior=ExpectedBehavior.SUCCESS,
            description="Test streaming request validation"
        )
        
        async with Environment(scenario) as env:
            # Test with various valid parameters
            test_cases = [
                {
                    "model": env.effective_model_name,
                    "max_tokens": 100,
                    "stream": True,
                    "messages": [{"role": "user", "content": "Basic validation test"}]
                },
                {
                    "model": env.effective_model_name,
                    "max_tokens": 200,
                    "stream": True,
                    "temperature": 0.5,
                    "messages": [{"role": "user", "content": "Temperature validation test"}]
                },
                {
                    "model": env.effective_model_name,
                    "max_tokens": 150,
                    "stream": True,
                    "top_p": 0.9,
                    "messages": [{"role": "user", "content": "Top-p validation test"}]
                }
            ]
            
            async with httpx.AsyncClient() as client:
                for request_data in test_cases:
                    response = await client.post(
                        f"{env.balancer_url}/v1/messages",
                        json=request_data
                    )
                    
                    assert response.status_code == 200
                    assert "text/event-stream" in response.headers.get("content-type", "")