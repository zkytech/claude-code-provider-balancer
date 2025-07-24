"""Tests for non-streaming request handling."""

import pytest
import respx
from httpx import AsyncClient, ConnectError, ReadTimeout, Response

from conftest import (
    async_client, claude_headers, test_messages_request, 
    test_openai_request, mock_provider_manager
)


class TestNonStreamingRequests:
    """Test non-streaming request handling scenarios."""

    @pytest.mark.asyncio
    async def test_successful_non_streaming_response(self, async_client: AsyncClient, claude_headers, test_messages_request):
        """Test successful non-streaming response handling."""
        with respx.mock:
            # Mock successful response
            mock_response = {
                "id": "msg_test_success", 
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": "Hello! This is a test response."}],
                "model": "claude-3-5-sonnet-20241022",
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 10, "output_tokens": 8}
            }
            respx.post("http://localhost:9090/test-providers/anthropic/v1/messages").mock(
                return_value=Response(200, json=mock_response)
            )
            
            response = await async_client.post(
                "/v1/messages",
                json=test_messages_request,
                headers=claude_headers
            )
        
        assert response.status_code == 200
        assert response.headers.get("content-type") == "application/json"
        
        data = response.json()
        assert "id" in data
        assert "type" in data
        assert data["type"] == "message"
        assert "role" in data
        assert data["role"] == "assistant"
        assert "content" in data
        assert len(data["content"]) > 0
        assert "usage" in data
        assert "input_tokens" in data["usage"]
        assert "output_tokens" in data["usage"]

    @pytest.mark.asyncio
    async def test_non_streaming_with_system_message(self, async_client: AsyncClient, claude_headers):
        """Test non-streaming request with system message."""
        request_data = {
            "model": "claude-3-5-sonnet-20241022",
            "max_tokens": 100,
            "system": "You are a helpful assistant.",
            "messages": [
                {
                    "role": "user",
                    "content": "Hello, how are you?"
                }
            ]
        }
        
        with respx.mock:
            # Mock successful response
            mock_response = {
                "id": "msg_system_test", 
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": "Hello! I'm doing well, thank you for asking."}],
                "model": "claude-3-5-sonnet-20241022",
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 15, "output_tokens": 12}
            }
            respx.post("http://localhost:9090/test-providers/anthropic/v1/messages").mock(
                return_value=Response(200, json=mock_response)
            )
            
            response = await async_client.post(
                "/v1/messages",
                json=request_data,
                headers=claude_headers
            )
        
        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "message"
        assert len(data["content"]) > 0

    @pytest.mark.asyncio
    async def test_non_streaming_with_temperature(self, async_client: AsyncClient, claude_headers, test_messages_request):
        """Test non-streaming request with temperature parameter."""
        request_data = test_messages_request.copy()
        request_data["temperature"] = 0.7
        
        with respx.mock:
            # Mock successful response with temperature
            mock_response = {
                "id": "msg_temp_test",
                "type": "message",
                "role": "assistant", 
                "content": [{"type": "text", "text": "Response with temperature 0.7"}],
                "model": "claude-3-5-sonnet-20241022",
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 10, "output_tokens": 8}
            }
            respx.post("http://localhost:9090/test-providers/anthropic/v1/messages").mock(
                return_value=Response(200, json=mock_response)
            )
            
            response = await async_client.post(
                "/v1/messages",
                json=request_data,
                headers=claude_headers
            )
        
        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "message"

    @pytest.mark.asyncio
    async def test_non_streaming_provider_error_500(self, async_client: AsyncClient, claude_headers, test_messages_request):
        """Test non-streaming request with provider returning 500 error."""
        with respx.mock:
            # Mock provider to return 500 error
            respx.post("http://localhost:9090/test-providers/anthropic/v1/messages").mock(
                return_value=Response(
                    500,
                    json={
                        "type": "error",
                        "error": {
                            "type": "internal_server_error",
                            "message": "Internal server error"
                        }
                    }
                )
            )
            
            response = await async_client.post(
                "/v1/messages",
                json=test_messages_request,
                headers=claude_headers
            )
            
            assert response.status_code == 500
            error_data = response.json()
            assert "error" in error_data

    @pytest.mark.asyncio
    async def test_non_streaming_provider_error_401(self, async_client: AsyncClient, claude_headers, test_messages_request):
        """Test non-streaming request with authentication error."""
        with respx.mock:
            # Mock both providers to return 401 error to test failover
            error_response = {
                "type": "error",
                "error": {
                    "type": "authentication_error",
                    "message": "Invalid API key"
                }
            }
            # Mock all possible provider URLs that might be tried
            respx.post("http://localhost:9090/test-providers/anthropic/v1/messages").mock(
                return_value=Response(401, json=error_response)
            )
            # Mock any other routes as well
            respx.route().mock(
                return_value=Response(401, json=error_response)
            )
            
            response = await async_client.post(
                "/v1/messages",
                json=test_messages_request,
                headers=claude_headers
            )
            
            # When all providers fail, the system should return 500
            assert response.status_code == 500
            error_data = response.json()
            assert "error" in error_data
            # The error message should indicate all providers failed
            assert "unable to process requests" in error_data["error"]["message"]

    @pytest.mark.asyncio
    async def test_non_streaming_provider_error_429(self, async_client: AsyncClient, claude_headers, test_messages_request):
        """Test non-streaming request with rate limit error."""
        with respx.mock:
            # Mock both providers to return 429 error to test failover
            error_response = {
                "type": "error",
                "error": {
                    "type": "rate_limit_error",
                    "message": "Rate limit exceeded"
                }
            }
            # Mock all possible provider URLs that might be tried
            respx.post("http://localhost:9090/test-providers/anthropic/v1/messages").mock(
                return_value=Response(429, json=error_response, headers={"retry-after": "60"})
            )
            # Mock any other routes as well
            respx.route().mock(
                return_value=Response(429, json=error_response, headers={"retry-after": "60"})
            )
            
            response = await async_client.post(
                "/v1/messages",
                json=test_messages_request,
                headers=claude_headers
            )
            
            # When all providers fail, the system should return 500
            assert response.status_code == 500
            error_data = response.json()
            assert "error" in error_data
            # The error message should indicate all providers failed
            assert "unable to process requests" in error_data["error"]["message"]

    @pytest.mark.asyncio
    async def test_non_streaming_connection_error(self, async_client: AsyncClient, claude_headers, test_messages_request):
        """Test non-streaming request with connection error."""
        with respx.mock:
            # Mock connection error
            respx.post("http://localhost:9090/test-providers/anthropic/v1/messages").mock(
                side_effect=ConnectError("Connection failed")
            )
            
            response = await async_client.post(
                "/v1/messages",
                json=test_messages_request,
                headers=claude_headers
            )
            
            # Should failover or return appropriate error
            assert response.status_code in [500, 502, 503]

    @pytest.mark.asyncio
    async def test_non_streaming_timeout_error(self, async_client: AsyncClient, claude_headers, test_messages_request):
        """Test non-streaming request with timeout."""
        with respx.mock:
            # Mock timeout error
            respx.post("http://localhost:9090/test-providers/anthropic/v1/messages").mock(
                side_effect=ReadTimeout("Request timeout")
            )
            
            response = await async_client.post(
                "/v1/messages",
                json=test_messages_request,
                headers=claude_headers
            )
            
            # Should handle timeout gracefully
            assert response.status_code in [504, 500]

    @pytest.mark.asyncio
    async def test_non_streaming_invalid_json_response(self, async_client: AsyncClient, claude_headers, test_messages_request):
        """Test non-streaming request with invalid JSON response."""
        with respx.mock:
            # Mock response with invalid JSON
            respx.post("http://localhost:9090/test-providers/anthropic/v1/messages").mock(
                return_value=Response(200, content="invalid json response")
            )
            
            response = await async_client.post(
                "/v1/messages",
                json=test_messages_request,
                headers=claude_headers
            )
            
            # Should handle invalid JSON gracefully
            assert response.status_code in [500, 502]

    @pytest.mark.asyncio
    async def test_non_streaming_empty_response(self, async_client: AsyncClient, claude_headers, test_messages_request):
        """Test non-streaming request with empty response."""
        with respx.mock:
            # Mock empty response
            respx.post("http://localhost:9090/test-providers/anthropic/v1/messages").mock(
                return_value=Response(200, content="")
            )
            
            response = await async_client.post(
                "/v1/messages",
                json=test_messages_request,
                headers=claude_headers
            )
            
            # Should handle empty response appropriately
            assert response.status_code in [500, 502]

    @pytest.mark.asyncio
    async def test_non_streaming_200_with_error_content(self, async_client: AsyncClient, claude_headers, test_messages_request):
        """Test non-streaming request that returns 200 but contains error in content."""
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
                json=test_messages_request,
                headers=claude_headers
            )
            
            # Should detect and handle error content
            assert response.status_code in [400, 500]
            error_data = response.json()
            assert "error" in error_data

    @pytest.mark.asyncio
    async def test_non_streaming_openai_format_request(self, async_client: AsyncClient):
        """Test non-streaming request with OpenAI format."""
        openai_headers = {
            "authorization": "Bearer test-key",
            "content-type": "application/json"
        }
        
        openai_request = {
            "model": "gpt-3.5-turbo",
            "max_tokens": 100,
            "messages": [
                {
                    "role": "user",
                    "content": "Hello from OpenAI format test"
                }
            ]
        }
        
        with respx.mock:
            # Mock OpenAI provider response
            mock_response = {
                "id": "chatcmpl-test-openai",
                "object": "chat.completion",
                "created": 1677652288,
                "model": "gpt-3.5-turbo",
                "choices": [{
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "Hello! This is an OpenAI format response."
                    },
                    "finish_reason": "stop"
                }],
                "usage": {
                    "prompt_tokens": 9,
                    "completion_tokens": 9,
                    "total_tokens": 18
                }
            }
            # Mock the OpenAI chat completions endpoint
            respx.post("http://localhost:9090/test-providers/openai/v1/chat/completions").mock(
                return_value=Response(200, json=mock_response)
            )
            # Mock any other routes that might be tried
            respx.route().mock(
                return_value=Response(200, json=mock_response)
            )
        
            response = await async_client.post(
                "/v1/messages",
                json=openai_request,
                headers=openai_headers
            )
        
        assert response.status_code == 200
        data = response.json()
        # Should be converted to Anthropic format
        assert "id" in data
        assert "content" in data

    @pytest.mark.asyncio
    async def test_non_streaming_with_tools(self, async_client: AsyncClient, claude_headers):
        """Test non-streaming request with tools."""
        request_data = {
            "model": "claude-3-5-sonnet-20241022",
            "max_tokens": 100,
            "messages": [
                {
                    "role": "user",
                    "content": "What's the weather like?"
                }
            ],
            "tools": [
                {
                    "name": "get_weather",
                    "description": "Get current weather for a location",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "location": {
                                "type": "string",
                                "description": "City name"
                            }
                        },
                        "required": ["location"]
                    }
                }
            ]
        }
        
        with respx.mock:
            # Mock successful response with tool use
            mock_response = {
                "id": "msg_tools_test", 
                "type": "message",
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_weather_123",
                        "name": "get_weather",
                        "input": {"location": "San Francisco"}
                    }
                ],
                "model": "claude-3-5-sonnet-20241022",
                "stop_reason": "tool_use",
                "stop_sequence": None,
                "usage": {"input_tokens": 25, "output_tokens": 15}
            }
            respx.post("http://localhost:9090/test-providers/anthropic/v1/messages").mock(
                return_value=Response(200, json=mock_response)
            )
            
            response = await async_client.post(
                "/v1/messages",
                json=request_data,
                headers=claude_headers
            )
        
        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "message"

    @pytest.mark.asyncio
    async def test_non_streaming_invalid_model(self, async_client: AsyncClient, claude_headers):
        """Test non-streaming request with invalid model."""
        request_data = {
            "model": "invalid-model-name",
            "max_tokens": 100,
            "messages": [
                {
                    "role": "user",
                    "content": "Hello"
                }
            ]
        }
        
        response = await async_client.post(
            "/v1/messages",
            json=request_data,
            headers=claude_headers
        )
        
        # Should handle invalid model gracefully
        assert response.status_code in [400, 404]

    @pytest.mark.asyncio
    async def test_non_streaming_missing_required_fields(self, async_client: AsyncClient, claude_headers):
        """Test non-streaming request with missing required fields."""
        # Missing max_tokens
        request_data = {
            "model": "claude-3-5-sonnet-20241022",
            "messages": [
                {
                    "role": "user",
                    "content": "Hello"
                }
            ]
        }
        
        response = await async_client.post(
            "/v1/messages",
            json=request_data,
            headers=claude_headers
        )
        
        assert response.status_code == 400  # Validation error