"""Request deduplication and caching functionality."""

import asyncio
import dataclasses
import hashlib
import json
import time
import threading
import uuid
from typing import Any, Dict, List, Optional, Tuple, Union

from fastapi.responses import JSONResponse, StreamingResponse

from utils.logging.handlers import info, LogEvent

# Global references - set by main application
_provider_manager = None
# _make_anthropic_request = None  # No longer needed after handler refactoring

def set_provider_manager(manager):
    """Set the global provider manager reference"""
    global _provider_manager
    _provider_manager = manager

def get_provider_manager():
    """Get the global provider manager reference"""
    return _provider_manager

# Global state for caching and deduplication
_pending_requests: Dict[str, Tuple[asyncio.Future, str]] = {}
_duplicate_requests: Dict[str, List[Tuple[asyncio.Future, str, str, float, bool]]] = {}  # signature -> [(future, request_id, original_request_id, timestamp, is_stream), ...]
# 已删除响应缓存机制，只保留去重缓存
_request_cleanup_lock = threading.RLock()


def clear_all_cache():
    """Clear all pending requests and duplicate requests cache (for testing)"""
    global _pending_requests, _duplicate_requests
    
    with _request_cleanup_lock:
        # Cancel any pending futures before clearing
        for signature, (future, _) in list(_pending_requests.items()):
            if not future.done():
                future.cancel()
        
        for signature, duplicate_list in list(_duplicate_requests.items()):
            for future, _, _, _, _ in duplicate_list:
                if not future.done():
                    future.cancel()
        
        _pending_requests.clear()
        _duplicate_requests.clear()


# 响应缓存功能已删除，只保留去重功能



def cleanup_stuck_requests(force_cleanup_all: bool = False):
    """清理卡住的请求（超时但未正确清理的请求）"""
    try:
        provider_manager = get_provider_manager()
    except ImportError:
        provider_manager = None
    try:
        from utils.logging.handlers import warning, LogRecord
    except ImportError:
        try:
            from utils.logging import warning, LogRecord
        except ImportError:
            warning = lambda x: None
            LogRecord = dict
    
    if not provider_manager:
        return
    
    current_time = time.time()
    # 获取去重超时配置
    request_timeout = _provider_manager.get_caching_timeouts()['deduplication_timeout'] if _provider_manager else 300
    
    with _request_cleanup_lock:
        stuck_requests = []
        
        # 检查pending requests
        for signature, (future, request_id) in list(_pending_requests.items()):
            should_cleanup = False
            reason = ""
            
            # 检查Future是否已经完成但没有被清理
            if future.done():
                try:
                    result = future.result()
                    should_cleanup = True
                    reason = "completed_but_not_cleaned"
                except Exception as e:
                    should_cleanup = True
                    reason = f"failed_but_not_cleaned: {str(e)}"
            elif force_cleanup_all:
                # 强制清理模式：取消所有未完成的Future
                should_cleanup = True
                reason = "force_cleanup_requested"
                if not future.cancelled():
                    future.cancel()
            
            if should_cleanup:
                stuck_requests.append((signature, request_id, reason))
                del _pending_requests[signature]
        
        # 检查duplicate requests
        for signature, duplicate_list in list(_duplicate_requests.items()):
            requests_to_cleanup = []
            
            for future, req_id, original_req_id, timestamp, is_stream in duplicate_list:
                should_cleanup = False
                reason = ""
                
                # 检查Future是否已经完成但没有被清理
                if future.done():
                    try:
                        result = future.result()
                        should_cleanup = True
                        reason = "completed_but_not_cleaned"
                    except Exception as e:
                        should_cleanup = True
                        reason = f"failed_but_not_cleaned: {str(e)}"
                elif force_cleanup_all:
                    # 强制清理模式：取消所有未完成的Future
                    should_cleanup = True
                    reason = "force_cleanup_requested"
                    if not future.cancelled():
                        future.cancel()
                
                if should_cleanup:
                    requests_to_cleanup.append((req_id, reason))
            
            # 从duplicate_list中移除已清理的请求
            if requests_to_cleanup:
                cleanup_ids = {req_id for req_id, _ in requests_to_cleanup}
                _duplicate_requests[signature] = [
                    (future, req_id, original_req_id, timestamp, is_stream)
                    for future, req_id, original_req_id, timestamp, is_stream in duplicate_list
                    if req_id not in cleanup_ids
                ]
                
                # 如果列表为空，删除整个条目
                if not _duplicate_requests[signature]:
                    del _duplicate_requests[signature]
                
                # 添加到stuck_requests日志中
                for req_id, reason in requests_to_cleanup:
                    stuck_requests.append((signature, req_id, f"duplicate_{reason}"))
        
        if stuck_requests:
            for signature, request_id, reason in stuck_requests:
                warning(
                    LogRecord(
                        LogEvent.STUCK_REQUEST_CLEANUP.value,
                        f"Cleaned up stuck request: {reason}",
                        request_id,
                        {
                            "signature": signature[:16] + "...",
                            "reason": reason,
                            "cleanup_method": "manual" if force_cleanup_all else "automatic"
                        }
                    )
                )




