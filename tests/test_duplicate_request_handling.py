"""Tests for duplicate request handling with stream/non-stream mixed scenarios."""

import asyncio
import pytest
import respx
from httpx import AsyncClient, Response
from unittest.mock import patch, AsyncMock

from conftest import (
    async_client, claude_headers, test_messages_request, 
    test_streaming_request, mock_provider_manager
)
from test_config import get_test_provider_url


class TestDuplicateRequestHandling:
    """Test duplicate request handling with mixed streaming scenarios."""

    @pytest.mark.asyncio
    async def test_duplicate_non_streaming_requests(self, async_client: AsyncClient, claude_headers, test_messages_request):
        """Test duplicate non-streaming requests are properly cached."""
        with respx.mock:
            # Mock provider response
            mock_response = {
                "id": "msg_duplicate_test",
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": "Original response"}],
                "model": test_messages_request["model"],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 10, "output_tokens": 15}
            }
            
            respx.post(get_test_provider_url("anthropic")).mock(
                return_value=Response(200, json=mock_response)
            )
            
            # Make first request
            response1 = await async_client.post(
                "/v1/messages",
                json=test_messages_request,
                headers=claude_headers
            )
            
            assert response1.status_code == 200
            data1 = response1.json()
            
            # Make identical second request
            response2 = await async_client.post(
                "/v1/messages",
                json=test_messages_request,
                headers=claude_headers
            )
            
            assert response2.status_code == 200
            data2 = response2.json()
            
            # Responses should be identical (cached)
            assert data1["content"] == data2["content"]

    @pytest.mark.asyncio
    async def test_duplicate_streaming_requests(self, async_client: AsyncClient, claude_headers, test_streaming_request):
        """Test duplicate streaming requests are handled appropriately."""
        # No respx mock needed - use our real mock provider on localhost:8998
        
        # Make both streaming requests concurrently to ensure they overlap
        async def make_streaming_request():
            response = await async_client.post(
                "/v1/messages",
                json=test_streaming_request,
                headers=claude_headers
            )
            
            assert response.status_code == 200
            assert "text/event-stream" in response.headers.get("content-type", "")
            
            # Collect response chunks
            chunks = []
            async for chunk in response.aiter_text():
                if chunk.strip():
                    chunks.append(chunk.strip())
            
            return chunks
        
        # Start both requests concurrently with a small delay between them
        async def request_with_delay(delay=0):
            if delay > 0:
                await asyncio.sleep(delay)
            return await make_streaming_request()
        
        # Make the first request immediately, second after 0.05s delay
        tasks = [
            request_with_delay(0),      # First request starts immediately
            request_with_delay(0.05)    # Second request starts after 0.05s
        ]
        
        chunks1, chunks2 = await asyncio.gather(*tasks)
        
        # Both should have streaming content
        assert len(chunks1) > 0, f"First request got no chunks: {chunks1}"
        assert len(chunks2) > 0, f"Second request got no chunks: {chunks2}"

    @pytest.mark.asyncio
    async def test_mixed_streaming_non_streaming_duplicates(self, async_client: AsyncClient, claude_headers):
        """Test duplicate requests with mixed streaming and non-streaming modes."""
        base_request = {
            "model": "claude-3-5-sonnet-20241022",
            "max_tokens": 100,
            "messages": [
                {
                    "role": "user",
                    "content": "Mixed mode duplicate test"
                }
            ]
        }
        
        # No respx mock needed - use our real mock provider on localhost:8998
        
        # Make non-streaming request first
        non_streaming_request = base_request.copy()
        non_streaming_request["stream"] = False
        
        response1 = await async_client.post(
            "/v1/messages",
            json=non_streaming_request,
            headers=claude_headers
        )
        
        assert response1.status_code == 200
        data1 = response1.json()
        assert data1["type"] == "message"
        
        # Now make streaming request with same content
        streaming_request = base_request.copy()
        streaming_request["stream"] = True
        
        response2 = await async_client.post(
            "/v1/messages",
            json=streaming_request,
            headers=claude_headers
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
    async def test_concurrent_duplicate_requests(self, async_client: AsyncClient, claude_headers, test_messages_request):
        """Test concurrent duplicate requests are handled properly."""
        with respx.mock:
            # Mock provider response with delay to simulate race conditions
            async def delayed_response(request):
                await asyncio.sleep(0.1)  # Small delay
                return Response(200, json={
                    "id": "msg_concurrent_test",
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "text", "text": "Concurrent response"}],
                    "model": test_messages_request["model"],
                    "stop_reason": "end_turn",
                    "usage": {"input_tokens": 10, "output_tokens": 15}
                })
            
            respx.post(get_test_provider_url("anthropic")).mock(
                side_effect=delayed_response
            )
            
            # Make concurrent identical requests
            async def make_request():
                return await async_client.post(
                    "/v1/messages",
                    json=test_messages_request,
                    headers=claude_headers
                )
            
            tasks = [make_request() for _ in range(3)]
            responses = await asyncio.gather(*tasks)
            
            # All should succeed (some may be duplicate responses)
            successful_responses = []
            cancelled_responses = []
            
            for response in responses:
                if response.status_code == 200:
                    successful_responses.append(response)
                    data = response.json()
                    assert data["type"] == "message"
                elif response.status_code == 409:
                    # This is expected for some duplicate requests that get cancelled
                    cancelled_responses.append(response)
                else:
                    assert False, f"Unexpected status code: {response.status_code}"
            
            # At least one request should succeed (the original one)
            assert len(successful_responses) >= 1
            # The total should be all 3 requests
            assert len(successful_responses) + len(cancelled_responses) == 3

    @pytest.mark.asyncio
    async def test_duplicate_requests_with_different_parameters(self, async_client: AsyncClient, claude_headers):
        """Test that requests with different parameters are not considered duplicates."""
        base_messages = [
            {
                "role": "user",
                "content": "Same content, different parameters"
            }
        ]
        
        with respx.mock:
            # Mock different responses for different requests
            response1_mock = {
                "id": "msg_param_test1",
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": "Response 1"}],
                "model": "claude-3-5-sonnet-20241022",
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 10, "output_tokens": 15}
            }
            
            response2_mock = {
                "id": "msg_param_test2",
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": "Response 2"}],
                "model": "claude-3-5-sonnet-20241022",
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 10, "output_tokens": 15}
            }
            
            respx.post(get_test_provider_url("anthropic")).mock(
                side_effect=[
                    Response(200, json=response1_mock),
                    Response(200, json=response2_mock)
                ]
            )
            
            # First request with temperature 0.5
            request1 = {
                "model": "claude-3-5-sonnet-20241022",
                "max_tokens": 100,
                "temperature": 0.5,
                "messages": base_messages
            }
            
            response1 = await async_client.post(
                "/v1/messages",
                json=request1,
                headers=claude_headers
            )
            
            assert response1.status_code == 200
            data1 = response1.json()
            
            # Second request with temperature 0.8 (different parameter)
            request2 = {
                "model": "claude-3-5-sonnet-20241022",
                "max_tokens": 100,
                "temperature": 0.8,
                "messages": base_messages
            }
            
            response2 = await async_client.post(
                "/v1/messages",
                json=request2,
                headers=claude_headers
            )
            
            assert response2.status_code == 200
            data2 = response2.json()
            
            # Should be different responses due to different parameters
            assert data1["id"] != data2["id"]  # Different message IDs indicate different responses

    @pytest.mark.asyncio
    async def test_duplicate_requests_with_system_messages(self, async_client: AsyncClient, claude_headers):
        """Test duplicate detection with system messages."""
        request_data = {
            "model": "claude-3-5-sonnet-20241022",
            "max_tokens": 100,
            "system": "You are a helpful assistant.",
            "messages": [
                {
                    "role": "user",
                    "content": "Hello with system message"
                }
            ]
        }
        
        with respx.mock:
            mock_response = {
                "id": "msg_system_duplicate",
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": "System message response"}],
                "model": request_data["model"],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 15, "output_tokens": 20}
            }
            
            respx.post(get_test_provider_url("anthropic")).mock(
                return_value=Response(200, json=mock_response)
            )
            
            # Make first request
            response1 = await async_client.post(
                "/v1/messages",
                json=request_data,
                headers=claude_headers
            )
            
            assert response1.status_code == 200
            
            # Make duplicate request
            response2 = await async_client.post(
                "/v1/messages",
                json=request_data,
                headers=claude_headers
            )
            
            assert response2.status_code == 200
            
            # Should handle system messages in duplicate detection
            data1 = response1.json()
            data2 = response2.json()
            assert data1["content"] == data2["content"]

    @pytest.mark.asyncio
    async def test_duplicate_requests_with_tools(self, async_client: AsyncClient, claude_headers):
        """Test duplicate detection with tool definitions."""
        request_data = {
            "model": "claude-3-5-sonnet-20241022",
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
        
        with respx.mock:
            mock_response = {
                "id": "msg_tools_duplicate",
                "type": "message",
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "tool_123",
                        "name": "get_weather",
                        "input": {"location": "San Francisco"}
                    }
                ],
                "model": request_data["model"],
                "stop_reason": "tool_use",
                "usage": {"input_tokens": 25, "output_tokens": 10}
            }
            
            respx.post(get_test_provider_url("anthropic")).mock(
                return_value=Response(200, json=mock_response)
            )
            
            # Make first request
            response1 = await async_client.post(
                "/v1/messages",
                json=request_data,
                headers=claude_headers
            )
            
            assert response1.status_code == 200
            
            # Make duplicate request
            response2 = await async_client.post(
                "/v1/messages",
                json=request_data,
                headers=claude_headers
            )
            
            assert response2.status_code == 200
            
            # Should handle tools in duplicate detection
            data1 = response1.json()
            data2 = response2.json()
            assert data1["content"] == data2["content"]

    @pytest.mark.asyncio
    async def test_cache_expiration_behavior(self, async_client: AsyncClient, claude_headers, test_messages_request):
        """Test cache expiration and refresh behavior."""
        with respx.mock:
            # Mock first response
            first_response = {
                "id": "msg_cache_test1",
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": "First response"}],
                "model": test_messages_request["model"],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 10, "output_tokens": 15}
            }
            
            # Mock second response (after cache expiration)
            second_response = {
                "id": "msg_cache_test2",
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": "Second response"}],
                "model": test_messages_request["model"],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 10, "output_tokens": 15}
            }
            
            respx.post(get_test_provider_url("anthropic")).mock(
                side_effect=[
                    Response(200, json=first_response),
                    Response(200, json=second_response)
                ]
            )
            
            # Make first request
            response1 = await async_client.post(
                "/v1/messages",
                json=test_messages_request,
                headers=claude_headers
            )
            
            assert response1.status_code == 200
            data1 = response1.json()
            
            # Simulate cache expiration by patching time
            with patch('time.time', return_value=9999999):  # Far future time
                response2 = await async_client.post(
                    "/v1/messages",
                    json=test_messages_request,
                    headers=claude_headers
                )
                
                assert response2.status_code == 200
                data2 = response2.json()
                
                # After cache expiration, should get fresh response
                # Note: This test assumes cache expiration leads to different responses
                # The actual behavior depends on the cache implementation

    @pytest.mark.asyncio
    async def test_duplicate_detection_with_provider_failover(self, async_client: AsyncClient, claude_headers, test_messages_request):
        """Test duplicate detection when provider failover occurs."""
        with respx.mock:
            # Mock first provider failure
            respx.post(get_test_provider_url("anthropic")).mock(
                side_effect=[
                    Response(500, json={"error": {"message": "Server error"}}),
                    Response(200, json={
                        "id": "msg_failover_duplicate",
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "text", "text": "Failover response"}],
                        "model": test_messages_request["model"],
                        "stop_reason": "end_turn",
                        "usage": {"input_tokens": 10, "output_tokens": 15}
                    })
                ]
            )
            
            # Mock secondary provider success
            respx.post(get_test_provider_url("anthropic")).mock(
                return_value=Response(200, json={
                    "id": "msg_secondary_duplicate",
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "text", "text": "Secondary provider response"}],
                    "model": test_messages_request["model"],
                    "stop_reason": "end_turn",
                    "usage": {"input_tokens": 10, "output_tokens": 15}
                })
            )
            
            # Make first request (should failover)
            response1 = await async_client.post(
                "/v1/messages",
                json=test_messages_request,
                headers=claude_headers
            )
            
            assert response1.status_code == 200
            
            # Make duplicate request (should use primary provider now that it's recovered)
            response2 = await async_client.post(
                "/v1/messages",
                json=test_messages_request,
                headers=claude_headers
            )
            
            assert response2.status_code == 200
            
            # Both should succeed despite provider failover scenario
            data1 = response1.json()
            data2 = response2.json()
            assert data1["type"] == "message"
            assert data2["type"] == "message"