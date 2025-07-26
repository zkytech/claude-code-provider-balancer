"""
Mock provider endpoints for testing real streaming behavior.
Creates endpoints that simulate actual Claude provider responses with real delays.
"""

import json
import asyncio
from typing import Dict, Any
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse, JSONResponse


def create_mock_provider_router() -> APIRouter:
    """Create mock provider router for testing streaming."""
    router = APIRouter(prefix="/test-providers", tags=["Mock Providers"])

    @router.post("/anthropic/v1/messages")
    async def mock_anthropic_streaming(request: Request):
        """Mock Anthropic provider with real streaming delays."""
        try:
            # Parse request body
            body = await request.body()
            request_data = json.loads(body.decode('utf-8'))
            
            stream = request_data.get('stream', False)
            max_tokens = request_data.get('max_tokens', 100)
            messages = request_data.get('messages', [])
            
            if not stream:
                # Non-streaming response
                response_content = {
                    "id": "msg_test_12345",
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "text",
                            "text": "这是一个测试响应，用于验证非流式传输。"
                        }
                    ],
                    "model": "claude-3-5-sonnet-20241022",
                    "stop_reason": "end_turn",
                    "stop_sequence": None,
                    "usage": {
                        "input_tokens": 20,
                        "output_tokens": 15
                    }
                }
                return JSONResponse(content=response_content)
            
            # Streaming response with real delays
            async def generate_real_stream():
                """Generate real streaming SSE events with actual delays."""
                
                # Message start event
                start_event = {
                    "type": "message_start",
                    "message": {
                        "id": "msg_test_stream_12345",
                        "type": "message",
                        "role": "assistant",
                        "content": [],
                        "model": "claude-3-5-sonnet-20241022",
                        "stop_reason": None,
                        "stop_sequence": None,
                        "usage": {"input_tokens": 20, "output_tokens": 0}
                    }
                }
                yield f"event: message_start\ndata: {json.dumps(start_event)}\n\n"
                
                # Real delay to simulate network/processing time
                await asyncio.sleep(0.5)  # 500ms initial delay
                
                # Content block start
                content_start = {
                    "type": "content_block_start",
                    "index": 0,
                    "content_block": {"type": "text", "text": ""}
                }
                yield f"event: content_block_start\ndata: {json.dumps(content_start)}\n\n"
                
                # Simulate real text generation with delays between chunks
                text_parts = [
                    "机器学习", "是人工智能", "的一个", "重要分支", "，它使计算机",
                    "能够", "从数据中", "学习", "并做出", "预测", "或决策", "。",
                    "通过", "算法", "和统计", "模型", "，机器", "可以", "识别", "模式",
                    "，改进", "性能", "，而无需", "明确", "编程", "每个", "任务", "。"
                ]
                
                chunk_count = 0
                for i, text_part in enumerate(text_parts):
                    chunk_count += 1
                    
                    # Create content block delta
                    delta_event = {
                        "type": "content_block_delta",
                        "index": 0,
                        "delta": {"type": "text_delta", "text": text_part}
                    }
                    
                    # Significant delay between chunks to make streaming visible
                    if i > 0:
                        await asyncio.sleep(0.3)  # 300ms delay between chunks
                    
                    yield f"event: content_block_delta\ndata: {json.dumps(delta_event)}\n\n"
                
                # Content block stop
                content_stop = {"type": "content_block_stop", "index": 0}
                yield f"event: content_block_stop\ndata: {json.dumps(content_stop)}\n\n"
                
                # Small delay before final message
                await asyncio.sleep(0.02)
                
                # Message stop event
                stop_event = {
                    "type": "message_stop"
                }
                yield f"event: message_stop\ndata: {json.dumps(stop_event)}\n\n"
            
            return StreamingResponse(
                generate_real_stream(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no"
                }
            )
            
        except Exception as e:
            error_response = {
                "type": "error",
                "error": {
                    "type": "internal_server_error",
                    "message": f"Mock provider error: {str(e)}"
                }
            }
            return JSONResponse(content=error_response, status_code=500)

    @router.post("/openai/v1/chat/completions")
    async def mock_openai_streaming(request: Request):
        """Mock OpenAI provider with real streaming delays."""
        try:
            body = await request.body()
            request_data = json.loads(body.decode('utf-8'))
            
            stream = request_data.get('stream', False)
            
            if not stream:
                # Non-streaming OpenAI response
                response_content = {
                    "id": "chatcmpl-test12345",
                    "object": "chat.completion",
                    "created": 1234567890,
                    "model": "gpt-4",
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": "这是OpenAI格式的测试响应。"
                            },
                            "finish_reason": "stop"
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 20,
                        "completion_tokens": 10,
                        "total_tokens": 30
                    }
                }
                return JSONResponse(content=response_content)
            
            # OpenAI streaming format
            async def generate_openai_stream():
                """Generate OpenAI format streaming with real delays."""
                
                text_parts = [
                    "机器学习", "是", "人工智能", "的", "重要", "分支", "，",
                    "它", "使", "计算机", "能够", "从", "数据中", "学习", "。"
                ]
                
                for i, text_part in enumerate(text_parts):
                    chunk = {
                        "id": "chatcmpl-stream12345",
                        "object": "chat.completion.chunk",
                        "created": 1234567890,
                        "model": "gpt-4",
                        "choices": [
                            {
                                "index": 0,
                                "delta": {"content": text_part},
                                "finish_reason": None
                            }
                        ]
                    }
                    
                    # Real delay between chunks
                    if i > 0:
                        await asyncio.sleep(0.05)
                    
                    yield f"data: {json.dumps(chunk)}\n\n"
                
                # Final chunk with finish_reason
                final_chunk = {
                    "id": "chatcmpl-stream12345",
                    "object": "chat.completion.chunk",
                    "created": 1234567890,
                    "model": "gpt-4",
                    "choices": [
                        {
                            "index": 0,
                            "delta": {},
                            "finish_reason": "stop"
                        }
                    ]
                }
                
                await asyncio.sleep(0.02)
                yield f"data: {json.dumps(final_chunk)}\n\n"
                yield "data: [DONE]\n\n"
            
            return StreamingResponse(
                generate_openai_stream(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive"
                }
            )
            
        except Exception as e:
            error_response = {
                "error": {
                    "message": f"Mock OpenAI provider error: {str(e)}",
                    "type": "internal_server_error"
                }
            }
            return JSONResponse(content=error_response, status_code=500)

    @router.post("/test-providers/anthropic-sse-error/v1/messages")
    async def mock_anthropic_sse_error_messages(request: Request):
        """Mock Anthropic provider that returns SSE error for testing duplicate request handling"""
        try:
            # Parse request body for logging
            request_body = await request.json()
            
            # Check if it's a streaming request
            if request_body.get("stream", False):
                # Return SSE error stream
                async def generate_sse_error_stream():
                    # Start with message_start event
                    message_start = {
                        "type": "message_start",
                        "message": {
                            "id": "msg_sse_error_test",
                            "type": "message",
                            "role": "assistant",
                            "content": [],
                            "model": "claude-3-5-sonnet-20241022",
                            "stop_reason": None,
                            "stop_sequence": None,
                            "usage": {"input_tokens": 10, "output_tokens": 0}
                        }
                    }
                    yield f"event: message_start\ndata: {json.dumps(message_start)}\n\n"
                    
                    # Small delay to simulate processing
                    await asyncio.sleep(0.1)
                    
                    # Return SSE error event
                    error_event = {
                        "type": "error",
                        "error": {
                            "type": "invalid_request_error",
                            "message": "Request contains invalid parameters"
                        }
                    }
                    yield f"event: error\ndata: {json.dumps(error_event)}\n\n"
                
                return StreamingResponse(
                    generate_sse_error_stream(),
                    media_type="text/event-stream",
                    headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
                )
            else:
                # Non-streaming request - return JSON error
                return JSONResponse(
                    status_code=400,
                    content={
                        "type": "error",
                        "error": {
                            "type": "invalid_request_error",
                            "message": "Request contains invalid parameters"
                        }
                    }
                )
                
        except Exception as e:
            # Return error response in case of any issues
            return JSONResponse(
                status_code=500,
                content={
                    "type": "error",
                    "error": {
                        "type": "internal_server_error",
                        "message": f"Mock SSE error provider error: {str(e)}"
                    }
                }
            )

    return router