async def simulate_testing_delay(request_body: Dict[str, Any], request_id: str):
    """模拟测试延迟，用于测试重试机制"""
    try:
        provider_manager = get_provider_manager()
    except ImportError:
        provider_manager = None
    try:
        from utils.logging.handlers import info, LogRecord
    except ImportError:
        try:
            from utils.logging import info, LogRecord
        except ImportError:
            info = lambda x: None
            LogRecord = dict
    
    if not provider_manager:
        return
    
    testing_config = provider_manager.settings.get("testing", {})
    if not testing_config.get("simulate_delay", False):
        return
    
    delay_seconds = testing_config.get("delay_seconds", 70)
    trigger_keywords = testing_config.get("delay_trigger_keywords", [])
    
    # 检查是否应该触发延迟
    should_delay = False
    
    if trigger_keywords:
        # 检查消息内容是否包含触发关键词
        messages = request_body.get("messages", [])
        for message in messages:
            content = message.get("content", "")
            if isinstance(content, str):
                for keyword in trigger_keywords:
                    if keyword.lower() in content.lower():
                        should_delay = True
                        break
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text = block.get("text", "")
                        for keyword in trigger_keywords:
                            if keyword.lower() in text.lower():
                                should_delay = True
                                break
            if should_delay:
                break
    else:
        # 如果没有配置关键词，则对所有请求启用延迟
        should_delay = True
    
    if should_delay:
        info(
            LogRecord(
                "testing_delay_start",
                f"Starting simulated delay of {delay_seconds} seconds for testing",
                request_id,
                {
                    "delay_seconds": delay_seconds,
                    "trigger_keywords": trigger_keywords,
                    "reason": "Testing retry mechanism"
                }
            )
        )
        
        # 执行延迟
        await asyncio.sleep(delay_seconds)
        
        info(
            LogRecord(
                "testing_delay_end",
                f"Simulated delay of {delay_seconds} seconds completed",
                request_id,
                {"delay_seconds": delay_seconds}
            )
        )


