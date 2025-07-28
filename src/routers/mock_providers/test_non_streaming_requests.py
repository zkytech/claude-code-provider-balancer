"""
Mock providers specifically for test_non_streaming_requests.py
Handles non-streaming request testing scenarios.
"""

import json
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse


def create_test_non_streaming_requests_routes():
    """Create mock provider routes for test_non_streaming_requests.py"""
    router = APIRouter()

    # ========== test_successful_non_streaming_response ==========
    @router.post("/non-streaming-success-test/v1/messages")
    async def mock_non_streaming_success_test_provider(request: Request):
        """专用于test_successful_non_streaming_response测试"""
        return JSONResponse(
            status_code=200,
            content={
                "id": "msg_test_success", 
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": "Hello! This is a test response."}],
                "model": "claude-3-5-sonnet-20241022",
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 10, "output_tokens": 8}
            }
        )

    # ========== test_non_streaming_with_system_message ==========
    @router.post("/non-streaming-system-message-test/v1/messages")
    async def mock_non_streaming_system_message_test_provider(request: Request):
        """专用于test_non_streaming_with_system_message测试"""
        request_body = await request.json()
        # Verify system message is properly handled
        return JSONResponse(
            status_code=200,
            content={
                "id": "msg_system_test",
                "type": "message", 
                "role": "assistant",
                "content": [{"type": "text", "text": "I understand I am a helpful assistant."}],
                "model": "claude-3-5-sonnet-20241022",
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 15, "output_tokens": 8}
            }
        )

    # ========== test_non_streaming_with_temperature ==========
    @router.post("/non-streaming-temperature-test/v1/messages")
    async def mock_non_streaming_temperature_test_provider(request: Request):
        """专用于test_non_streaming_with_temperature测试"""
        request_body = await request.json()
        # Temperature should be passed through
        return JSONResponse(
            status_code=200,
            content={
                "id": "msg_temp_test",
                "type": "message",
                "role": "assistant", 
                "content": [{"type": "text", "text": f"Temperature setting received: {request_body.get('temperature', 'not set')}"}],
                "model": "claude-3-5-sonnet-20241022",
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 12, "output_tokens": 10}
            }
        )

    # ========== test_non_streaming_provider_error_500 ==========
    @router.post("/non-streaming-error-500-test/v1/messages")
    async def mock_non_streaming_error_500_test_provider(request: Request):
        """专用于test_non_streaming_provider_error_500测试"""
        return JSONResponse(
            status_code=500,
            content={
                "type": "error",
                "error": {
                    "type": "internal_server_error",
                    "message": "Internal server error for testing"
                }
            }
        )

    # ========== test_non_streaming_provider_error_401 ==========
    @router.post("/non-streaming-error-401-test/v1/messages")
    async def mock_non_streaming_error_401_test_provider(request: Request):
        """专用于test_non_streaming_provider_error_401测试"""
        return JSONResponse(
            status_code=401,
            content={
                "type": "error",
                "error": {
                    "type": "authentication_error",
                    "message": "Invalid API key"
                }
            }
        )

    # ========== test_non_streaming_provider_error_429 ==========
    @router.post("/non-streaming-error-429-test/v1/messages")
    async def mock_non_streaming_error_429_test_provider(request: Request):
        """专用于test_non_streaming_provider_error_429测试"""
        return JSONResponse(
            status_code=429,
            content={
                "type": "error",
                "error": {
                    "type": "rate_limit_error",
                    "message": "Rate limit exceeded"
                }
            }
        )

    # ========== test_non_streaming_connection_error ==========
    @router.post("/non-streaming-connection-error-test/v1/messages")
    async def mock_non_streaming_connection_error_test_provider(request: Request):
        """专用于test_non_streaming_connection_error测试"""
        from fastapi import HTTPException
        raise HTTPException(
            status_code=503,
            detail="Connection failed - Service unavailable"
        )

    # ========== test_non_streaming_timeout_error ==========
    @router.post("/non-streaming-timeout-error-test/v1/messages")
    async def mock_non_streaming_timeout_error_test_provider(request: Request):
        """专用于test_non_streaming_timeout_error测试"""
        return JSONResponse(
            status_code=408,
            content={
                "type": "error",
                "error": {
                    "type": "timeout_error",
                    "message": "Request timeout"
                }
            }
        )

    # ========== test_non_streaming_invalid_json_response ==========
    @router.post("/non-streaming-invalid-json-test/v1/messages")
    async def mock_non_streaming_invalid_json_test_provider(request: Request):
        """专用于test_non_streaming_invalid_json_response测试"""
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(
            status_code=200,
            content="{'invalid': json syntax}"
        )

    # ========== test_non_streaming_empty_response ==========
    @router.post("/non-streaming-empty-response-test/v1/messages")
    async def mock_non_streaming_empty_response_test_provider(request: Request):
        """专用于test_non_streaming_empty_response测试 - 返回真正的空响应"""
        from fastapi import Response
        return Response(
            status_code=200,
            content="",
            media_type="application/json"
        )

    # ========== test_non_streaming_200_with_error_content ==========
    @router.post("/non-streaming-200-error-content-test/v1/messages")
    async def mock_non_streaming_200_error_content_test_provider(request: Request):
        """专用于test_non_streaming_200_with_error_content测试"""
        return JSONResponse(
            status_code=200,
            content={
                "type": "error",
                "error": {
                    "type": "invalid_request_error",
                    "message": "Request contains invalid parameters"
                }
            }
        )

    # ========== test_non_streaming_openai_format_request ==========
    @router.post("/non-streaming-openai-format-test/v1/chat/completions")
    async def mock_non_streaming_openai_format_test_provider(request: Request):
        """专用于test_non_streaming_openai_format_request测试"""
        return JSONResponse(
            status_code=200,
            content={
                "id": "chatcmpl-test",
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
                    "prompt_tokens": 12,
                    "completion_tokens": 8,
                    "total_tokens": 20
                }
            }
        )

    # ========== test_non_streaming_with_tools ==========
    @router.post("/non-streaming-tools-test/v1/messages")
    async def mock_non_streaming_tools_test_provider(request: Request):
        """专用于test_non_streaming_with_tools测试"""
        return JSONResponse(
            status_code=200,
            content={
                "id": "msg_tools_test",
                "type": "message",
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_test123",
                        "name": "get_weather",
                        "input": {"location": "San Francisco"}
                    }
                ],
                "model": "claude-3-5-sonnet-20241022", 
                "stop_reason": "tool_use",
                "usage": {"input_tokens": 25, "output_tokens": 15}
            }
        )

    # ========== test_non_streaming_invalid_model ==========
    @router.post("/non-streaming-invalid-model-test/v1/messages")
    async def mock_non_streaming_invalid_model_test_provider(request: Request):
        """专用于test_non_streaming_invalid_model测试"""
        return JSONResponse(
            status_code=400,
            content={
                "type": "error",
                "error": {
                    "type": "invalid_request_error",
                    "message": "Invalid model specified"
                }
            }
        )

    # ========== test_non_streaming_missing_required_fields ==========
    @router.post("/non-streaming-missing-fields-test/v1/messages")
    async def mock_non_streaming_missing_fields_test_provider(request: Request):
        """专用于test_non_streaming_missing_required_fields测试"""
        return JSONResponse(
            status_code=400,
            content={
                "type": "error",
                "error": {
                    "type": "invalid_request_error",
                    "message": "Missing required field: messages"
                }
            }
        )

    # ========== test_multi_provider_non_streaming_failover_from_json_error ==========
    @router.post("/non-streaming-failover-error-test/v1/messages")
    async def mock_non_streaming_failover_error_test_provider(request: Request):
        """专用于test_multi_provider_non_streaming_failover_from_json_error测试中的错误provider"""
        # Return 500 error which is in unhealthy_http_codes, will trigger health check failure
        return JSONResponse(
            status_code=500,
            content={
                "type": "error",
                "error": {
                    "type": "internal_server_error",
                    "message": "Failover test error"
                }
            }
        )

    @router.post("/non-streaming-failover-success-test/v1/messages")
    async def mock_non_streaming_failover_success_test_provider(request: Request):
        """专用于test_multi_provider_non_streaming_failover_from_json_error测试中的成功provider"""
        return JSONResponse(
            status_code=200,
            content={
                "id": "msg_failover_success",
                "type": "message", 
                "role": "assistant",
                "content": [{"type": "text", "text": "Failover successful!"}],
                "model": "claude-3-5-sonnet-20241022",
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 10, "output_tokens": 3}
            }
        )

    return router