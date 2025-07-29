"""
Mock providers specifically for test_streaming_requests.py
每个测试用例都有独立的mock provider，避免互相影响
"""

import json
import asyncio
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse, JSONResponse


def create_test_streaming_requests_routes():
    """Create mock provider routes for test_streaming_requests.py"""
    router = APIRouter()

    # ========== test_streaming_request_processing ==========
    @router.post("/streaming-processing-test/v1/messages")
    async def mock_streaming_processing_test_provider(request: Request):
        """专用于test_streaming_request_processing测试"""
        request_body = await request.json()
        stream = request_body.get('stream', False)
        
        if stream:
            async def generate_stream():
                yield f"data: {json.dumps({'type': 'message_start', 'message': {'id': 'msg_streaming_processing', 'type': 'message', 'role': 'assistant', 'content': [], 'model': request_body.get('model', 'claude-3-5-sonnet-20241022'), 'stop_reason': None, 'usage': {'input_tokens': 10, 'output_tokens': 0}}}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'type': 'content_block_start', 'index': 0, 'content_block': {'type': 'text', 'text': ''}}, ensure_ascii=False)}\n\n"
                
                text_chunks = ["Streaming", " processing", " test", " response"]
                for chunk in text_chunks:
                    yield f"data: {json.dumps({'type': 'content_block_delta', 'index': 0, 'delta': {'type': 'text_delta', 'text': chunk}}, ensure_ascii=False)}\n\n"
                    await asyncio.sleep(0.01)
                
                yield f"data: {json.dumps({'type': 'content_block_stop', 'index': 0}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'type': 'message_stop'}, ensure_ascii=False)}\n\n"
            
            return StreamingResponse(generate_stream(), media_type="text/event-stream")
        else:
            return JSONResponse(status_code=200, content={
                "id": "msg_streaming_processing", "type": "message", "role": "assistant",
                "content": [{"type": "text", "text": "Streaming processing test response"}],
                "model": request_body.get("model", "claude-3-5-sonnet-20241022"),
                "stop_reason": "end_turn", "usage": {"input_tokens": 10, "output_tokens": 5}
            })

    # ========== test_streaming_error_handling ==========
    @router.post("/streaming-error-test/v1/messages")
    async def mock_streaming_error_test_provider(request: Request):
        """专用于test_streaming_error_handling测试"""
        return JSONResponse(status_code=500, content={
            "error": {"type": "internal_server_error", "message": "Streaming error test"}
        })

    # ========== test_streaming_timeout_handling ==========
    @router.post("/streaming-timeout-test/v1/messages")
    async def mock_streaming_timeout_test_provider(request: Request):
        """专用于test_streaming_timeout_handling测试 - 模拟连接超时，在开始流式传输前就失败"""
        request_body = await request.json()
        stream = request_body.get('stream', False)
        
        # 模拟连接超时 - 在开始流式传输前就失败，返回408状态码
        # 这样可以让测试验证超时错误的正确处理
        if stream:
            return JSONResponse(status_code=408, content={
                "error": {"type": "timeout_error", "message": "Connection timeout before streaming started"}
            })
        else:
            return JSONResponse(status_code=408, content={
                "error": {"type": "timeout_error", "message": "Request timeout"}
            })

    # ========== test_streaming_interruption_handling ==========
    @router.post("/streaming-interruption-test/v1/messages")
    async def mock_streaming_interruption_test_provider(request: Request):
        """专用于test_streaming_interruption_handling测试"""
        request_body = await request.json()
        stream = request_body.get('stream', False)
        
        if stream:
            async def generate_interrupt_stream():
                yield f"data: {json.dumps({'type': 'message_start', 'message': {'id': 'msg_interrupt', 'type': 'message', 'role': 'assistant', 'content': [], 'model': 'claude-3-5-sonnet-20241022', 'stop_reason': None, 'usage': {'input_tokens': 10, 'output_tokens': 0}}}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'type': 'content_block_start', 'index': 0, 'content_block': {'type': 'text', 'text': ''}}, ensure_ascii=False)}\n\n"
                
                text_chunks = ["Stream", " will", " be", " interrupted"]
                for i, chunk in enumerate(text_chunks):
                    yield f"data: {json.dumps({'type': 'content_block_delta', 'index': 0, 'delta': {'type': 'text_delta', 'text': chunk}}, ensure_ascii=False)}\n\n"
                    if i == 2:  # 在第3个chunk后中断
                        return  # 直接返回，不发送结束事件
                    await asyncio.sleep(0.01)
            
            return StreamingResponse(generate_interrupt_stream(), media_type="text/event-stream")
        else:
            return JSONResponse(status_code=200, content={
                "id": "msg_interrupt", "type": "message", "role": "assistant",
                "content": [{"type": "text", "text": "Non-stream interrupt test"}],
                "model": "claude-3-5-sonnet-20241022", "stop_reason": "end_turn",
                "usage": {"input_tokens": 10, "output_tokens": 5}
            })

    # ========== test_streaming_200_with_empty_content ==========
    @router.post("/streaming-empty-content-test/v1/messages")
    async def mock_streaming_empty_content_test_provider(request: Request):
        """专用于test_streaming_200_with_empty_content测试 - 返回真正的空内容"""
        request_body = await request.json()
        stream = request_body.get('stream', False)
        
        if stream:
            async def generate_empty_stream():
                # 返回最基本的stream格式但没有实际内容
                yield f"data: {json.dumps({'type': 'message_start', 'message': {'id': 'msg_empty', 'type': 'message', 'role': 'assistant', 'content': [], 'model': 'claude-3-5-sonnet-20241022', 'stop_reason': None, 'usage': {'input_tokens': 10, 'output_tokens': 0}}}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'type': 'content_block_start', 'index': 0, 'content_block': {'type': 'text', 'text': ''}}, ensure_ascii=False)}\n\n"
                # 没有content_block_delta - 这就是"空内容"
                yield f"data: {json.dumps({'type': 'content_block_stop', 'index': 0}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'type': 'message_stop'}, ensure_ascii=False)}\n\n"
            
            return StreamingResponse(generate_empty_stream(), media_type="text/event-stream")
        else:
            return JSONResponse(status_code=200, content={
                "id": "msg_empty", "type": "message", "role": "assistant",
                "content": [{"type": "text", "text": ""}],  # 空内容
                "model": "claude-3-5-sonnet-20241022", "stop_reason": "end_turn",
                "usage": {"input_tokens": 10, "output_tokens": 0}
            })

    return router