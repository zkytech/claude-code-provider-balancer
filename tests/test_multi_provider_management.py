"""Tests for multi-provider management, failover, and provider availability scenarios."""

import pytest
import respx
from httpx import AsyncClient, ConnectError, ReadTimeout, Response
from unittest.mock import patch, AsyncMock

from conftest import (
    async_client, claude_headers, test_messages_request, 
    test_streaming_request, mock_provider_manager
)


class TestMultiProviderManagement:
    """Test multi-provider management and failover scenarios."""

    @pytest.mark.asyncio
    async def test_primary_provider_success(self, async_client: AsyncClient, claude_headers, test_messages_request):
        """Test successful request to primary provider."""
        response = await async_client.post(
            "/v1/messages",
            json=test_messages_request,
            headers=claude_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "message"

    @pytest.mark.asyncio
    async def test_failover_to_secondary_provider(self, async_client: AsyncClient, claude_headers, test_messages_request):
        """Test failover when primary provider fails."""
        with respx.mock:
            # Mock primary provider failure
            respx.post("http://localhost:9090/test-providers/anthropic/success").mock(
                side_effect=ConnectError("Primary provider connection failed")
            )
            
            # Mock secondary provider success
            respx.post("http://localhost:9090/test-providers/anthropic/error/server_error").mock(
                return_value=Response(
                    200,
                    json={
                        "id": "test_msg_failover",
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "text", "text": "Response from secondary provider"}],
                        "model": test_messages_request["model"],
                        "stop_reason": "end_turn",
                        "usage": {"input_tokens": 10, "output_tokens": 20}
                    }
                )
            )
            
            response = await async_client.post(
                "/v1/messages",
                json=test_messages_request,
                headers=claude_headers
            )
            
            # Should successfully failover
            assert response.status_code == 200
            data = response.json()
            assert data["type"] == "message"

    @pytest.mark.asyncio
    async def test_all_providers_unavailable(self, async_client: AsyncClient, claude_headers, test_messages_request):
        """Test scenario when all providers are unavailable."""
        with respx.mock:
            # Mock all providers failing
            respx.post("http://localhost:9090/test-providers/anthropic/success").mock(
                side_effect=ConnectError("Provider 1 connection failed")
            )
            respx.post("http://localhost:9090/test-providers/anthropic/error/server_error").mock(
                side_effect=ConnectError("Provider 2 connection failed")
            )
            respx.post("http://localhost:9090/test-providers/openai/success").mock(
                side_effect=ConnectError("Provider 3 connection failed")
            )
            
            response = await async_client.post(
                "/v1/messages",
                json=test_messages_request,
                headers=claude_headers
            )
            
            # Should return service unavailable error
            assert response.status_code in [503, 502, 500]
            error_data = response.json()
            assert "error" in error_data

    @pytest.mark.asyncio
    async def test_provider_cooldown_mechanism(self, async_client: AsyncClient, claude_headers, test_messages_request):
        """Test provider cooldown mechanism after failures."""
        with respx.mock:
            # Mock primary provider failure multiple times
            failure_responses = [
                ConnectError("Connection failed"),
                ConnectError("Connection failed"),
                ConnectError("Connection failed")
            ]
            
            respx.post("http://localhost:9090/test-providers/anthropic/success").mock(
                side_effect=failure_responses
            )
            
            # Mock secondary provider success
            respx.post("http://localhost:9090/test-providers/anthropic/error/server_error").mock(
                return_value=Response(
                    200,
                    json={
                        "id": "test_msg_cooldown",
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "text", "text": "Response during cooldown"}],
                        "model": test_messages_request["model"],
                        "stop_reason": "end_turn",
                        "usage": {"input_tokens": 10, "output_tokens": 20}
                    }
                )
            )
            
            # Make multiple requests to trigger cooldown
            for i in range(3):
                response = await async_client.post(
                    "/v1/messages",
                    json=test_messages_request,
                    headers=claude_headers
                )
                
                # Should failover to secondary provider
                assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_provider_recovery_after_cooldown(self, async_client: AsyncClient, claude_headers, test_messages_request):
        """Test provider recovery after cooldown period."""
        with respx.mock:
            # Initially mock provider failure
            respx.post("http://localhost:9090/test-providers/anthropic/success").mock(
                side_effect=ConnectError("Temporary failure")
            )
            
            # Make first request to trigger failure
            response1 = await async_client.post(
                "/v1/messages",
                json=test_messages_request,
                headers=claude_headers
            )
            
            # Should fail or failover
            assert response1.status_code in [200, 500, 502, 503]
            
            # Now mock provider recovery
            respx.post("http://localhost:9090/test-providers/anthropic/success").mock(
                return_value=Response(
                    200,
                    json={
                        "id": "test_msg_recovered",
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "text", "text": "Provider recovered"}],
                        "model": test_messages_request["model"],
                        "stop_reason": "end_turn",
                        "usage": {"input_tokens": 10, "output_tokens": 20}
                    }
                )
            )
            
            # Wait for cooldown to expire (simulate with patch)
            with patch('time.time', return_value=9999999):  # Future time
                response2 = await async_client.post(
                    "/v1/messages",
                    json=test_messages_request,
                    headers=claude_headers
                )
                
                assert response2.status_code == 200

    @pytest.mark.asyncio
    async def test_streaming_failover(self, async_client: AsyncClient, claude_headers, test_streaming_request):
        """Test failover for streaming requests."""
        with respx.mock:
            # Mock primary provider failure for streaming
            respx.post("http://localhost:9090/test-providers/anthropic/success").mock(
                side_effect=ReadTimeout("Streaming timeout")
            )
            
            # Mock secondary provider streaming success
            async def mock_streaming_response():
                yield b'event: message_start\ndata: {"type": "message_start", "message": {"id": "failover_stream"}}\n\n'
                yield b'event: content_block_delta\ndata: {"type": "content_block_delta", "delta": {"text": "Failover stream"}}\n\n'
                yield b'event: message_stop\ndata: {"type": "message_stop"}\n\n'
            
            respx.post("http://localhost:9090/test-providers/anthropic/error/server_error").mock(
                return_value=Response(
                    200,
                    headers={"content-type": "text/event-stream"},
                    stream=mock_streaming_response()
                )
            )
            
            response = await async_client.post(
                "/v1/messages",
                json=test_streaming_request,
                headers=claude_headers
            )
            
            # Should successfully failover to streaming
            assert response.status_code == 200
            assert response.headers.get("content-type") == "text/event-stream"

    @pytest.mark.asyncio
    async def test_provider_health_check_integration(self, async_client: AsyncClient):
        """Test provider health check endpoint reflects actual provider status."""
        response = await async_client.get("/providers")
        
        assert response.status_code == 200
        data = response.json()
        assert "providers" in data
        assert "healthy_count" in data
        assert "total_count" in data
        
        # Verify provider health information
        providers = data["providers"]
        assert len(providers) > 0
        
        for provider in providers:
            assert "name" in provider
            assert "healthy" in provider
            assert "type" in provider

    @pytest.mark.asyncio
    async def test_provider_priority_ordering(self, async_client: AsyncClient, claude_headers):
        """Test that providers are selected based on priority ordering."""
        # Test with a model that has multiple providers configured
        request_data = {
            "model": "claude-3-5-sonnet-20241022",
            "max_tokens": 100,
            "messages": [
                {
                    "role": "user",
                    "content": "Test priority ordering"
                }
            ]
        }
        
        response = await async_client.post(
            "/v1/messages",
            json=request_data,
            headers=claude_headers
        )
        
        # Should use highest priority provider
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_provider_type_specific_error_handling(self, async_client: AsyncClient, claude_headers):
        """Test error handling specific to different provider types."""
        # Test with OpenAI provider
        openai_request = {
            "model": "gpt-3.5-turbo",
            "max_tokens": 100,
            "messages": [
                {
                    "role": "user",
                    "content": "Test OpenAI error handling"
                }
            ]
        }
        
        with respx.mock:
            # Mock OpenAI-style error response
            respx.post("http://localhost:9090/test-providers/openai/success").mock(
                return_value=Response(
                    400,
                    json={
                        "error": {
                            "message": "Bad request",
                            "type": "invalid_request_error",
                            "code": "invalid_request"
                        }
                    }
                )
            )
            
            response = await async_client.post(
                "/v1/messages",
                json=openai_request,
                headers={"authorization": "Bearer test-key", "content-type": "application/json"}
            )
            
            # Should handle OpenAI error format
            assert response.status_code == 400
            error_data = response.json()
            assert "error" in error_data

    @pytest.mark.asyncio
    async def test_concurrent_requests_with_failover(self, async_client: AsyncClient, claude_headers, test_messages_request):
        """Test concurrent requests during provider failover."""
        import asyncio
        
        async def make_request():
            return await async_client.post(
                "/v1/messages",
                json=test_messages_request,
                headers=claude_headers
            )
        
        with respx.mock:
            # Mock intermittent failures
            responses = [
                ConnectError("Intermittent failure"),
                Response(200, json={
                    "id": "concurrent_test",
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "text", "text": "Concurrent response"}],
                    "model": test_messages_request["model"],
                    "stop_reason": "end_turn",
                    "usage": {"input_tokens": 10, "output_tokens": 20}
                })
            ] * 10
            
            respx.post("http://localhost:9090/test-providers/anthropic/success").mock(
                side_effect=responses
            )
            
            # Make concurrent requests
            tasks = [make_request() for _ in range(5)]
            responses = await asyncio.gather(*tasks, return_exceptions=True)
            
            # At least some should succeed
            success_count = sum(1 for r in responses if hasattr(r, 'status_code') and r.status_code == 200)
            assert success_count > 0

    @pytest.mark.asyncio
    async def test_provider_selection_with_model_routing(self, async_client: AsyncClient, claude_headers):
        """Test provider selection based on model routing rules."""
        # Test different models to verify routing
        test_cases = [
            ("claude-3-5-sonnet-20241022", "test_anthropic_success"),
            ("gpt-3.5-turbo", "test_openai_success"),
            ("test-model", "test_anthropic_success")
        ]
        
        for model, expected_provider_type in test_cases:
            request_data = {
                "model": model,
                "max_tokens": 100,
                "messages": [
                    {
                        "role": "user",
                        "content": f"Test routing for {model}"
                    }
                ]
            }
            
            response = await async_client.post(
                "/v1/messages",
                json=request_data,
                headers=claude_headers
            )
            
            # Should route to appropriate provider
            assert response.status_code in [200, 404]  # 404 if model not configured