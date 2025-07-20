"""Cache serving functionality for handling cached responses."""

import asyncio
import json
import logging
import time
import uuid
from typing import Any, Dict, List

from fastapi.responses import JSONResponse, StreamingResponse

from .deduplication import _request_cleanup_lock, _duplicate_requests, extract_content_from_sse_chunks


def serve_waiting_duplicate_requests(signature: str, collected_chunks: List[str], is_streaming: bool, request_id: str):
    """立即为等待中的duplicate request提供服务，避免额外等待时间
    只响应最新的重试请求，按original_request_id分组"""
    try:
        from log_utils.handlers import debug, info, warning, error, LogRecord
    except ImportError:
        try:
            from log_utils import debug, info, warning, error, LogRecord
        except ImportError:
            debug = info = warning = error = lambda x: None
            LogRecord = dict
    
    served_count = 0
    cancelled_count = 0
    
    with _request_cleanup_lock:
        if signature in _duplicate_requests:
            duplicate_list = _duplicate_requests[signature]
            
            # 按original_request_id分组
            requests_by_original_id = {}
            for future, req_id, original_req_id, timestamp, is_stream in duplicate_list:
                if not future.done():
                    if original_req_id not in requests_by_original_id:
                        requests_by_original_id[original_req_id] = []
                    requests_by_original_id[original_req_id].append((future, req_id, timestamp, is_stream))
            
            # 为每组中最新的请求设置结果，取消较早的请求
            for original_req_id, requests_in_group in requests_by_original_id.items():
                if not requests_in_group:
                    continue
                
                # 按时间戳排序，最新的在最后
                requests_in_group.sort(key=lambda x: x[2])
                
                # 取消较早的请求（除了最新的一个）
                for future, req_id, timestamp, is_stream in requests_in_group[:-1]:
                    try:
                        if not future.done():
                            future.cancel()
                            cancelled_count += 1
                            debug(
                                LogRecord(
                                    "duplicate_request_cancelled",
                                    f"Cancelled earlier duplicate request {req_id[:8]}",
                                    req_id,
                                    {"original_request_id": original_req_id, "timestamp": timestamp}
                                )
                            )
                    except Exception as e:
                        error(
                            LogRecord(
                                "duplicate_request_cancel_error",
                                f"Failed to cancel duplicate request {req_id[:8]}: {str(e)}",
                                req_id,
                                {"error": str(e)}
                            )
                        )
                
                # 为最新的请求设置结果
                latest_future, latest_req_id, latest_timestamp, latest_is_stream = requests_in_group[-1]
                try:
                    if not latest_future.done():
                        # 根据请求类型构建响应
                        if latest_is_stream == is_streaming:
                            # 相同类型，直接提供collected_chunks
                            latest_future.set_result(collected_chunks)
                            served_count += 1
                            
                            debug(
                                LogRecord(
                                    "duplicate_request_served_directly",
                                    f"Served latest duplicate request {latest_req_id[:8]} with collected chunks",
                                    latest_req_id,
                                    {
                                        "original_request_id": original_req_id,
                                        "chunks_count": len(collected_chunks),
                                        "is_streaming": latest_is_stream,
                                        "timestamp": latest_timestamp
                                    }
                                )
                            )
                        else:
                            # 不同类型，设置特殊标记让后续处理进行转换
                            conversion_result = f"streaming_conversion_needed:{json.dumps(collected_chunks)}"
                            latest_future.set_result(conversion_result)
                            served_count += 1
                            
                            debug(
                                LogRecord(
                                    "duplicate_request_needs_conversion",
                                    f"Marked duplicate request {latest_req_id[:8]} for stream conversion",
                                    latest_req_id,
                                    {
                                        "original_request_id": original_req_id,
                                        "source_streaming": is_streaming,
                                        "target_streaming": latest_is_stream,
                                        "chunks_count": len(collected_chunks),
                                        "timestamp": latest_timestamp
                                    }
                                )
                            )
                except Exception as e:
                    error(
                        LogRecord(
                            "duplicate_request_set_result_error",
                            f"Failed to set result for duplicate request {latest_req_id[:8]}: {str(e)}",
                            latest_req_id,
                            {"error": str(e)}
                        )
                    )
            
            # 清理已完成的duplicate requests
            del _duplicate_requests[signature]
            
            info(
                LogRecord(
                    "duplicate_cleanup_summary",
                    f"Cleaned up duplicate requests for signature {signature[:16]}...",
                    request_id,
                    {
                        "signature": signature[:16] + "...",
                        "served_count": served_count,
                        "cancelled_count": cancelled_count
                    }
                )
            )


async def serve_from_cache(cached: Any, is_stream: bool, request_id: str) -> Any:
    """响应缓存已删除，此函数不应被调用"""
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=500,
        content={
            "type": "error",
            "error": {
                "type": "internal_error",
                "message": "serve_from_cache should not be called after response cache removal"
            }
        }
    )