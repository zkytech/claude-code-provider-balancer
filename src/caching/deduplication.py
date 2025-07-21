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

from log_utils.handlers import info

# Global references - set by main application
_provider_manager = None
_make_anthropic_request = None

def set_provider_manager(manager):
    """Set the global provider manager reference"""
    global _provider_manager
    _provider_manager = manager

def get_provider_manager():
    """Get the global provider manager reference"""
    return _provider_manager

def set_make_anthropic_request(func):
    """Set the global make_anthropic_request function reference"""
    global _make_anthropic_request
    _make_anthropic_request = func

def get_make_anthropic_request():
    """Get the global make_anthropic_request function reference"""
    return _make_anthropic_request


# CachedResponse 类已删除，不再需要响应缓存


# Global state for caching and deduplication
_pending_requests: Dict[str, Tuple[asyncio.Future, str]] = {}
_duplicate_requests: Dict[str, List[Tuple[asyncio.Future, str, str, float, bool]]] = {}  # signature -> [(future, request_id, original_request_id, timestamp, is_stream), ...]
# 已删除响应缓存机制，只保留去重缓存
_request_cleanup_lock = threading.RLock()


# 响应缓存功能已删除，只保留去重功能


def cleanup_stuck_requests(force_cleanup_all: bool = False):
    """清理卡住的请求（超时但未正确清理的请求）"""
    try:
        provider_manager = get_provider_manager()
    except ImportError:
        provider_manager = None
    try:
        from log_utils.handlers import warning, LogRecord
    except ImportError:
        try:
            from log_utils import warning, LogRecord
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
                        "stuck_request_cleanup",
                        f"Cleaned up stuck request: {reason}",
                        request_id,
                        {
                            "signature": signature[:16] + "...",
                            "reason": reason,
                            "cleanup_method": "manual" if force_cleanup_all else "automatic"
                        }
                    )
                )


def check_cache_size_limit(content: Union[Dict[str, Any], List[str]]) -> bool:
    """响应缓存已删除，此函数为空实现保持接口兼容"""
    return True


async def simulate_testing_delay(request_body: Dict[str, Any], request_id: str):
    """模拟测试延迟，用于测试重试机制"""
    try:
        provider_manager = get_provider_manager()
    except ImportError:
        provider_manager = None
    try:
        from log_utils.handlers import info, LogRecord
    except ImportError:
        try:
            from log_utils import info, LogRecord
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

    # 将数据转换为可哈希的字符串
    signature_str = json.dumps(signature_data, sort_keys=True, separators=(',', ':'))

    # 生成 SHA256 哈希
    signature_hash = hashlib.sha256(signature_str.encode('utf-8')).hexdigest()

    # 添加调试日志
    try:
        from log_utils.handlers import debug, LogRecord
    except ImportError:
        try:
            from log_utils import debug, LogRecord
        except ImportError:
            debug = lambda x: None
            LogRecord = dict
    
    debug(
        LogRecord(
            "signature_generated",
            f"Generated signature: {signature_hash[:16]}... for data: {signature_str[:200]}...",
            None,
            {
                "signature": signature_hash,
                "signature_data": signature_str,
                "include_max_tokens": include_max_tokens
            }
        )
    )

    return signature_hash


def cleanup_completed_request(signature: str):
    """清理已完成的请求"""
    with _request_cleanup_lock:
        if signature in _pending_requests:
            del _pending_requests[signature]


