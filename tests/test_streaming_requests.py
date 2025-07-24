"""Tests for streaming request handling."""

import asyncio
import json
import pytest
import respx
from httpx import AsyncClient, ConnectError, ReadTimeout, Response
from unittest.mock import patch, AsyncMock

from conftest import (
    test_client, async_client, claude_headers, 
    test_streaming_request, mock_provider_manager
)


class TestStreamingRequests:
    """Test streaming request handling scenarios."""

    @pytest.mark.asyncio
    async def test_successful_streaming_response(self, async_client: AsyncClient, claude_headers, test_streaming_request):
        """Test successful streaming response handling."""
        with respx.mock:
            # Mock the actual provider that's configured in config.yaml
            async def mock_streaming_response():
                yield b'event: message_start\ndata: {"type": "message_start", "message": {"id": "msg_test_success", "type": "message", "role": "assistant", "content": [], "model": "claude-3-5-sonnet-20241022", "stop_reason": null, "stop_sequence": null, "usage": {"input_tokens": 10, "output_tokens": 0}}}\n\n'
                yield b'event: content_block_start\ndata: {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}\n\n'
                yield b'event: content_block_delta\ndata: {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Hello"}}\n\n'
                yield b'event: content_block_delta\ndata: {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": " from"}}\n\n'
                yield b'event: content_block_delta\ndata: {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": " streaming"}}\n\n'
                yield b'event: content_block_stop\ndata: {"type": "content_block_stop", "index": 0}\n\n'
                yield b'event: message_delta\ndata: {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": null}, "usage": {"output_tokens": 3}}\n\n'
                yield b'event: message_stop\ndata: {"type": "message_stop"}\n\n'
            
            respx.post("http://localhost:9090/test-providers/anthropic/v1/messages").mock(
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
            
            assert response.status_code == 200
            assert "text/event-stream" in response.headers.get("content-type", "")
            
            # Collect streaming chunks
            chunks = []
            async for chunk in response.aiter_text():
                if chunk.strip():
                    chunks.append(chunk.strip())
            
            # Verify we got streaming events
            assert len(chunks) > 0
            
            # Verify message_start event
            message_start = next((chunk for chunk in chunks if "message_start" in chunk), None)
            assert message_start is not None
            
            # Verify content_block_delta events
            content_deltas = [chunk for chunk in chunks if "content_block_delta" in chunk]
            assert len(content_deltas) > 0
            
            # Verify message_stop event
            message_stop = next((chunk for chunk in chunks if "message_stop" in chunk), None)
            assert message_stop is not None

    @pytest.mark.asyncio
    async def test_streaming_provider_error(self, async_client: AsyncClient, claude_headers):
        """Test streaming request with provider returning error."""
        request_data = {
            "model": "claude-3-5-sonnet-20241022",
            "max_tokens": 100,  
            "stream": True,
            "messages": [{"role": "user", "content": "Test error"}]
        }
        
        with respx.mock:
            # Mock provider to return 500 error
            respx.post("http://localhost:9090/test-providers/anthropic/v1/messages").mock(
                return_value=Response(500, json={"error": {"message": "Internal server error"}})
            )
            
            response = await async_client.post(
                "/v1/messages",
                json=request_data,
                headers=claude_headers
            )
            
            assert response.status_code == 500
            error_data = response.json()
            assert "error" in error_data

    @pytest.mark.asyncio
    async def test_streaming_connection_error(self, async_client: AsyncClient, claude_headers, test_streaming_request):
        """Test streaming request with connection error."""
        with respx.mock:
            # Mock connection error
            respx.post("http://localhost:9090/test-providers/anthropic/v1/messages").mock(
                side_effect=ConnectError("Connection failed")
            )
            
            response = await async_client.post(
                "/v1/messages", 
                json=test_streaming_request,
                headers=claude_headers
            )
            
            # Should failover or return appropriate error
            assert response.status_code in [500, 502, 503]

    @pytest.mark.asyncio
    async def test_streaming_timeout_error(self, async_client: AsyncClient, claude_headers, test_streaming_request):
        """Test streaming request with timeout."""
        with respx.mock:
            # Mock timeout error
            respx.post("http://localhost:9090/test-providers/anthropic/v1/messages").mock(
                side_effect=ReadTimeout("Request timeout")
            )
            
            response = await async_client.post(
                "/v1/messages",
                json=test_streaming_request,
                headers=claude_headers
            )
            
            # Should handle timeout gracefully
            assert response.status_code in [504, 500]

    @pytest.mark.asyncio
    async def test_streaming_200_with_error_content(self, async_client: AsyncClient, claude_headers, test_streaming_request):
        """Test streaming request that returns 200 but contains error in content."""
        with respx.mock:
            # Mock 200 response with error content
            error_content = {
                "type": "error",
                "error": {
                    "type": "invalid_request_error", 
                    "message": "Invalid request parameters"
                }
            }
            respx.post("http://localhost:9090/test-providers/anthropic/v1/messages").mock(
                return_value=Response(200, json=error_content)
            )
            
            response = await async_client.post(
                "/v1/messages",
                json=test_streaming_request,
                headers=claude_headers
            )
            
            # Should return 200 but detect error content internally
            # The provider is marked as unhealthy but response is still forwarded
            assert response.status_code == 200
            
            # Verify the error content is returned
            content = response.text
            assert "invalid_request_error" in content or "error" in content

    @pytest.mark.asyncio 
    async def test_streaming_200_with_empty_content(self, async_client: AsyncClient, claude_headers, test_streaming_request):
        """Test streaming request that returns 200 but with empty/invalid content."""
        with respx.mock:
            # Mock 200 response with empty content
            respx.post("http://localhost:9090/test-providers/anthropic/v1/messages").mock(
                return_value=Response(200, content="")
            )
            
            response = await async_client.post(
                "/v1/messages",
                json=test_streaming_request,
                headers=claude_headers
            )
            
            # Should return 200 with empty content - provider marked unhealthy but response forwarded
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_streaming_malformed_json_response(self, async_client: AsyncClient, claude_headers, test_streaming_request):
        """Test streaming request with malformed JSON response."""
        with respx.mock:
            # Mock response with malformed JSON
            respx.post("http://localhost:9090/test-providers/anthropic/v1/messages").mock(
                return_value=Response(200, content="{'invalid': json}")
            )
            
            response = await async_client.post(
                "/v1/messages",
                json=test_streaming_request,
                headers=claude_headers
            )
            
            # Should return 200 with malformed content - provider marked unhealthy but response forwarded  
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_streaming_partial_response_interruption(self, async_client: AsyncClient, claude_headers, test_streaming_request):
        """Test streaming request that gets interrupted mid-stream."""
        
        async def mock_interrupted_stream():
            """Mock streaming response that gets interrupted."""
            yield b'event: message_start\ndata: {"type": "message_start"}\n\n'
            yield b'event: content_block_delta\ndata: {"type": "content_block_delta"}\n\n'
            # Simulate interruption - no more data
            
        with respx.mock:
            # Mock interrupted streaming response
            respx.post("http://localhost:9090/test-providers/anthropic/v1/messages").mock(
                return_value=Response(
                    200,
                    headers={"content-type": "text/event-stream"},
                    stream=mock_interrupted_stream()
                )
            )
            
            response = await async_client.post(
                "/v1/messages",
                json=test_streaming_request,
                headers=claude_headers
            )
            
            # Should handle partial streaming response
            assert response.status_code == 200
            
            # Collect what we can from the interrupted stream
            chunks = []
            async for chunk in response.aiter_text():
                if chunk.strip():
                    chunks.append(chunk.strip())
            
            # Should have at least some content before interruption
            assert len(chunks) >= 1

    @pytest.mark.asyncio
    async def test_streaming_with_different_content_types(self, async_client: AsyncClient, claude_headers, test_streaming_request):
        """Test streaming request with unexpected content type."""
        with respx.mock:
            # Mock response with wrong content type
            respx.post("http://localhost:9090/test-providers/anthropic/v1/messages").mock(
                return_value=Response(
                    200,
                    headers={"content-type": "application/json"},
                    json={"message": "This should be streaming but isn't"}
                )
            )
            
            response = await async_client.post(
                "/v1/messages",
                json=test_streaming_request,
                headers=claude_headers
            )
            
            # Should handle content type mismatch
            assert response.status_code in [200, 500]

    @pytest.mark.asyncio
    async def test_streaming_with_rate_limit_error(self, async_client: AsyncClient, claude_headers, test_streaming_request):
        """Test streaming request with rate limit error."""
        with respx.mock:
            # Mock rate limit error
            respx.post("http://localhost:9090/test-providers/anthropic/v1/messages").mock(
                return_value=Response(
                    429,
                    json={
                        "type": "error",
                        "error": {
                            "type": "rate_limit_error",
                            "message": "Rate limit exceeded"
                        }
                    }
                )
            )
            
            response = await async_client.post(
                "/v1/messages",
                json=test_streaming_request,
                headers=claude_headers
            )
            
            # Should handle rate limit error - when all providers fail with 429, system returns 500
            assert response.status_code == 500
            error_data = response.json()
            assert "error" in error_data
            # The error message should indicate all providers failed
            assert "All configured providers" in error_data["error"]["message"]