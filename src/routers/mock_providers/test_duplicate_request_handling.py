"""
Mock providers specifically for test_duplicate_request_handling.py
Each endpoint corresponds to the dedicated providers we created for duplicate request testing.
"""

import json
import asyncio
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse, JSONResponse


def create_test_duplicate_request_handling_routes():
    """Create mock provider routes for test_duplicate_request_handling.py"""
    router = APIRouter()

    @router.post("/duplicate-success/v1/messages")
    async def mock_duplicate_success_provider(request: Request):
        """Mock provider that always returns success - for duplicate request testing."""
        try:
            request_body = await request.json()
            stream = request_body.get('stream', False)
            
            if not stream:
                # Non-streaming response
                return JSONResponse(
                    status_code=200,
                    content={
                        "id": "msg_duplicate_success",
                        "type": "message",
                        "role": "assistant",
                        "content": [
                            {
                                "type": "text",
                                "text": "Duplicate test success response"
                            }
                        ],
                        "model": request_body.get("model", "duplicate-test-model"),
                        "stop_reason": "end_turn",
                        "usage": {"input_tokens": 10, "output_tokens": 5}
                    }
                )
            else:
                # Streaming response for duplicate testing
                async def generate_duplicate_stream():
                    # Message start
                    start_event = {
                        "type": "message_start",
                        "message": {
                            "id": "msg_duplicate_stream",
                            "type": "message",
                            "role": "assistant",
                            "content": [],
                            "model": request_body.get("model", "duplicate-test-model"),
                            "stop_reason": None,
                            "usage": {"input_tokens": 10, "output_tokens": 0}
                        }
                    }
                    yield f"event: message_start\ndata: {json.dumps(start_event, ensure_ascii=False)}\n\n"
                    
                    # Content block start
                    yield f"event: content_block_start\ndata: {json.dumps({'type': 'content_block_start', 'index': 0, 'content_block': {'type': 'text', 'text': ''}}, ensure_ascii=False)}\n\n"
                    
                    # Content chunks
                    await asyncio.sleep(0.1)
                    yield f"event: content_block_delta\ndata: {json.dumps({'type': 'content_block_delta', 'index': 0, 'delta': {'type': 'text_delta', 'text': 'Duplicate streaming test'}}, ensure_ascii=False)}\n\n"
                    
                    # End events
                    yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': 0}, ensure_ascii=False)}\n\n"
                    yield f"event: message_stop\ndata: {json.dumps({'type': 'message_stop'}, ensure_ascii=False)}\n\n"
                
                return StreamingResponse(
                    generate_duplicate_stream(),
                    media_type="text/event-stream",
                    headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
                )
                
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={
                    "type": "error",
                    "error": {
                        "type": "internal_server_error",
                        "message": f"Duplicate success provider error: {str(e)}"
                    }
                }
            )

    @router.post("/duplicate-concurrent/v1/messages")
    async def mock_duplicate_concurrent_provider(request: Request):
        """Mock provider with delay - for concurrent duplicate request testing."""
        try:
            request_body = await request.json()
            
            # Add delay to simulate processing time for concurrent testing
            await asyncio.sleep(0.2)
            
            return JSONResponse(
                status_code=200,
                content={
                    "id": "msg_concurrent_duplicate",
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "text",
                            "text": "Concurrent duplicate test response"
                        }
                    ],
                    "model": request_body.get("model", "duplicate-concurrent-test"),
                    "stop_reason": "end_turn",
                    "usage": {"input_tokens": 10, "output_tokens": 5}
                }
            )
                
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={
                    "type": "error",
                    "error": {
                        "type": "internal_server_error",
                        "message": f"Concurrent duplicate provider error: {str(e)}"
                    }
                }
            )

    @router.post("/parameter-sensitive/v1/messages")
    async def mock_parameter_sensitive_provider(request: Request):
        """Mock provider that returns different responses based on parameters."""
        try:
            request_body = await request.json()
            temperature = request_body.get('temperature', 0.0)
            
            # Return different responses based on temperature
            if temperature == 0.5:
                response_text = "Temperature 0.5 response"
                msg_id = "msg_temp_05"
            elif temperature == 0.8:
                response_text = "Temperature 0.8 response"
                msg_id = "msg_temp_08"
            else:
                response_text = f"Default response for temperature {temperature}"
                msg_id = "msg_temp_default"
            
            return JSONResponse(
                status_code=200,
                content={
                    "id": msg_id,
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "text",
                            "text": response_text
                        }
                    ],
                    "model": request_body.get("model", "parameter-test-model"),
                    "stop_reason": "end_turn",
                    "usage": {"input_tokens": 10, "output_tokens": 5}
                }
            )
                
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={
                    "type": "error",
                    "error": {
                        "type": "internal_server_error",
                        "message": f"Parameter sensitive provider error: {str(e)}"
                    }
                }
            )

    @router.post("/system-message-test/v1/messages")
    async def mock_system_message_provider(request: Request):
        """Mock provider for testing system message handling."""
        try:
            request_body = await request.json()
            system_msg = request_body.get('system', '')
            
            response_text = f"System message processed: {system_msg[:50]}..." if system_msg else "No system message"
            
            return JSONResponse(
                status_code=200,
                content={
                    "id": "msg_system_test",
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "text",
                            "text": response_text
                        }
                    ],
                    "model": request_body.get("model", "system-test-model"),
                    "stop_reason": "end_turn",
                    "usage": {"input_tokens": 15, "output_tokens": 8}
                }
            )
                
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={
                    "type": "error",
                    "error": {
                        "type": "internal_server_error",
                        "message": f"System message provider error: {str(e)}"
                    }
                }
            )

    @router.post("/tools-test/v1/messages")
    async def mock_tools_provider(request: Request):
        """Mock provider for testing tool call handling."""
        try:
            request_body = await request.json()
            tools = request_body.get('tools', [])
            
            if tools:
                # Return tool use response
                tool_name = tools[0].get('name', 'unknown_tool')
                return JSONResponse(
                    status_code=200,
                    content={
                        "id": "msg_tools_test",
                        "type": "message",
                        "role": "assistant",
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "tool_test_123",
                                "name": tool_name,
                                "input": {"test": "value"}
                            }
                        ],
                        "model": request_body.get("model", "tools-test-model"),
                        "stop_reason": "tool_use",
                        "usage": {"input_tokens": 25, "output_tokens": 10}
                    }
                )
            else:
                # No tools defined
                return JSONResponse(
                    status_code=200,
                    content={
                        "id": "msg_no_tools",
                        "type": "message",
                        "role": "assistant",
                        "content": [
                            {
                                "type": "text",
                                "text": "No tools available"
                            }
                        ],
                        "model": request_body.get("model", "tools-test-model"),
                        "stop_reason": "end_turn",
                        "usage": {"input_tokens": 15, "output_tokens": 5}
                    }
                )
                
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={
                    "type": "error",
                    "error": {
                        "type": "internal_server_error",
                        "message": f"Tools provider error: {str(e)}"
                    }
                }
            )

    @router.post("/failover-fail/v1/messages")
    async def mock_failover_fail_provider(request: Request):
        """Mock provider that always fails - for failover testing."""
        return JSONResponse(
            status_code=503,
            content={
                "type": "error",
                "error": {
                    "type": "service_unavailable",
                    "message": "Failover primary provider unavailable"
                }
            }
        )

    @router.post("/failover-success/v1/messages")
    async def mock_failover_success_provider(request: Request):
        """Mock provider that always succeeds - for failover testing."""
        try:
            request_body = await request.json()
            
            return JSONResponse(
                status_code=200,
                content={
                    "id": "msg_failover_success",
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "text",
                            "text": "Failover success response"
                        }
                    ],
                    "model": request_body.get("model", "failover-test-model"),
                    "stop_reason": "end_turn",
                    "usage": {"input_tokens": 10, "output_tokens": 5}
                }
            )
                
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={
                    "type": "error",
                    "error": {
                        "type": "internal_server_error",
                        "message": f"Failover success provider error: {str(e)}"
                    }
                }
            )

    return router