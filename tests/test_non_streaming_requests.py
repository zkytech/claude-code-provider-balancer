"""Tests for non-streaming request handling."""

import pytest
from httpx import AsyncClient

from conftest import (
    async_client, claude_headers, test_messages_request, 
    test_openai_request, mock_provider_manager
)


class TestNonStreamingRequests:
    """Test non-streaming request handling scenarios."""

    @pytest.mark.asyncio
    async def test_successful_non_streaming_response(self, async_client: AsyncClient, claude_headers):
        """Test successful non-streaming response handling - uses dedicated test provider."""
        # Use dedicated non-streaming success test model
        test_request = {
            "model": "non-streaming-success-test",
            "max_tokens": 100,
            "messages": [{"role": "user", "content": "Hello, test message"}]
        }
        
        # Use dedicated success provider - no respx.mock needed
        response = await async_client.post(
            "/v1/messages",
            json=test_request,
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
        """Test non-streaming request with system message - uses dedicated test provider."""
        request_data = {
            "model": "non-streaming-system-message-test",
            "max_tokens": 100,
            "system": "You are a helpful assistant.",
            "messages": [
                {
                    "role": "user",
                    "content": "Hello, how are you?"
                }
            ]
        }
        
        # Use dedicated system message test provider - no respx.mock needed
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
    async def test_non_streaming_with_temperature(self, async_client: AsyncClient, claude_headers):
        """Test non-streaming request with temperature parameter - uses dedicated test provider."""
        # Use dedicated temperature test model with temperature parameter
        request_data = {
            "model": "non-streaming-temperature-test",
            "max_tokens": 100,
            "temperature": 0.7,
            "messages": [{"role": "user", "content": "Test temperature"}]
        }
        
        # Use dedicated temperature test provider - no respx.mock needed
        response = await async_client.post(
            "/v1/messages",
            json=request_data,
            headers=claude_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "message"

    @pytest.mark.asyncio
    async def test_non_streaming_provider_error_500(self, async_client: AsyncClient, claude_headers):
        """Test non-streaming request with provider returning 500 error - uses dedicated test provider."""
        # Use dedicated 500 error test model
        test_request = {
            "model": "non-streaming-error-500-test",
            "max_tokens": 100,
            "messages": [{"role": "user", "content": "Test 500 error"}]
        }
        
        # Use dedicated 500 error test provider - no respx.mock needed
        response = await async_client.post(
            "/v1/messages",
            json=test_request,
            headers=claude_headers
        )
        
        assert response.status_code == 500
        error_data = response.json()
        assert "error" in error_data
        assert "Internal server error for testing" in error_data["error"]["message"]

    @pytest.mark.asyncio
    async def test_non_streaming_provider_error_401(self, async_client: AsyncClient, claude_headers):
        """Test non-streaming request with authentication error - uses dedicated test provider."""
        # Use dedicated 401 error test model
        test_request = {
            "model": "non-streaming-error-401-test",
            "max_tokens": 100,
            "messages": [{"role": "user", "content": "Test 401 error"}]
        }
        
        # Use dedicated 401 error test provider - no respx.mock needed
        response = await async_client.post(
            "/v1/messages",
            json=test_request,
            headers=claude_headers
        )
        
        # Should return 401 directly from provider
        assert response.status_code == 401
        error_data = response.json()
        assert "error" in error_data
        assert "Invalid API key" in error_data["error"]["message"]

    @pytest.mark.asyncio
    async def test_non_streaming_provider_error_429(self, async_client: AsyncClient, claude_headers):
        """Test non-streaming request with rate limit error - uses dedicated test provider."""
        # Use dedicated 429 error test model
        test_request = {
            "model": "non-streaming-error-429-test",
            "max_tokens": 100,
            "messages": [{"role": "user", "content": "Test 429 error"}]
        }
        
        # Use dedicated 429 error test provider - no respx.mock needed
        response = await async_client.post(
            "/v1/messages",
            json=test_request,
            headers=claude_headers
        )
        
        # Should return 429 directly from provider
        assert response.status_code == 429
        error_data = response.json()
        assert "error" in error_data
        assert "Rate limit exceeded" in error_data["error"]["message"]

    @pytest.mark.asyncio
    async def test_non_streaming_connection_error(self, async_client: AsyncClient, claude_headers):
        """Test non-streaming request with connection error - uses dedicated test provider."""
        # Use dedicated connection error test model
        test_request = {
            "model": "non-streaming-connection-error-test",
            "max_tokens": 100,
            "messages": [{"role": "user", "content": "Test connection error"}]
        }
        
        # Use dedicated connection error test provider - returns 503 Service Unavailable
        response = await async_client.post(
            "/v1/messages",
            json=test_request,
            headers=claude_headers
        )
        
        # Should return appropriate error from dedicated provider
        assert response.status_code == 503

    @pytest.mark.asyncio
    async def test_non_streaming_timeout_error(self, async_client: AsyncClient, claude_headers):
        """Test non-streaming request with timeout - uses dedicated test provider."""
        # Use dedicated timeout error test model
        test_request = {
            "model": "non-streaming-timeout-error-test",
            "max_tokens": 100,
            "messages": [{"role": "user", "content": "Test timeout error"}]
        }
        
        # Use dedicated timeout error test provider - returns 408 Request Timeout
        response = await async_client.post(
            "/v1/messages",
            json=test_request,
            headers=claude_headers
        )
        
        # Should handle timeout gracefully
        assert response.status_code == 408
        error_data = response.json()
        assert "error" in error_data
        assert "Request timeout" in error_data["error"]["message"]

    @pytest.mark.asyncio
    async def test_non_streaming_invalid_json_response(self, async_client: AsyncClient, claude_headers):
        """Test non-streaming request with invalid JSON response - uses dedicated test provider."""
        # Use dedicated invalid JSON test model
        test_request = {
            "model": "non-streaming-invalid-json-test",
            "max_tokens": 100,
            "messages": [{"role": "user", "content": "Test invalid JSON"}]
        }
        
        # Use dedicated invalid JSON test provider - returns invalid JSON as plain text
        response = await async_client.post(
            "/v1/messages",
            json=test_request,
            headers=claude_headers
        )
        
        # Should handle invalid JSON gracefully - provider itself returns 200 with invalid JSON,
        # but the balancer should detect this and return an error
        assert response.status_code in [500, 502]

    @pytest.mark.asyncio
    async def test_non_streaming_empty_response(self, async_client: AsyncClient, claude_headers):
        """Test non-streaming request with empty response - uses dedicated test provider."""
        # Use dedicated empty response test model
        test_request = {
            "model": "non-streaming-empty-response-test",
            "max_tokens": 100,
            "messages": [{"role": "user", "content": "Test empty response"}]
        }
        
        # Use dedicated empty response test provider - returns empty JSON object
        response = await async_client.post(
            "/v1/messages",
            json=test_request,
            headers=claude_headers
        )
        
        # Should handle empty response appropriately - provider returns 200 but empty,
        # balancer should detect this and return an error
        assert response.status_code in [500, 502]

    @pytest.mark.asyncio
    async def test_non_streaming_200_with_error_content(self, async_client: AsyncClient, claude_headers):
        """Test non-streaming request that returns 200 but contains error in content - uses dedicated test provider."""
        # Use dedicated 200 error content test model
        test_request = {
            "model": "non-streaming-200-error-content-test",
            "max_tokens": 100,
            "messages": [{"role": "user", "content": "Test 200 with error content"}]
        }
        
        # Use dedicated 200 error content test provider - returns 200 status but error content
        # First request - should return 200 but error count 1/2 (below threshold)
        response1 = await async_client.post(
            "/v1/messages",
            json=test_request,
            headers=claude_headers
        )
        assert response1.status_code == 200  # First error, below threshold, returns 200
        
        # Second request - should trigger unhealthy threshold and return error status
        response2 = await async_client.post(
            "/v1/messages",
            json=test_request,
            headers=claude_headers
        )
        
        # Should detect and handle error content - provider marked unhealthy after reaching threshold
        # When all providers are marked unhealthy, should return 503 Service Unavailable
        assert response2.status_code == 503
        error_data = response2.json()
        assert "error" in error_data

    @pytest.mark.asyncio
    async def test_non_streaming_openai_format_request(self, async_client: AsyncClient):
        """Test non-streaming request with OpenAI format - uses dedicated test provider."""
        openai_headers = {
            "authorization": "Bearer test-key",
            "content-type": "application/json"
        }
        
        # Use dedicated OpenAI format test model
        openai_request = {
            "model": "non-streaming-openai-format-test",
            "max_tokens": 100,
            "messages": [
                {
                    "role": "user",
                    "content": "Hello from OpenAI format test"
                }
            ]
        }
        
        # Use dedicated OpenAI format test provider - returns OpenAI format response
        response = await async_client.post(
            "/v1/messages",
            json=openai_request,
            headers=openai_headers
        )
        
        # Should work with OpenAI format provider
        assert response.status_code == 200
        data = response.json()
        # Should be converted to Anthropic format by the balancer
        assert "id" in data
        assert "content" in data or "choices" in data  # Allow both formats depending on conversion

    @pytest.mark.asyncio
    async def test_non_streaming_with_tools(self, async_client: AsyncClient, claude_headers):
        """Test non-streaming request with tools - uses dedicated test provider."""
        # Use dedicated tools test model
        request_data = {
            "model": "non-streaming-tools-test",
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
        
        # Use dedicated tools test provider - returns successful response with tool use
        response = await async_client.post(
            "/v1/messages",
            json=request_data,
            headers=claude_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "message"
        # Verify tool use is present in response
        assert "content" in data
        assert len(data["content"]) > 0
        assert data["content"][0]["type"] == "tool_use"

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

    @pytest.mark.asyncio
    async def test_multi_provider_non_streaming_failover_from_json_error(self, async_client: AsyncClient, claude_headers):
        """
        测试场景: 非流式请求中首个provider返回错误，自动failover到健康provider
        预期结果: 首个provider被标记不健康，请求成功failover到第二个provider并返回正常响应
        
        注意: 这测试的是真正的failover（单个请求内的provider切换），针对非流式请求
        使用real mock providers，测试错误计数阈值机制（unhealthy_threshold=2）
        """
        request_data = {
            "model": "non-streaming-failover-test",  # Use the dedicated failover route
            "max_tokens": 1000,
            "messages": [{"role": "user", "content": "Hello"}],
            "stream": False
        }
        
        # First request: error provider returns 500, error count 1/2 (below threshold)
        response1 = await async_client.post(
            "/v1/messages",
            json=request_data,
            headers=claude_headers
        )
        # Should return 500 from first provider (below threshold, no failover yet)
        assert response1.status_code == 500
        
        # Second request: error provider error count reaches 2/2 (threshold), should trigger failover
        response2 = await async_client.post(
            "/v1/messages",
            json=request_data,
            headers=claude_headers
        )
        
        # Should succeed via failover to second provider
        assert response2.status_code == 200
        response_data = response2.json()
        assert "id" in response_data
        assert response_data["type"] == "message"
        assert "content" in response_data
        assert "Failover successful!" in response_data["content"][0]["text"]