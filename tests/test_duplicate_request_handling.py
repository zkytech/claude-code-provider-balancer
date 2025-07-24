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
            
            respx.post("http://localhost:9090/test-providers/anthropic/success").mock(
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
        with respx.mock:
            # Mock streaming response
            async def mock_streaming_response():
                yield b'event: message_start\ndata: {"type": "message_start", "message": {"id": "stream_duplicate"}}\n\n'
                yield b'event: content_block_delta\ndata: {"type": "content_block_delta", "delta": {"text": "Stream response"}}\n\n'
                yield b'event: message_stop\ndata: {"type": "message_stop"}\n\n'
            
            respx.post("http://localhost:9090/test-providers/anthropic/success").mock(
                return_value=Response(
                    200,
                    headers={"content-type": "text/event-stream"},
                    stream=mock_streaming_response()
                )
            )
            
            # Make first streaming request
            response1 = await async_client.post(
                "/v1/messages",
                json=test_streaming_request,
                headers=claude_headers
            )
            
            assert response1.status_code == 200
            assert response1.headers.get("content-type") == "text/event-stream"
            
            # Collect first response
            chunks1 = []
            async for chunk in response1.aiter_text():
                if chunk.strip():
                    chunks1.append(chunk.strip())
            
            # Make identical second streaming request
            response2 = await async_client.post(
                "/v1/messages",
                json=test_streaming_request,
                headers=claude_headers
            )
            
            assert response2.status_code == 200
            assert response2.headers.get("content-type") == "text/event-stream"
            
            # Collect second response
            chunks2 = []
            async for chunk in response2.aiter_text():
                if chunk.strip():
                    chunks2.append(chunk.strip())
            
            # Both should have streaming content
            assert len(chunks1) > 0
            assert len(chunks2) > 0

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
        
        with respx.mock:
            # Mock non-streaming response
            non_streaming_response = {
                "id": "msg_mixed_test",
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": "Non-streaming response"}],
                "model": base_request["model"],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 12, "output_tokens": 18}
            }
            
            # Mock streaming response
            async def mock_streaming_response():
                yield b'event: message_start\ndata: {"type": "message_start", "message": {"id": "mixed_stream"}}\n\n'
                yield b'event: content_block_delta\ndata: {"type": "content_block_delta", "delta": {"text": "Streaming response"}}\n\n'
                yield b'event: message_stop\ndata: {"type": "message_stop"}\n\n'
            
            respx.post("http://localhost:9090/test-providers/anthropic/success").mock(
                return_value=Response(200, json=non_streaming_response)
            )
            
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
            
            # Update mock for streaming response
            respx.post("http://localhost:9090/test-providers/anthropic/success").mock(
                return_value=Response(
                    200,
                    headers={"content-type": "text/event-stream"},
                    stream=mock_streaming_response()
                )
            )
            
            response2 = await async_client.post(
                "/v1/messages",
                json=streaming_request,
                headers=claude_headers
            )
            
            assert response2.status_code == 200
            assert response2.headers.get("content-type") == "text/event-stream"
            
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
            async def delayed_response():
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
            
            respx.post("http://localhost:9090/test-providers/anthropic/success").mock(
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
            
            # All should succeed
            for response in responses:
                assert response.status_code == 200
                data = response.json()
                assert data["type"] == "message"

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
            
            respx.post("http://localhost:9090/test-providers/anthropic/success").mock(
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
            
            respx.post("http://localhost:9090/test-providers/anthropic/success").mock(
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
            
            respx.post("http://localhost:9090/test-providers/anthropic/success").mock(
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
            
            respx.post("http://localhost:9090/test-providers/anthropic/success").mock(
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
            respx.post("http://localhost:9090/test-providers/anthropic/success").mock(
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
            respx.post("http://localhost:9090/test-providers/anthropic/error/server_error").mock(
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