def generate_request_signature(data: Dict[str, Any]) -> str:
    """为请求生成唯一签名用于去重"""
    try:
        provider_manager = get_provider_manager()
    except ImportError:
        provider_manager = None
    
    # 统一的签名生成逻辑，不区分流式和非流式
    # 这样相同内容的流式和非流式请求会生成相同的签名，实现真正的去重
    signature_data = {
        "model": data.get("model", ""),
        "messages": data.get("messages", []),
        "system": data.get("system", ""),
        "tools": data.get("tools", []),
        "temperature": data.get("temperature", 0),
        # 不包含 stream 字段，让流式和非流式请求共享去重
    }
    
    # 根据配置决定是否包含 max_tokens 字段
    include_max_tokens = provider_manager.settings.get("deduplication", {}).get("include_max_tokens_in_signature", False) if provider_manager else False
    if include_max_tokens:
        signature_data["max_tokens"] = data.get("max_tokens", 0)

    # Import logging utilities upfront to avoid scope issues  
    from utils.logging.handlers import warning, LogRecord, LogEvent
    
    # 将数据转换为可哈希的字符串
    try:
        signature_str = json.dumps(signature_data, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    except UnicodeEncodeError:
        # Handle Unicode issues in request data for signature generation
        warning(LogRecord(
            event=LogEvent.REQUEST_RECEIVED.value,
            message="Request data contains invalid Unicode characters, using ASCII encoding for signature generation",
            request_id=None,
            data={"signature_truncated": signature_str[:50] if 'signature_str' in locals() else "unavailable"}
        ))
        signature_str = json.dumps(signature_data, sort_keys=True, separators=(',', ':'), ensure_ascii=True)

    # 生成 SHA256 哈希，使用安全的编码方式
    try:
        signature_hash = hashlib.sha256(signature_str.encode('utf-8')).hexdigest()
    except UnicodeEncodeError:
        # Final fallback: use errors='ignore' to handle any remaining Unicode issues
        signature_hash = hashlib.sha256(signature_str.encode('utf-8', errors='ignore')).hexdigest()


    return signature_hash


def cleanup_completed_request(signature: str):
    """清理已完成的请求"""
    with _request_cleanup_lock:
        if signature in _pending_requests:
            del _pending_requests[signature]


def complete_and_cleanup_request_delayed(signature: str, result: Any, cache_content: Optional[Union[Dict[str, Any], List[str]]] = None, is_streaming: bool = False, provider_name: Optional[str] = None, delay_seconds: int = 30):
    """完成请求并延迟清理去重状态（用于SSE错误等场景）"""
    try:
        from utils.logging.handlers import debug, info, error, LogRecord
    except ImportError:
        try:
            from utils.logging import debug, info, error, LogRecord
        except ImportError:
            debug = info = error = lambda x: None
            LogRecord = dict
    
    # 先完成请求，但不立即清理
    if signature:
        try:
            with _request_cleanup_lock:
                # 处理原始请求
                if signature in _pending_requests:
                    future, original_request_id = _pending_requests[signature]
                    if not future.done():
                        future.set_result(result)
                    # 注意：这里不删除 _pending_requests[signature]，延迟删除
                    
                    debug(
                        LogRecord(
                            LogEvent.REQUEST_COMPLETED_DELAY_CLEANUP.value,
                            f"Request completed, cleanup delayed by {delay_seconds} seconds",
                            original_request_id,
                            {
                                "signature": signature[:16] + "...",
                                "result_type": type(result).__name__,
                                "delay_seconds": delay_seconds
                            }
                        )
                    )
                
                # 处理duplicate请求 - 给它们相同的结果
                if signature in _duplicate_requests:
                    duplicate_requests = _duplicate_requests[signature]
                    completed_count = 0
                    
                    debug(
                        LogRecord(
                            "processing_duplicate_requests_delayed",
                            f"Found {len(duplicate_requests)} duplicate requests to process",
                            original_request_id,
                            {
                                "signature": signature[:16] + "...",
                                "duplicate_count": len(duplicate_requests),
                                "result_type": type(result).__name__
                            }
                        )
                    )
                    
                    for duplicate_future, duplicate_request_id, _, _, _ in duplicate_requests:
                        if not duplicate_future.done():
                            duplicate_future.set_result(result)
                            completed_count += 1
                            debug(
                                LogRecord(
                                    "duplicate_future_set_result",
                                    f"Set result for duplicate request {duplicate_request_id[:8]}",
                                    original_request_id,
                                    {
                                        "duplicate_request_id": duplicate_request_id[:8],
                                        "signature": signature[:16] + "...",
                                        "result_type": type(result).__name__
                                    }
                                )
                            )
                        else:
                            debug(
                                LogRecord(
                                    "duplicate_future_already_done",
                                    f"Duplicate request {duplicate_request_id[:8]} already completed",
                                    original_request_id,
                                    {
                                        "duplicate_request_id": duplicate_request_id[:8],
                                        "signature": signature[:16] + "...",
                                    }
                                )
                            )
                    # 延迟清理duplicate requests
                    debug(
                        LogRecord(
                            LogEvent.DUPLICATE_REQUESTS_COMPLETED_DELAY_CLEANUP.value,
                            f"Duplicate requests completed, cleanup delayed by {delay_seconds} seconds",
                            original_request_id,
                            {
                                "signature": signature[:16] + "...",
                                "duplicate_count": len(_duplicate_requests[signature]),
                                "completed_count": completed_count
                            }
                        )
                    )
                else:
                    debug(
                        LogRecord(
                            LogEvent.NO_DUPLICATE_REQUESTS_FOUND.value,
                            f"No duplicate requests found for signature during delayed cleanup",
                            original_request_id,
                            {
                                "signature": signature[:16] + "...",
                                "result_type": type(result).__name__
                            }
                        )
                    )
        except Exception as e:
            error(
                LogRecord(
                    "request_delayed_completion_error", 
                    f"Error during delayed request completion: {str(e)}",
                    "",
                    {"signature": signature[:16] + "...", "error": str(e)}
                )
            )
    
    # 启动延迟清理任务（使用asyncio而不是线程，避免阻塞）
    import asyncio
    
    async def delayed_cleanup_async():
        try:
            await asyncio.sleep(delay_seconds)
            with _request_cleanup_lock:
                # 在延迟清理时，再次检查是否有新的重复请求到达
                # 如果有，为它们设置结果
                if signature in _duplicate_requests:
                    duplicate_requests = _duplicate_requests[signature]
                    late_completion_count = 0
                    
                    debug(
                        LogRecord(
                            LogEvent.LATE_DUPLICATE_REQUESTS_FOUND.value,
                            f"Found {len(duplicate_requests)} duplicate requests during delayed cleanup",
                            "",
                            {
                                "signature": signature[:16] + "...",
                                "duplicate_count": len(duplicate_requests),
                                "result_type": type(result).__name__
                            }
                        )
                    )
                    
                    for duplicate_future, duplicate_request_id, _, _, _ in duplicate_requests:
                        if not duplicate_future.done():
                            duplicate_future.set_result(result)
                            late_completion_count += 1
                            debug(
                                LogRecord(
                                    LogEvent.LATE_DUPLICATE_FUTURE_SET_RESULT.value,
                                    f"Set result for late duplicate request {duplicate_request_id[:8]}",
                                    "",
                                    {
                                        "duplicate_request_id": duplicate_request_id[:8],
                                        "signature": signature[:16] + "...",
                                        "result_type": type(result).__name__
                                    }
                                )
                            )
                    
                    if late_completion_count > 0:
                        debug(
                            LogRecord(
                                LogEvent.LATE_DUPLICATE_COMPLETION_SUMMARY.value,
                                f"Completed {late_completion_count} late duplicate requests during cleanup",
                                "",
                                {
                                    "signature": signature[:16] + "...",
                                    "late_completion_count": late_completion_count
                                }
                            )
                        )
                
                # 延迟后执行清理
                cleaned_items = []
                if signature in _pending_requests:
                    del _pending_requests[signature]
                    cleaned_items.append("pending_requests")
                if signature in _duplicate_requests:
                    del _duplicate_requests[signature]
                    cleaned_items.append("duplicate_requests")
                
                if cleaned_items:
                    debug(
                        LogRecord(
                            LogEvent.DELAYED_CLEANUP_COMPLETED.value,
                            f"Delayed cleanup completed for signature",
                            "",
                            {
                                "signature": signature[:16] + "...", 
                                "delay_seconds": delay_seconds,
                                "cleaned_items": cleaned_items
                            }
                        )
                    )
        except Exception as e:
            error(
                LogRecord(
                    "delayed_cleanup_error",
                    f"Error during delayed cleanup: {str(e)}",
                    "",
                    {"signature": signature[:16] + "...", "error": str(e)}
                )
            )
    
    # 在后台任务中执行延迟清理，不阻塞当前请求
    try:
        loop = asyncio.get_event_loop()
        loop.create_task(delayed_cleanup_async())
    except RuntimeError:
        # 如果没有运行的事件循环，回退到线程方式
        def delayed_cleanup_thread():
            try:
                time.sleep(delay_seconds)
                with _request_cleanup_lock:
                    cleaned_items = []
                    if signature in _pending_requests:
                        del _pending_requests[signature]
                        cleaned_items.append("pending_requests")
                    if signature in _duplicate_requests:
                        del _duplicate_requests[signature]
                        cleaned_items.append("duplicate_requests")
                    
                    if cleaned_items:
                        debug(
                            LogRecord(
                                LogEvent.DELAYED_CLEANUP_COMPLETED.value,
                                f"Delayed cleanup completed for signature",
                                "",
                                {
                                    "signature": signature[:16] + "...", 
                                    "delay_seconds": delay_seconds,
                                    "cleaned_items": cleaned_items
                                }
                            )
                        )
            except Exception as e:
                error(
                    LogRecord(
                        "delayed_cleanup_error",
                        f"Error during delayed cleanup: {str(e)}",
                        "",
                        {"signature": signature[:16] + "...", "error": str(e)}
                    )
                )
        
        cleanup_thread = threading.Thread(target=delayed_cleanup_thread, daemon=True)
        cleanup_thread.start()

def complete_and_cleanup_request(signature: str, result: Any, cache_content: Optional[Union[Dict[str, Any], List[str]]] = None, is_streaming: bool = False, provider_name: Optional[str] = None):
    """完成请求并清理去重状态"""
    try:
        from utils.logging.handlers import debug, info, error, LogRecord
    except ImportError:
        try:
            from utils.logging import debug, info, error, LogRecord
        except ImportError:
            debug = info = error = lambda x: None
            LogRecord = dict
    
    # 检查是否是客户端断开导致的完成
    is_client_disconnect = isinstance(result, Exception) and "Client disconnected" in str(result)
    
    
    if signature:
        try:
            # 设置 Future 结果并清理
            with _request_cleanup_lock:
                # 处理原始请求
                if signature in _pending_requests:
                    future, original_request_id = _pending_requests[signature]
                    if not future.done():
                        future.set_result(result)
                    del _pending_requests[signature]
                    debug(
                        LogRecord(
                            LogEvent.ORIGINAL_REQUEST_COMPLETED.value,
                            f"Original request completed and cleaned up",
                            original_request_id,
                            {"signature": signature[:16] + "...", "result_type": type(result).__name__}
                        )
                    )
                else:
                    debug(
                        LogRecord(
                            LogEvent.REQUEST_CLEANUP_SKIP.value,
                            f"No pending request found for signature (non-duplicate request)",
                            None,
                            {"signature": signature[:16] + "...", "result_type": type(result).__name__}
                        )
                    )
                
                # 处理所有等待中的duplicate requests，只响应每个original_request_id的最新请求
                # 即使原始请求不在_pending_requests中，也要检查_duplicate_requests
                if signature in _duplicate_requests and _duplicate_requests[signature]:
                    duplicate_list = _duplicate_requests[signature]
                    
                    # 快速检查是否有未完成的请求，如果没有就跳过处理
                    has_pending_requests = any(not future.done() for future, _, _, _, _ in duplicate_list)
                    if not has_pending_requests:
                        # 清理空的duplicate requests条目
                        del _duplicate_requests[signature]
                        debug(
                            LogRecord(
                                "no_pending_duplicates_skip",
                                f"All duplicate requests for signature {signature[:16]}... already completed, skipping",
                                original_request_id if 'original_request_id' in locals() else "unknown",
                                {"signature": signature[:16] + "..."}
                            )
                        )
                    else:
                        # 按original_request_id分组
                        requests_by_original_id = {}
                        for future, req_id, original_req_id, timestamp, is_stream in duplicate_list:
                            if not future.done():
                                if original_req_id not in requests_by_original_id:
                                    requests_by_original_id[original_req_id] = []
                                requests_by_original_id[original_req_id].append((future, req_id, timestamp, is_stream))
                        
                        # 为每组中最新的请求设置结果，取消较早的请求
                        served_count = 0
                        cancelled_count = 0
                        
                        for original_req_id, requests_in_group in requests_by_original_id.items():
                            if not requests_in_group:
                                continue
                            
                            # 按时间戳排序，最新的在最后
                            requests_in_group.sort(key=lambda x: x[2])
                            
                            # 如果是客户端断开导致的完成，需要特殊处理
                            if is_client_disconnect:
                                # 对于客户端断开的情况，只将结果发送给非流式请求
                                # 流式请求的客户端已经断开，发送结果没有意义
                                for future, req_id, timestamp, is_stream in requests_in_group:
                                    try:
                                        if is_stream:
                                            # 流式请求的客户端已断开，取消这些请求
                                            future.cancel()
                                            cancelled_count += 1
                                            debug(
                                                LogRecord(
                                                    "stream_request_cancelled_due_to_disconnect",
                                                    f"Cancelled stream request {req_id[:8]} due to original client disconnect",
                                                    req_id,
                                                    {"original_request_id": original_req_id, "timestamp": timestamp}
                                                )
                                            )
                                        else:
                                            # 非流式请求仍然可以接收结果
                                            # 但将错误转换为适当的响应，而不是客户端断开错误
                                            timeout_error = Exception("Original streaming request timed out")
                                            future.set_result(timeout_error)
                                            served_count += 1
                                            debug(
                                                LogRecord(
                                                    "non_stream_served_after_disconnect",
                                                    f"Served non-stream request {req_id[:8]} with timeout error after original disconnect",
                                                    req_id,
                                                    {"original_request_id": original_req_id, "timestamp": timestamp}
                                                )
                                            )
                                    except Exception:
                                        pass
                            else:
                                # 正常完成的情况，使用原来的逻辑
                                # 取消较早的请求
                                for future, req_id, timestamp, is_stream in requests_in_group[:-1]:
                                    try:
                                        future.cancel()
                                        cancelled_count += 1
                                    except Exception:
                                        pass
                                
                                # 为最新的请求设置结果
                                latest_future, latest_req_id, latest_timestamp, latest_is_stream = requests_in_group[-1]
                                try:
                                    latest_future.set_result(result)
                                    served_count += 1
                                except Exception:
                                    pass
                        
                        # 清理duplicate requests
                        del _duplicate_requests[signature]
                        
                        if served_count > 0 or cancelled_count > 0:
                            info(
                                LogRecord(
                                    "duplicate_cleanup_summary",
                                    f"Cleaned up duplicate requests for signature {signature[:16]}...",
                                    original_request_id if 'original_request_id' in locals() else "unknown",
                                    {
                                        "signature": signature[:16] + "...",
                                        "served_latest_count": served_count,
                                        "cancelled_earlier_count": cancelled_count,
                                        "client_disconnect": is_client_disconnect
                                    }
                                )
                            )
                    
                    # 响应缓存已删除，不再缓存响应内容
                    
                    # 根据结果类型确定清理原因
                    if is_client_disconnect:
                        cleanup_reason = "client_disconnected"
                        message = f"Request cleaned up due to client disconnect (duplicate request cleared)"
                    elif isinstance(result, Exception):
                        cleanup_reason = "request_failed"
                        message = f"Request failed and cleaned up (duplicate request cleared): {str(result)}"
                    elif isinstance(result, str):
                        if "streaming" in result:
                            cleanup_reason = LogEvent.STREAMING_COMPLETED.value
                            message = f"Streaming request completed and cleaned up (duplicate request cleared)"
                        else:
                            cleanup_reason = LogEvent.REQUEST_COMPLETED.value
                            message = f"Request completed and cleaned up (duplicate request cleared)"
                    else:
                        cleanup_reason = LogEvent.REQUEST_COMPLETED.value
                        message = f"Request completed and cleaned up (duplicate request cleared)"
                    
                    info(
                        LogRecord(
                            LogEvent.REQUEST_CLEANUP.value,
                            message,
                            original_request_id,
                            {
                                "request_signature": signature[:16] + "...",
                                "result_type": type(result).__name__,
                                "pending_requests_count": len(_pending_requests),
                                "cleanup_reason": cleanup_reason,
                                "client_disconnect": is_client_disconnect
                            },
                        )
                    )
                else:
                    # 这种情况是正常的，因为非重复请求不会在pending_requests中
                    debug(
                        LogRecord(
                            LogEvent.REQUEST_CLEANUP_SKIP.value,
                            f"No pending request found for signature (non-duplicate request)",
                            None,
                            {"signature": signature[:16] + "..."},
                        )
                    )
        except Exception as e:
            error(
                LogRecord(
                    "request_cleanup_error",
                    f"Error during request cleanup: {str(e)}",
                    None,
                    {"signature": signature[:16] + "..."},
                )
            )




async def handle_duplicate_request(signature: str, request_id: str, is_stream: bool = False, request_data: Dict[str, Any] = None) -> Optional[Any]:
    """处理重复请求，如果是重复请求则等待原请求完成"""
    try:
        from utils.logging.handlers import info, warning, LogRecord, LogEvent
    except ImportError:
        try:
            from utils.logging import info, warning, LogRecord, LogEvent
        except ImportError:
            info = warning = lambda x: None
            LogRecord = dict
            class LogEvent:
                REQUEST_RECEIVED = type('', (), {'value': 'request_received'})()
                REQUEST_COMPLETED = type('', (), {'value': 'request_completed'})()
                REQUEST_FAILURE = type('', (), {'value': 'request_failure'})()
    
    future_to_wait = None
    original_request_id = None

    with _request_cleanup_lock:
        # 响应缓存已删除，直接检查去重逻辑
        
        if signature in _pending_requests or signature in _duplicate_requests:
            # 检查是否有正在处理的原始请求
            if signature in _pending_requests:
                # 这是重复请求，获取 Future 但不在锁内等待
                future_to_wait, original_request_id = _pending_requests[signature]
                
                # 将这个重复请求添加到 _duplicate_requests 中
                if signature not in _duplicate_requests:
                    _duplicate_requests[signature] = []
                
                # 创建新的Future为这个duplicate request
                duplicate_future = asyncio.Future()
                current_timestamp = time.time()
                _duplicate_requests[signature].append((duplicate_future, request_id, original_request_id, current_timestamp, is_stream))
                
                info(
                    LogRecord(
                        LogEvent.DUPLICATE_REQUEST_RECEIVED.value,
                        f"Duplicate request for original request {original_request_id[:8]}, added to duplicate requests queue",
                        request_id,
                        {
                            "original_request_id": original_request_id[:8],
                            "signature": signature[:16] + "...",
                            "duplicate_queue_size": len(_duplicate_requests[signature])
                        }
                    )
                )
                
                # 等待这个duplicate request的结果
                future_to_wait = duplicate_future
                
            elif signature in _duplicate_requests:
                # 检查是否还有活跃的duplicate requests等待
                # 如果没有活跃的等待请求，说明原始请求已经完成，这应该是一个新请求
                active_duplicates = [f for f, _, _, _, _ in _duplicate_requests[signature] if not f.done()]
                
                if not active_duplicates:
                    # 没有活跃的duplicate requests，清理这个signature并当作新请求处理
                    del _duplicate_requests[signature]
                    info(
                        LogRecord(
                            LogEvent.REQUEST_RECEIVED.value,
                            f"Found inactive duplicate queue for signature {signature[:16]}..., treating as new request",
                            request_id,
                            {"signature": signature[:16] + "...", "cleaned_inactive_queue": True}
                        )
                    )
                    # 这是新请求，创建 Future 并记录
                    future = asyncio.Future()
                    _pending_requests[signature] = (future, request_id)
                    return None  # 表示这是新请求，继续处理
                else:
                    # 有其他重复请求在等待，添加到队列
                    duplicate_future = asyncio.Future()
                    current_timestamp = time.time()
                    _duplicate_requests[signature].append((duplicate_future, request_id, original_request_id, current_timestamp, is_stream))
                    
                    info(
                        LogRecord(
                            LogEvent.REQUEST_RECEIVED.value,
                            f"Additional duplicate request for signature {signature[:16]}..., added to duplicate requests queue",
                            request_id,
                            {
                                "signature": signature[:16] + "...",
                                "duplicate_queue_size": len(_duplicate_requests[signature]),
                                "is_stream": is_stream
                            }
                        )
                    )
                    
                    # 等待这个duplicate request的结果
                    future_to_wait = duplicate_future
        else:
            # 这是新请求，创建 Future 并记录
            future = asyncio.Future()
            _pending_requests[signature] = (future, request_id)
            return None  # 表示这是新请求，继续处理

    # 在锁外等待原请求完成
    if future_to_wait:
        try:
            # 添加超时机制防止无限等待
            try:
                from core.provider_manager import get_provider_manager
                provider_manager = get_provider_manager()
                timeout = provider_manager.get_caching_timeouts()['deduplication_timeout'] if provider_manager else 180
            except:
                timeout = 180  # 默认3分钟超时
            
            result = await asyncio.wait_for(future_to_wait, timeout=timeout)
            
            # 检查result是否是Exception对象
            if isinstance(result, Exception):
                # 原请求失败，重复请求也应该收到相同的错误
                info(
                    LogRecord(
                        LogEvent.REQUEST_FAILURE.value,
                        "Duplicate request failed via original request",
                        request_id,
                        {"original_request_id": original_request_id, "signature": signature[:16] + "...", "error": str(result)},
                    )
                )
                
                # 对于流式duplicate requests，需要返回StreamingResponse格式的错误
                if is_stream:
                    # 尝试从异常消息中提取有意义的错误信息
                    error_message = str(result)
                    if "Provider returned JSON error:" in error_message:
                        # 这是来自provider的JSON错误，尝试提取原始消息
                        try:
                            # 从异常消息中提取实际的错误信息
                            # 假设格式是 "Provider returned JSON error: {...}"
                            parts = error_message.split("Provider returned JSON error:", 1)
                            if len(parts) > 1:
                                extracted_part = parts[1].strip()
                                # 先检查原始的chunk数据，这个信息应该在原始请求的SSE输出中
                                # 但是我们这里只有Exception对象，需要从原始提供商响应中获取完整信息
                                
                                # 由于我们无法直接访问原始JSON响应，我们需要重新构造
                                # 最好的做法是保持错误消息的一致性，使用相同的处理逻辑
                                
                                # 检查是否是简单的错误字符串还是JSON结构
                                if extracted_part.startswith('{') and extracted_part.endswith('}'):
                                    # 尝试解析为JSON以提取实际的错误消息
                                    try:
                                        error_json = json.loads(extracted_part)
                                        if isinstance(error_json, dict):
                                            # 优先使用message字段，如果没有则使用error字段
                                            if "message" in error_json:
                                                error_message = error_json["message"]
                                            elif "error" in error_json and isinstance(error_json["error"], str):
                                                error_message = error_json["error"]
                                            else:
                                                error_message = extracted_part
                                        else:
                                            error_message = extracted_part
                                    except json.JSONDecodeError:
                                        # 不是JSON格式，直接使用提取的部分
                                        error_message = extracted_part
                                else:
                                    # 不是JSON格式，但这可能只是error字段的值
                                    # 保持原来的逻辑，直接使用提取的部分
                                    error_message = extracted_part
                        except:
                            pass  # 如果提取失败，使用原始错误消息
                    
                    # 创建一个包含错误信息的streaming response
                    error_response = {
                        "type": "error",
                        "error": {
                            "type": "api_error",
                            "message": error_message
                        }
                    }
                    
                    async def stream_error_response():
                        from utils.logging.formatters import _safe_json_dumps
                        formatted_error_chunk = f"event: error\ndata: {_safe_json_dumps(error_response)}\n\n"
                        yield formatted_error_chunk
                    
                    from fastapi.responses import StreamingResponse
                    return StreamingResponse(
                        stream_error_response(),
                        media_type="text/event-stream"
                    )
                else:
                    # 对于非流式请求，重新抛出异常让上层处理器处理
                    raise result
            elif isinstance(result, list):
                # 检查是否是实际发送给客户端的内容缓存 (List[str]格式的collected_chunks)
                # 这可能包含SSE错误响应或者正常的SSE内容
                # 注意：即使是空列表也应该处理，因为这可能代表原始请求的真实状态
                
                if is_stream:
                    # 流式请求：直接返回缓存的内容（无论是成功还是错误，甚至是空内容）
                        
                    async def stream_cached_content():
                        for chunk in result:
                            yield chunk
                    
                    from fastapi.responses import StreamingResponse
                    return StreamingResponse(
                        stream_cached_content(),
                        media_type="text/event-stream"
                    )
                else:
                    # 非流式请求：需要从SSE格式转换为JSON格式
                    # 如果是空列表，说明原始请求没有收到任何内容
                    if not result:
                        return JSONResponse(
                            content={
                                "type": "error",
                                "error": {
                                    "type": "api_error",
                                    "message": "No response received from provider"
                                }
                            },
                            status_code=500
                        )
                    
                    # 首先检查是否是错误响应
                    for chunk in result:
                        if isinstance(chunk, str) and "event: error" in chunk:
                            # 这是错误响应，从SSE格式提取JSON错误响应
                            try:
                                lines = chunk.strip().split('\n')
                                for line in lines:
                                    if line.startswith('data:'):
                                        error_data = line[5:].strip()  # Remove 'data:' prefix
                                        error_json = json.loads(error_data)
                                        
                                        # 确定正确的HTTP状态码
                                        status_code = 500  # 默认为500
                                        if isinstance(error_json, dict) and "error" in error_json:
                                            error_type = error_json.get("error", {}).get("type", "")
                                            # 根据错误类型确定状态码
                                            if error_type in ["invalid_request_error", "authentication_error"]:
                                                status_code = 400
                                            elif error_type in ["permission_error", "forbidden"]:
                                                status_code = 403
                                            elif error_type in ["not_found_error"]:
                                                status_code = 404
                                            elif error_type in ["rate_limit_error"]:
                                                status_code = 429
                                            elif error_type in ["overloaded_error"]:
                                                status_code = 529
                                            else:
                                                status_code = 500
                                        
                                        return JSONResponse(content=error_json, status_code=status_code)
                            except Exception:
                                pass
                    
                    # 如果不是错误响应，尝试提取为正常响应
                    try:
                        response_content = extract_content_from_sse_chunks(result)
                        info(
                            LogRecord(
                                LogEvent.REQUEST_COMPLETED.value,
                                "Duplicate request returning cached successful response",
                                request_id,
                                {"original_request_id": original_request_id, "signature": signature[:16] + "...", "is_stream": is_stream},
                            )
                        )
                        return JSONResponse(content=response_content)
                    except Exception as e:
                        # 添加详细的错误日志
                        from utils.logging.handlers import error
                        error(
                            LogRecord(
                                LogEvent.REQUEST_FAILURE.value,
                                f"Failed to extract content from SSE chunks: {str(e)}",
                                request_id,
                                {
                                    "error_type": type(e).__name__,
                                    "error_message": str(e),
                                    "result_type": type(result).__name__ if 'result' in locals() else "unknown",
                                    "result_length": len(result) if isinstance(result, (list, str)) and 'result' in locals() else "unknown"
                                }
                            )
                        )
                        # 内容提取失败，返回通用错误
                        return JSONResponse(
                            content={
                                "type": "error",
                                "error": {
                                    "type": "api_error",
                                    "message": "Failed to process cached response"
                                }
                            },
                            status_code=500
                        )
            
            # 成功响应 - 根据是否为流式请求分别处理
            if is_stream:
                # 流式重复请求需要返回StreamingResponse格式
                if isinstance(result, dict) and "content" in result:
                    # result是提取的响应内容，需要转换为SSE流格式
                    async def stream_cached_response():
                        # 发送message_start事件
                        message_start = {
                            "type": "message_start",
                            "message": {
                                "id": result.get("id", ""),
                                "type": "message",
                                "role": "assistant",
                                "content": [],
                                "model": result.get("model", "unknown"),
                                "stop_reason": None,
                                "stop_sequence": None,
                                "usage": result.get("usage", {"input_tokens": 0, "output_tokens": 0})
                            }
                        }
                        from utils.logging.formatters import _safe_json_dumps
                        yield f"event: message_start\ndata: {_safe_json_dumps(message_start)}\n\n"
                        
                        # 处理内容块
                        content_blocks = result.get("content", [])
                        for i, block in enumerate(content_blocks):
                            if block.get("type") == "text":
                                # 发送content_block_start事件
                                content_block_start = {
                                    "type": "content_block_start",
                                    "index": i,
                                    "content_block": {"type": "text", "text": ""}
                                }
                                yield f"event: content_block_start\ndata: {_safe_json_dumps(content_block_start)}\n\n"
                                
                                # 发送文本内容作为delta
                                text_content = block.get("text", "")
                                if text_content:
                                    content_delta = {
                                        "type": "content_block_delta",
                                        "index": i,  
                                        "delta": {
                                            "type": "text_delta",
                                            "text": text_content
                                        }
                                    }
                                    yield f"event: content_block_delta\ndata: {_safe_json_dumps(content_delta)}\n\n"
                                
                                # 发送content_block_stop事件
                                content_block_stop = {
                                    "type": "content_block_stop",
                                    "index": i
                                }
                                yield f"event: content_block_stop\ndata: {_safe_json_dumps(content_block_stop)}\n\n"
                        
                        # 发送message_delta和message_stop事件
                        message_delta = {
                            "type": "message_delta",
                            "delta": {
                                "stop_reason": result.get("stop_reason", "end_turn"),
                                "stop_sequence": result.get("stop_sequence")
                            }
                        }
                        if "usage" in result:
                            message_delta["usage"] = result["usage"]
                        yield f"event: message_delta\ndata: {_safe_json_dumps(message_delta)}\n\n"
                        
                        message_stop = {"type": "message_stop"}
                        yield f"event: message_stop\ndata: {_safe_json_dumps(message_stop)}\n\n"
                    
                    from fastapi.responses import StreamingResponse
                    return StreamingResponse(
                        stream_cached_response(),
                        media_type="text/event-stream"
                    )
                else:
                    # 如果result不是预期的格式，记录调试信息并返回错误
                    try:
                        from utils.logging.handlers import warning, LogRecord
                        warning(
                            LogRecord(
                                "unexpected_result_format",
                                f"Unexpected result format in duplicate request: type={type(result)}, value={repr(result)[:200]}",
                                request_id,
                                {
                                    "result_type": str(type(result)),
                                    "result_repr": repr(result)[:200],
                                    "is_stream": is_stream,
                                    "signature": signature[:16] + "..."
                                }
                            )
                        )
                    except:
                        pass  # 如果日志记录失败，继续处理
                        
                    error_response = {
                        "type": "error",
                        "error": {
                            "type": "api_error",
                            "message": "Invalid cached response format"
                        }
                    }
                    
                    async def stream_error_response():
                        from utils.logging.formatters import _safe_json_dumps
                        formatted_error_chunk = f"event: error\ndata: {_safe_json_dumps(error_response)}\n\n"
                        yield formatted_error_chunk
                    
                    from fastapi.responses import StreamingResponse
                    return StreamingResponse(
                        stream_error_response(),
                        media_type="text/event-stream"
                    )
            else:
                # 非流式重复请求直接返回JSON响应
                info(
                    LogRecord(
                        LogEvent.REQUEST_COMPLETED.value,
                        "Duplicate request completed via original request (non-stream)",
                        request_id,
                        {"original_request_id": original_request_id, "signature": signature[:16] + "...", "is_stream": is_stream},
                    )
                )
                return result
        except asyncio.CancelledError:
            # 原请求被取消，返回适当的错误响应
            warning(
                LogRecord(
                    LogEvent.REQUEST_FAILURE.value,
                    "Duplicate request failed: original request was cancelled",
                    request_id,
                    {"original_request_id": original_request_id, "signature": signature[:16] + "...", "reason": "cancelled"},
                )
            )
            return JSONResponse(
                status_code=409,
                content={
                    "type": "error",
                    "error": {
                        "type": "request_cancelled",
                        "message": "Original request was cancelled. Please retry your request."
                    }
                }
            )
        except asyncio.TimeoutError:
            # 等待原始请求超时
            timeout_error = Exception(f"Duplicate request timed out waiting for original request (timeout: {timeout}s)")
            info(
                LogRecord(
                    LogEvent.REQUEST_FAILURE.value,
                    f"Duplicate request timed out after {timeout}s",
                    request_id,
                    {"original_request_id": original_request_id, "signature": signature[:16] + "...", "timeout": timeout}
                )
            )
            
            if is_stream:
                # 返回超时错误的流式响应
                error_response = {
                    "type": "error",
                    "error": {
                        "type": "api_error", 
                        "message": "Request timed out waiting for duplicate processing"
                    }
                }
                
                async def stream_timeout_response():
                    from src.utils.logging.formatters import _safe_json_dumps
                    formatted_error_chunk = f"event: error\ndata: {_safe_json_dumps(error_response)}\n\n"
                    yield formatted_error_chunk
                
                from fastapi.responses import StreamingResponse
                return StreamingResponse(
                    stream_timeout_response(),
                    media_type="text/event-stream"
                )
            else:
                # 非流式请求直接抛出异常
                raise timeout_error
                
        except Exception as e:
            # 这里捕获的是真正的异常（比如网络错误等），不是我们设置的Exception对象
            # 对于流式duplicate requests，需要返回StreamingResponse格式的错误
            if is_stream:
                error_response = {
                    "type": "error",
                    "error": {
                        "type": "api_error",
                        "message": str(e)
                    }
                }
                
                async def stream_error_response():
                    formatted_error_chunk = f"event: error\ndata: {json.dumps(error_response)}\n\n"
                    yield formatted_error_chunk
                
                from fastapi.responses import StreamingResponse
                return StreamingResponse(
                    stream_error_response(),
                    media_type="text/event-stream"
                )
            else:
                # 对于非流式请求，重新抛出异常让上层处理器处理
                raise e

    return None






def extract_content_from_sse_chunks(sse_chunks: List[str]) -> Dict[str, Any]:
    """从SSE数据块中提取完整的响应内容"""
    
    content_blocks = []
    usage = {"input_tokens": 0, "output_tokens": 0}
    model = "unknown"
    stop_reason = "end_turn"
    
    for chunk_index, chunk in enumerate(sse_chunks):
        try:
            
            # 处理每个chunk，可能包含多行
            lines = chunk.strip().split('\n')
            for line_index, line in enumerate(lines):
                line = line.strip()
                if line.startswith('data: '):
                    data_str = line[6:]  # 去掉 'data: ' 前缀
                    if data_str.strip() and data_str.strip() != '[DONE]':
                        try:
                            data = json.loads(data_str)
                            
                            if data.get('type') == 'message_start':
                                message = data.get('message', {})
                                model = message.get('model', model)
                                if 'usage' in message:
                                    usage.update(message['usage'])
                            
                            elif data.get('type') == 'content_block_start':
                                content_block = data.get('content_block', {})
                                if content_block.get('type') == 'text':
                                    content_blocks.append({
                                        "type": "text",
                                        "text": ""
                                    })
                            
                            elif data.get('type') == 'content_block_delta':
                                delta = data.get('delta', {})
                                if delta.get('type') == 'text_delta':
                                    text_to_add = delta.get('text', '')
                                    
                                    # 如果没有content_blocks但有text_delta，自动创建一个content block
                                    if not content_blocks:
                                        content_blocks.append({
                                            "type": "text",
                                            "text": ""
                                        })
                                    
                                    content_blocks[-1]['text'] += text_to_add
                            
                            elif data.get('type') == 'message_delta':
                                delta = data.get('delta', {})
                                if 'stop_reason' in delta:
                                    stop_reason = delta['stop_reason']
                                if 'usage' in data:
                                    usage.update(data['usage'])
                        
                        except json.JSONDecodeError as e:
                            from utils.logging.handlers import warning, LogRecord, LogEvent
                            warning(LogRecord(
                                event=LogEvent.REQUEST_FAILURE.value,
                                message="SSE JSON decode error during chunk processing",
                                request_id=None,
                                data={
                                    "chunk_index": chunk_index,
                                    "line_index": line_index,
                                    "error": str(e),
                                    "problematic_line": line[:200] + "..." if len(line) > 200 else line
                                }
                            ))
                            continue
        except Exception as e:
            from utils.logging.handlers import warning, LogRecord, LogEvent
            warning(LogRecord(
                event=LogEvent.REQUEST_FAILURE.value,
                message="SSE chunk processing error",
                request_id=None,
                data={
                    "chunk_index": chunk_index,
                    "error": str(e),
                    "chunk_preview": chunk[:100] + "..." if len(chunk) > 100 else chunk
                }
            ))
            continue
    
    # 记录最终提取结果
    try:
        from utils.logging.handlers import debug, LogRecord, LogEvent
        debug(
            LogRecord(
                event=LogEvent.SSE_EXTRACTION_COMPLETE.value,
                message=f"SSE extraction complete: {len(content_blocks)} content blocks",
                request_id=None,
                data={
                    "content_blocks_count": len(content_blocks),
                    "total_text_length": sum(len(block.get('text', '')) for block in content_blocks),
                    "model": model,
                    "stop_reason": stop_reason,
                    "usage": usage
                }
            )
        )
    except ImportError:
        pass  # Skip logging if not available
    
    return {
        "id": str(uuid.uuid4()),
        "type": "message",
        "role": "assistant",
        "content": content_blocks,
        "model": model,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": usage
    }


