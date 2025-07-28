"""
Mock providers specifically for test_multi_provider_management.py
Handles multi-provider management testing scenarios.
"""

import json
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse


def create_test_multi_provider_management_routes():
    """Create mock provider routes for test_multi_provider_management.py"""
    router = APIRouter()

    # ========== test_primary_provider_success ==========
    @router.post("/multi-primary-success-test/v1/messages")
    async def mock_multi_primary_success_test_provider(request: Request):
        """专用于test_primary_provider_success测试"""
        request_body = await request.json()
        return JSONResponse(
            status_code=200,
            content={
                "id": "msg_primary_success",
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": "Primary provider success response"}],
                "model": request_body.get("model", "claude-3-5-sonnet-20241022"),
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 10, "output_tokens": 8}
            }
        )

    # ========== test_failover_to_secondary_provider ==========
    @router.post("/multi-failover-primary-error-test/v1/messages")
    async def mock_multi_failover_primary_error_test_provider(request: Request):
        """专用于test_failover_to_secondary_provider测试中的主provider（错误）"""
        return JSONResponse(
            status_code=500,
            content={
                "type": "error",
                "error": {
                    "type": "internal_server_error",
                    "message": "Primary provider failure for failover test"
                }
            }
        )

    @router.post("/multi-failover-secondary-success-test/v1/messages")
    async def mock_multi_failover_secondary_success_test_provider(request: Request):
        """专用于test_failover_to_secondary_provider测试中的备provider（成功）"""
        request_body = await request.json()
        return JSONResponse(
            status_code=200,
            content={
                "id": "msg_secondary_success",
                "type": "message",
                "role": "assistant", 
                "content": [{"type": "text", "text": "Secondary provider failover success"}],
                "model": request_body.get("model", "claude-3-5-sonnet-20241022"),
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 10, "output_tokens": 8}
            }
        )

    # ========== test_all_providers_unavailable ==========
    @router.post("/multi-all-providers-error-test/v1/messages")
    async def mock_multi_all_providers_error_test_provider(request: Request):
        """专用于test_all_providers_unavailable测试（所有provider都失败）"""
        return JSONResponse(
            status_code=503,
            content={
                "type": "error",
                "error": {
                    "type": "service_unavailable",
                    "message": "All providers unavailable"
                }
            }
        )

    # ========== test_provider_cooldown_mechanism ==========
    @router.post("/multi-cooldown-test/v1/messages")
    async def mock_multi_cooldown_test_provider(request: Request):
        """专用于test_provider_cooldown_mechanism测试"""
        return JSONResponse(
            status_code=502,
            content={
                "type": "error",
                "error": {
                    "type": "bad_gateway",
                    "message": "Provider in cooldown test"
                }
            }
        )

    # ========== test_provider_recovery_after_cooldown ==========  
    @router.post("/multi-recovery-test/v1/messages")
    async def mock_multi_recovery_test_provider(request: Request):
        """专用于test_provider_recovery_after_cooldown测试"""
        request_body = await request.json()
        return JSONResponse(
            status_code=200,
            content={
                "id": "msg_recovery_success",
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": "Provider recovery success"}],
                "model": request_body.get("model", "claude-3-5-sonnet-20241022"),
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 10, "output_tokens": 8}
            }
        )

    # ========== test_streaming_failover ==========
    @router.post("/multi-streaming-failover-error-test/v1/messages")
    async def mock_multi_streaming_failover_error_test_provider(request: Request):
        """专用于test_streaming_failover测试中的错误provider"""
        return JSONResponse(
            status_code=500,
            content={
                "type": "error",
                "error": {
                    "type": "internal_server_error",
                    "message": "Streaming failover error test"
                }
            }
        )

    @router.post("/multi-streaming-failover-success-test/v1/messages")
    async def mock_multi_streaming_failover_success_test_provider(request: Request):
        """专用于test_streaming_failover测试中的成功provider"""
        request_body = await request.json()
        stream = request_body.get('stream', False)
        
        if stream:
            import asyncio
            async def generate_stream():
                yield f"data: {json.dumps({'type': 'message_start', 'message': {'id': 'msg_stream_failover', 'type': 'message', 'role': 'assistant', 'content': [], 'model': 'claude-3-5-sonnet-20241022', 'stop_reason': None, 'usage': {'input_tokens': 10, 'output_tokens': 0}}}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'type': 'content_block_start', 'index': 0, 'content_block': {'type': 'text', 'text': ''}}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'type': 'content_block_delta', 'index': 0, 'delta': {'type': 'text_delta', 'text': 'Streaming failover success'}}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'type': 'content_block_stop', 'index': 0}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'type': 'message_stop'}, ensure_ascii=False)}\n\n"
            
            from fastapi.responses import StreamingResponse
            return StreamingResponse(generate_stream(), media_type="text/event-stream")
        else:
            return JSONResponse(
                status_code=200,
                content={
                    "id": "msg_stream_failover",
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "text", "text": "Streaming failover success"}],
                    "model": request_body.get("model", "claude-3-5-sonnet-20241022"),
                    "stop_reason": "end_turn",
                    "usage": {"input_tokens": 10, "output_tokens": 8}
                }
            )

    # ========== test_provider_health_check_integration ==========
    @router.post("/multi-health-check-test/v1/messages")
    async def mock_multi_health_check_test_provider(request: Request):
        """专用于test_provider_health_check_integration测试"""
        request_body = await request.json()
        return JSONResponse(
            status_code=200,
            content={
                "id": "msg_health_check",
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": "Health check integration test"}],
                "model": request_body.get("model", "claude-3-5-sonnet-20241022"),
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 10, "output_tokens": 8}
            }
        )

    # ========== test_provider_priority_ordering ==========
    @router.post("/multi-priority-high-test/v1/messages")
    async def mock_multi_priority_high_test_provider(request: Request):
        """专用于test_provider_priority_ordering测试中的高优先级provider"""
        request_body = await request.json()
        return JSONResponse(
            status_code=200,
            content={
                "id": "msg_priority_high",
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": "High priority provider response"}],
                "model": request_body.get("model", "claude-3-5-sonnet-20241022"),
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 10, "output_tokens": 8}
            }
        )

    @router.post("/multi-priority-low-test/v1/messages")
    async def mock_multi_priority_low_test_provider(request: Request):
        """专用于test_provider_priority_ordering测试中的低优先级provider"""
        request_body = await request.json()
        return JSONResponse(
            status_code=200,
            content={
                "id": "msg_priority_low",
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": "Low priority provider response"}],
                "model": request_body.get("model", "claude-3-5-sonnet-20241022"),
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 10, "output_tokens": 8}
            }
        )

    # ========== test_concurrent_requests_with_failover ==========
    @router.post("/multi-concurrent-error-test/v1/messages")
    async def mock_multi_concurrent_error_test_provider(request: Request):
        """专用于test_concurrent_requests_with_failover测试中的错误provider"""
        return JSONResponse(
            status_code=500,
            content={
                "type": "error",
                "error": {
                    "type": "internal_server_error",
                    "message": "Concurrent failover error test"
                }
            }
        )

    @router.post("/multi-concurrent-success-test/v1/messages")
    async def mock_multi_concurrent_success_test_provider(request: Request):
        """专用于test_concurrent_requests_with_failover测试中的成功provider"""
        request_body = await request.json()
        return JSONResponse(
            status_code=200,
            content={
                "id": "msg_concurrent_success",
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": "Concurrent failover success"}],
                "model": request_body.get("model", "claude-3-5-sonnet-20241022"),
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 10, "output_tokens": 8}
            }
        )

    # ========== test_sticky_routing_after_success ==========
    @router.post("/multi-sticky-routing-test/v1/messages")
    async def mock_multi_sticky_routing_test_provider(request: Request):
        """专用于test_sticky_routing_after_success测试"""
        request_body = await request.json()
        return JSONResponse(
            status_code=200,
            content={
                "id": "msg_sticky_routing",
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": "Sticky routing test response"}],
                "model": request_body.get("model", "claude-3-5-sonnet-20241022"),
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 10, "output_tokens": 8}
            }
        )

    return router