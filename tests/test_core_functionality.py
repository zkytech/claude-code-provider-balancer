"""Simplified tests for core functionality with working mocks."""

import pytest
import respx
from httpx import AsyncClient, Response

from conftest import async_client, claude_headers


class TestCoreRequests:
    """Simplified tests for core request functionality."""

    @pytest.mark.asyncio
    async def test_streaming_request_success(self, async_client: AsyncClient, claude_headers):
        """Test successful streaming request."""
        request_data = {
            "model": "claude-3-5-sonnet-20241022",
            "max_tokens": 100,
            "stream": True,
            "messages": [{"role": "user", "content": "Hello"}]
        }
        
        with respx.mock:
            # Mock the AICODE provider from config.yaml
            async def mock_stream():
                yield b'event: message_start\ndata: {"type": "message_start"}\n\n'
                yield b'event: content_block_delta\ndata: {"type": "content_block_delta", "delta": {"text": "Hello"}}\n\n'
                yield b'event: message_stop\ndata: {"type": "message_stop"}\n\n'
            
            respx.post("https://api.aicodemirror.com/api/claudecode/v1/messages").mock(
                return_value=Response(
                    200,
                    headers={"content-type": "text/event-stream"},
                    stream=mock_stream()
                )
            )
            
            response = await async_client.post(
                "/v1/messages",
                json=request_data,
                headers=claude_headers
            )
            
            assert response.status_code == 200
            assert "text/event-stream" in response.headers.get("content-type", "")
            
            # Collect chunks
            chunks = []
            async for chunk in response.aiter_text():
                if chunk.strip():
                    chunks.append(chunk)
            
            assert len(chunks) > 0

    @pytest.mark.asyncio
    async def test_non_streaming_request_success(self, async_client: AsyncClient, claude_headers):
        """Test successful non-streaming request."""
        request_data = {
            "model": "claude-3-5-sonnet-20241022",
            "max_tokens": 100,
            "messages": [{"role": "user", "content": "Hello"}]
        }
        
        with respx.mock:
            # Mock the AICODE provider
            respx.post("https://api.aicodemirror.com/api/claudecode/v1/messages").mock(
                return_value=Response(200, json={
                    "id": "msg_test",
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "text", "text": "Hello! How can I help you today?"}],
                    "model": "claude-3-5-sonnet-20241022",
                    "stop_reason": "end_turn",
                    "usage": {"input_tokens": 10, "output_tokens": 15}
                })
            )
            
            response = await async_client.post(
                "/v1/messages",
                json=request_data,
                headers=claude_headers
            )
            
            assert response.status_code == 200
            data = response.json()
            assert "id" in data
            assert "content" in data
            assert len(data["content"]) > 0

    @pytest.mark.asyncio
    async def test_provider_error_handling(self, async_client: AsyncClient, claude_headers):
        """Test provider error handling."""
        request_data = {
            "model": "claude-3-5-sonnet-20241022",
            "max_tokens": 100,
            "messages": [{"role": "user", "content": "Test error"}]
        }
        
        with respx.mock:
            # Mock provider returning error
            respx.post("https://api.aicodemirror.com/api/claudecode/v1/messages").mock(
                return_value=Response(500, json={
                    "type": "error",
                    "error": {"type": "internal_server_error", "message": "Server error"}
                })
            )
            
            response = await async_client.post(
                "/v1/messages",
                json=request_data,
                headers=claude_headers
            )
            
            # Should return error status
            assert response.status_code == 500

    @pytest.mark.asyncio
    async def test_health_endpoint(self, async_client: AsyncClient):
        """Test health check endpoint."""
        response = await async_client.get("/")  # Root endpoint
        
        assert response.status_code == 200
        data = response.json()
        assert "status" in data

    @pytest.mark.asyncio
    async def test_providers_endpoint(self, async_client: AsyncClient):
        """Test providers status endpoint.""" 
        response = await async_client.get("/providers")
        
        assert response.status_code == 200
        data = response.json()
        assert "providers" in data
        assert "healthy_providers" in data  # Use correct field name