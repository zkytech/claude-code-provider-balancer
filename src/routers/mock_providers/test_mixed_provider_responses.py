"""
Mock providers specifically for test_mixed_provider_responses.py
Handles mixed OpenAI and Anthropic provider response testing scenarios.
"""

import json
import asyncio
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse, JSONResponse


def create_test_mixed_provider_responses_routes():
    """Create mock provider routes for test_mixed_provider_responses.py"""
    router = APIRouter()

    @router.post("/mixed-openai-success/v1/chat/completions")
    async def mock_mixed_openai_success_provider(request: Request):
        """Mock OpenAI provider that returns success - for mixed provider testing."""
        try:
            request_body = await request.json()
            stream = request_body.get('stream', False)
            
            if not stream:
                # Non-streaming OpenAI response
                return JSONResponse(
                    status_code=200,
                    content={
                        "id": "chatcmpl-mixed-test",
                        "object": "chat.completion",
                        "created": 1677652288,
                        "model": request_body.get("model", "gpt-3.5-turbo"),
                        "choices": [{
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": "Mixed provider OpenAI response - should be converted to Anthropic format"
                            },
                            "finish_reason": "stop"
                        }],
                        "usage": {
                            "prompt_tokens": 15,
                            "completion_tokens": 12,
                            "total_tokens": 27
                        }
                    }
                )
            else:
                # Streaming OpenAI response
                async def generate_openai_stream():
                    chunks = [
                        {
                            "id": "chatcmpl-mixed-stream",
                            "object": "chat.completion.chunk",
                            "created": 1677652288,
                            "model": request_body.get("model", "gpt-3.5-turbo"),
                            "choices": [{
                                "index": 0,
                                "delta": {"role": "assistant", "content": ""},
                                "finish_reason": None
                            }]
                        },
                        {
                            "id": "chatcmpl-mixed-stream",
                            "object": "chat.completion.chunk",
                            "created": 1677652288,
                            "model": request_body.get("model", "gpt-3.5-turbo"),
                            "choices": [{
                                "index": 0,
                                "delta": {"content": "Mixed"},
                                "finish_reason": None
                            }]
                        },
                        {
                            "id": "chatcmpl-mixed-stream",
                            "object": "chat.completion.chunk",
                            "created": 1677652288,
                            "model": request_body.get("model", "gpt-3.5-turbo"),
                            "choices": [{
                                "index": 0,
                                "delta": {"content": " provider"},
                                "finish_reason": None
                            }]
                        },
                        {
                            "id": "chatcmpl-mixed-stream",
                            "object": "chat.completion.chunk",
                            "created": 1677652288,
                            "model": request_body.get("model", "gpt-3.5-turbo"),
                            "choices": [{
                                "index": 0,
                                "delta": {"content": " streaming"},
                                "finish_reason": "stop"
                            }]
                        }
                    ]
                    
                    for chunk in chunks:
                        yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                        await asyncio.sleep(0.05)
                    
                    yield "data: [DONE]\n\n"
                
                return StreamingResponse(
                    generate_openai_stream(),
                    media_type="text/event-stream",
                    headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
                )
                
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={
                    "error": {
                        "message": f"Mixed OpenAI provider error: {str(e)}",
                        "type": "internal_server_error"
                    }
                }
            )

    @router.post("/mixed-openai-success/v1/messages")
    async def mock_mixed_openai_success_anthropic_endpoint(request: Request):
        """Mock OpenAI provider handling Anthropic-format requests - for mixed provider testing."""
        try:
            request_body = await request.json()
            # This endpoint receives Anthropic format but returns OpenAI format
            # (system should convert it back to Anthropic format for the client)
            
            return JSONResponse(
                status_code=200,
                content={
                    "id": "chatcmpl-mixed-anthropic-to-openai",
                    "object": "chat.completion",
                    "created": 1677652288,
                    "model": request_body.get("model", "gpt-3.5-turbo"),
                    "choices": [{
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": "Mixed provider OpenAI response from Anthropic format request"
                        },
                        "finish_reason": "stop"
                    }],
                    "usage": {
                        "prompt_tokens": 20,
                        "completion_tokens": 12,
                        "total_tokens": 32
                    }
                }
            )
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={
                    "error": {
                        "message": f"Mixed OpenAI provider (Anthropic endpoint) error: {str(e)}",
                        "type": "internal_server_error"
                    }
                }
            )

    @router.post("/mixed-anthropic-success/v1/messages")
    async def mock_mixed_anthropic_success_provider(request: Request):
        """Mock Anthropic provider that returns success - for mixed provider testing."""
        try:
            request_body = await request.json()
            
            return JSONResponse(
                status_code=200,
                content={
                    "id": "msg_mixed_test",
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "text",
                            "text": "Mixed provider Anthropic response - works with OpenAI format requests"
                        }
                    ],
                    "model": request_body.get("model", "claude-3-5-sonnet-20241022"),
                    "stop_reason": "end_turn",
                    "usage": {
                        "input_tokens": 15,
                        "output_tokens": 12
                    }
                }
            )
                
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={
                    "type": "error",
                    "error": {
                        "type": "internal_server_error",
                        "message": f"Mixed Anthropic provider error: {str(e)}"
                    }
                }
            )

    @router.post("/mixed-anthropic-success/v1/chat/completions")
    async def mock_mixed_anthropic_success_openai_endpoint(request: Request):
        """Mock Anthropic provider handling OpenAI-format requests - for mixed provider testing."""
        try:
            request_body = await request.json()
            # This endpoint receives OpenAI format but returns Anthropic format  
            # (system should convert it back to OpenAI format for the client)
            
            return JSONResponse(
                status_code=200,
                content={
                    "id": "msg_mixed_openai_to_anthropic",
                    "type": "message", 
                    "role": "assistant",
                    "content": [
                        {
                            "type": "text",
                            "text": "Mixed provider Anthropic response from OpenAI format request"
                        }
                    ],
                    "model": request_body.get("model", "claude-3-5-sonnet-20241022"),
                    "stop_reason": "end_turn",
                    "usage": {
                        "input_tokens": 15,
                        "output_tokens": 12
                    }
                }
            )
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={
                    "error": {
                        "type": "internal_server_error",
                        "message": f"Mixed Anthropic provider (OpenAI endpoint) error: {str(e)}"
                    }
                }
            )

    @router.post("/mixed-openai-error/v1/chat/completions")
    async def mock_mixed_openai_error_provider(request: Request):
        """Mock OpenAI provider that returns error - for mixed provider testing."""
        return JSONResponse(
            status_code=401,
            content={
                "error": {
                    "message": "Invalid API key provided",
                    "type": "invalid_request_error",
                    "param": None,
                    "code": "invalid_api_key"
                }
            }
        )

    @router.post("/mixed-anthropic-error/v1/messages")
    async def mock_mixed_anthropic_error_provider(request: Request):
        """Mock Anthropic provider that returns error - for mixed provider testing."""
        return JSONResponse(
            status_code=500,
            content={
                "type": "error",
                "error": {
                    "type": "internal_server_error",
                    "message": "Mixed provider error for failover testing"
                }
            }
        )

    @router.post("/mixed-failover-error/v1/messages")
    async def mock_mixed_failover_error_provider(request: Request):
        """Mock provider that returns connection error to trigger immediate failover."""
        # This will simulate a connection error that should trigger immediate unhealthy marking
        from fastapi import HTTPException
        raise HTTPException(
            status_code=503,
            detail="connection timeout - Service temporarily unavailable"
        )

    # ========== test_error_format_conversion_openai_to_anthropic ==========
    @router.post("/error-conversion-openai-test/v1/chat/completions")
    async def mock_error_conversion_openai_test_provider(request: Request):
        """专用于test_error_format_conversion_openai_to_anthropic测试"""
        return JSONResponse(
            status_code=401,
            content={
                "error": {
                    "message": "Invalid API key provided",
                    "type": "invalid_request_error",
                    "param": None,
                    "code": "invalid_api_key"
                }
            }
        )

    # ========== test_error_format_conversion_anthropic_to_openai ==========
    @router.post("/error-conversion-anthropic-test/v1/messages")
    async def mock_error_conversion_anthropic_test_provider(request: Request):
        """专用于test_error_format_conversion_anthropic_to_openai测试"""
        return JSONResponse(
            status_code=400,
            content={
                "type": "error",
                "error": {
                    "type": "invalid_request_error",
                    "message": "Invalid request format"
                }
            }
        )

    # ========== test_tool_use_format_conversion ==========
    @router.post("/tool-conversion-test/v1/chat/completions")
    async def mock_tool_conversion_test_provider(request: Request):
        """专用于test_tool_use_format_conversion测试"""
        return JSONResponse(
            status_code=200,
            content={
                "id": "chatcmpl-test-tools",
                "object": "chat.completion",
                "created": 1677652288,
                "model": "gpt-3.5-turbo",
                "choices": [{
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [{
                            "id": "call_123456789",
                            "type": "function",
                            "function": {
                                "name": "get_weather",
                                "arguments": "{\"location\": \"San Francisco\"}"
                            }
                        }]
                    },
                    "finish_reason": "tool_calls"
                }],
                "usage": {
                    "prompt_tokens": 25,
                    "completion_tokens": 15,
                    "total_tokens": 40
                }
            }
        )

    # ========== test_system_message_handling_mixed_providers ==========
    @router.post("/system-message-test/v1/chat/completions")
    async def mock_system_message_test_provider(request: Request):
        """专用于test_system_message_handling_mixed_providers测试"""
        return JSONResponse(
            status_code=200,
            content={
                "id": "chatcmpl-system-test",
                "object": "chat.completion",
                "created": 1677652288,
                "model": "gpt-3.5-turbo",
                "choices": [{
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "Weather forecast process involves collecting data from multiple sources including satellites, weather stations, and atmospheric models."
                    },
                    "finish_reason": "stop"
                }],
                "usage": {
                    "prompt_tokens": 30,
                    "completion_tokens": 20,
                    "total_tokens": 50
                }
            }
        )

    @router.post("/mixed-openai-tools/v1/chat/completions")
    async def mock_mixed_openai_tools_provider(request: Request):
        """Mock OpenAI provider with tool support - for mixed provider testing."""
        try:
            request_body = await request.json()
            
            return JSONResponse(
                status_code=200,
                content={
                    "id": "chatcmpl-tools-test",
                    "object": "chat.completion",
                    "created": 1677652288,
                    "model": request_body.get("model", "gpt-3.5-turbo"),
                    "choices": [{
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [{
                                "id": "call_mixed_test",
                                "type": "function",
                                "function": {
                                    "name": "get_weather",
                                    "arguments": '{"location": "San Francisco"}'
                                }
                            }]
                        },
                        "finish_reason": "tool_calls"
                    }],
                    "usage": {
                        "prompt_tokens": 25,
                        "completion_tokens": 15,
                        "total_tokens": 40
                    }
                }
            )
                
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={
                    "error": {
                        "message": f"Mixed OpenAI tools provider error: {str(e)}",
                        "type": "internal_server_error"
                    }
                }
            )

    return router