def complete_and_cleanup_request(signature: str, result: Any, cache_content: Optional[Union[Dict[str, Any], List[str]]] = None, is_streaming: bool = False, provider_name: Optional[str] = None):
    """完成请求并清理去重状态"""
    try:
        from log_utils.handlers import debug, info, error, LogRecord
    except ImportError:
        try:
            from log_utils import debug, info, error, LogRecord
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
                
                # 处理所有等待中的duplicate requests，只响应每个original_request_id的最新请求
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
                            cleanup_reason = "streaming_completed"
                            message = f"Streaming request completed and cleaned up (duplicate request cleared)"
                        else:
                            cleanup_reason = "request_completed"
                            message = f"Request completed and cleaned up (duplicate request cleared)"
                    else:
                        cleanup_reason = "request_completed"
                        message = f"Request completed and cleaned up (duplicate request cleared)"
                    
                    info(
                        LogRecord(
                            "request_cleanup",
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
                            "request_cleanup_skip",
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


async def debug_compare_provider_response(request_data: Dict[str, Any], signature: str, request_id: str, is_stream: bool = False) -> None:
    """调试函数：将重复请求转发给provider并记录响应，用于对比缓存数据"""
    try:
        provider_manager = get_provider_manager()
    except ImportError:
        provider_manager = None
    try:
        from log_utils.handlers import info, warning, LogRecord
    except ImportError:
        try:
            from log_utils import info, warning, LogRecord
        except ImportError:
            info = warning = lambda x: None
            LogRecord = dict
    make_anthropic_request = get_make_anthropic_request()
    
    try:
        # 检查 provider_manager 是否为 None
        if provider_manager is None:
            warning(
                LogRecord(
                    "debug_provider_request_error",
                    "Debug provider request skipped: provider_manager is None",
                    request_id,
                    {"signature": signature[:16] + "..."}
                )
            )
            return
            
        # 选择一个provider来获取真实响应
        model_provider_options = provider_manager.select_model_and_provider_options(request_data.get("model", "claude-3-5-sonnet-20241022"))
        if not model_provider_options:
            return
        
        _, selected_provider = model_provider_options[0]  # 使用第一个可用的provider
        
        info(
            LogRecord(
                "debug_provider_request_start",
                f"Starting debug provider request for duplicate comparison",
                request_id,
                {
                    "signature": signature[:16] + "...",
                    "provider": selected_provider.name,
                    "is_stream": is_stream,
                    "purpose": "duplicate_response_debugging"
                }
            )
        )
        
        # 转发到provider获取真实响应
        debug_response = await make_anthropic_request(
            selected_provider, 
            request_data, 
            f"{request_id}_debug", 
            stream=is_stream
        )
        
        if is_stream:
            # 对于流式响应，收集所有chunks
            debug_chunks = []
            if hasattr(debug_response, 'aiter_lines'):
                async for line in debug_response.aiter_lines():
                    if line:
                        debug_chunks.append(f"{line}\n")
            
            # 从debug chunks中提取内容
            from .cache_serving import extract_content_from_sse_chunks
            debug_extracted = extract_content_from_sse_chunks(debug_chunks)
            
            info(
                LogRecord(
                    "debug_provider_response_stream",
                    f"Debug provider streaming response collected",
                    request_id,
                    {
                        "signature": signature[:16] + "...",
                        "provider": selected_provider.name,
                        "debug_chunks_count": len(debug_chunks),
                        "debug_extracted": debug_extracted,
                        "debug_chunks_sample": debug_chunks[:5] if debug_chunks else []
                    }
                )
            )
        else:
            # 非流式响应
            debug_content = debug_response.json() if hasattr(debug_response, 'json') else debug_response
            
            info(
                LogRecord(
                    "debug_provider_response_nonstream",
                    f"Debug provider non-streaming response collected",
                    request_id,
                    {
                        "signature": signature[:16] + "...",
                        "provider": selected_provider.name,
                        "debug_content": debug_content
                    }
                )
            )
            
    except Exception as e:
        warning(
            LogRecord(
                "debug_provider_request_error",
                f"Debug provider request failed: {str(e)}",
                request_id,
                {
                    "signature": signature[:16] + "...",
                    "error": str(e)
                }
            )
        )


async def handle_duplicate_request(signature: str, request_id: str, is_stream: bool = False, request_data: Dict[str, Any] = None) -> Optional[Any]:
    """处理重复请求，如果是重复请求则等待原请求完成"""
    try:
        from log_utils.handlers import info, warning, LogRecord, LogEvent
    except ImportError:
        try:
            from log_utils import info, warning, LogRecord, LogEvent
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
                        LogEvent.REQUEST_RECEIVED.value,
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
            result = await future_to_wait
            
            # 响应缓存已删除，直接返回等待的结果
            
            # 如果没有缓存，使用原来的逻辑（向后兼容）
            if isinstance(result, str) and result.startswith("streaming_"):
                return JSONResponse(
                    status_code=409,
                    content={
                        "type": "error",
                        "error": {
                            "type": "duplicate_request_error",
                            "message": "Duplicate request detected but no cached content available. Please retry your request."
                        }
                    }
                )
            
            info(
                LogRecord(
                    LogEvent.REQUEST_COMPLETED.value,
                    "Duplicate request completed via original request",
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
        except Exception as e:
            # 原请求失败，重复请求也应该收到相同的错误
            info(
                LogRecord(
                    LogEvent.REQUEST_FAILURE.value,
                    "Duplicate request failed via original request",
                    request_id,
                    {"original_request_id": original_request_id, "signature": signature[:16] + "...", "error": str(e)},
                )
            )
            raise e

    return None


def update_response_cache(signature: str, collected_chunks: List[str], is_streaming: bool, request_id: str, provider_name: Optional[str] = None):
    """响应缓存已删除，此函数为空实现保持接口兼容"""
    pass


def validate_response_quality(collected_chunks: List[str], provider_name: str, request_id: str, http_status_code: Optional[int] = None) -> bool:
    """增强的响应质量验证，支持Anthropic和OpenAI格式"""
    try:
        from log_utils.handlers import warning, debug, LogRecord
    except ImportError:
        try:
            from log_utils import warning, debug, LogRecord
        except ImportError:
            warning = debug = lambda x: None
            LogRecord = dict
    
    # Skip quality validation for HTTP error status codes
    if http_status_code is not None and http_status_code >= 400:
        debug(
            LogRecord(
                "response_quality_check_skip_http_error",
                f"Skipping quality validation due to HTTP error status {http_status_code} from provider: {provider_name}",
                request_id,
                {"provider": provider_name, "http_status_code": http_status_code}
            )
        )
        return False
    
    if not collected_chunks:
        warning(
            LogRecord(
                "response_quality_check_empty",
                f"Empty response detected from provider: {provider_name}",
                request_id,
                {"provider": provider_name, "chunk_count": 0}
            )
        )
        return False
    
    full_content = "".join(collected_chunks)
    
    # Check for HTTP error responses in content (e.g., "503 Service Unavailable")
    error_indicators = ["503 Service Unavailable", "502 Bad Gateway", "500 Internal Server Error", 
                       "504 Gateway Timeout", "404 Not Found", "401 Unauthorized", "403 Forbidden"]
    if any(error_msg in full_content for error_msg in error_indicators):
        warning(
            LogRecord(
                "response_quality_check_http_error_in_content",
                f"HTTP error detected in response content from provider: {provider_name}",
                request_id,
                {
                    "provider": provider_name, 
                    "chunk_count": len(collected_chunks),
                    "content_preview": full_content[:200] + "..." if len(full_content) > 200 else full_content
                }
            )
        )
        return False
    
    # 基础格式检查：必须包含有效的SSE格式
    if not any(line.startswith("data:") for line in full_content.split('\n')):
        warning(
            LogRecord(
                "response_quality_check_no_sse",
                f"No valid SSE format detected from provider: {provider_name}",
                request_id,
                {
                    "provider": provider_name, 
                    "chunk_count": len(collected_chunks),
                    "content_preview": full_content[:200] + "..." if len(full_content) > 200 else full_content
                }
            )
        )
        return False
    
    # 检查是否包含明显的错误响应
    if ("event: error" in full_content) or \
       ('"error"' in full_content and '"type"' in full_content and len(full_content) < 500):
        warning(
            LogRecord(
                "response_quality_check_error",
                f"Error response detected from provider: {provider_name}",
                request_id,
                {
                    "provider": provider_name, 
                    "chunk_count": len(collected_chunks),
                    "content_preview": full_content[:200] + "..." if len(full_content) > 200 else full_content
                }
            )
        )
        return False
    
    # 检查完整性标志（支持Anthropic和OpenAI格式）
    has_completion_marker = any(marker in full_content for marker in [
        "event: message_stop",           # Anthropic
        "event: content_block_stop",     # Anthropic 
        "stop_reason",                   # Anthropic
        '"type": "message_stop"',        # Anthropic
        '"finish_reason"',               # OpenAI
        'data: [DONE]'                   # OpenAI
    ])
    
    if not has_completion_marker:
        warning(
            LogRecord(
                "response_quality_check_incomplete",
                f"Response appears incomplete from provider: {provider_name}",
                request_id,
                {
                    "provider": provider_name, 
                    "chunk_count": len(collected_chunks),
                    "has_completion_marker": has_completion_marker,
                    "content_length": len(full_content)
                }
            )
        )
        return False
    
    # 尝试解析为结构化响应并验证内容
    total_text_length = 0  # 初始化变量
    try:
        extracted_content = extract_content_from_sse_chunks(collected_chunks)
        
            
    except Exception as e:
        warning(
            LogRecord(
                "response_quality_check_parse_error",
                f"Failed to parse response from provider: {provider_name}",
                request_id,
                {
                    "provider": provider_name,
                    "error": str(e),
                    "content_preview": full_content[:200] + "..." if len(full_content) > 200 else full_content
                }
            )
        )
        return False
    
    debug(
        LogRecord(
            "response_quality_check_passed",
            f"Response quality validation passed for provider: {provider_name}",
            request_id,
            {
                "provider": provider_name, 
                "chunk_count": len(collected_chunks),
                "has_completion_marker": has_completion_marker,
                "content_length": len(full_content),
                "total_text_length": total_text_length
            }
        )
    )
    return True


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
                            import logging
                            logging.warning(json.dumps({
                                "event": "sse_json_decode_error",
                                "chunk_index": chunk_index,
                                "line_index": line_index,
                                "error": str(e),
                                "problematic_line": line[:200] + "..." if len(line) > 200 else line
                            }, ensure_ascii=False))
                            continue
        except Exception as e:
            import logging
            logging.warning(json.dumps({
                "event": "sse_chunk_processing_error",
                "chunk_index": chunk_index,
                "error": str(e),
                "chunk_preview": chunk[:100] + "..." if len(chunk) > 100 else chunk
            }, ensure_ascii=False))
            continue
    
    # 记录最终提取结果
    try:
        from log_utils.handlers import debug, LogRecord
        debug(
            LogRecord(
                event="sse_extraction_complete",
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


