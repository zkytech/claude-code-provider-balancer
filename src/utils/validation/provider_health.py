"""Provider health validation utilities."""

from typing import List, Optional, Tuple, Union, Dict, Any
import json


def map_exception_to_failover_type(exception_type: str, exception_message: str = "") -> Optional[str]:
    """将异常类型映射到failover错误类型
    
    Args:
        exception_type: 异常类型名称 (如 'ConnectError', 'TimeoutError')
        exception_message: 异常消息内容
        
    Returns:
        对应的failover错误类型，如果不匹配则返回None
    """
    # 网络连接错误映射
    connection_error_types = {
        'ConnectError': 'connection_error',
        'ConnectionError': 'connection_error', 
        'OSError': 'connection_error',
        'socket.error': 'connection_error',
        'SSLError': 'ssl_error',
        'SSLException': 'ssl_error',
        'CertificateError': 'ssl_error',
        'NetworkError': 'network_unreachable',
    }
    
    # 网络超时错误映射
    timeout_error_types = {
        'TimeoutError': 'connect_timeout',
        'ConnectTimeout': 'connect_timeout',
        'ReadTimeout': 'read_timeout',
        'Timeout': 'read_timeout',
        'asyncio.TimeoutError': 'read_timeout',
        'PoolTimeout': 'pool_timeout',
    }
    
    # HTTP错误映射 
    http_error_types = {
        'HTTPError': 'internal_server_error',
        'ServerError': 'internal_server_error',
        'BadGateway': 'bad_gateway',
        'ServiceUnavailable': 'service_unavailable',
    }
    
    # Stream特定错误映射
    stream_error_types = {
        'StreamError': 'stream_transmission_error',
        'ChunkedEncodingError': 'stream_transmission_error',
        'StreamInterrupted': 'stream_interrupted',
        'IncompleteRead': 'stream_transmission_error',
    }
    
    # 合并所有映射
    all_mappings = {
        **connection_error_types,
        **timeout_error_types, 
        **http_error_types,
        **stream_error_types
    }
    
    # 直接匹配异常类型
    if exception_type in all_mappings:
        return all_mappings[exception_type]
    
    # 基于异常消息的模糊匹配
    exception_message_lower = exception_message.lower()
    if 'timeout' in exception_message_lower:
        return 'read_timeout'
    elif 'connection' in exception_message_lower:
        return 'connection_error'
    elif 'ssl' in exception_message_lower:
        return 'ssl_error'
    elif 'stream' in exception_message_lower:
        return 'stream_transmission_error'
    
    return None


def validate_provider_health(response_content: Union[List[str], str, Dict[str, Any]], 
                           provider_name: str, 
                           request_id: str, 
                           http_status_code: Optional[int] = None, 
                           failover_error_types: Optional[List[str]] = None,
                           failover_http_codes: Optional[List[int]] = None,
                           exception_info: Optional[Dict[str, Any]] = None) -> Tuple[bool, Optional[str]]:
    """检查provider响应是否健康，判断是否命中failover规则
    
    Args:
        response_content: 响应内容 - 可以是SSE chunks或单个响应
        provider_name: provider名称
        request_id: 请求ID
        http_status_code: HTTP状态码
        failover_error_types: 配置的failover错误类型
        failover_http_codes: 配置的failover HTTP状态码
        exception_info: 异常信息字典，包含error_type和error_message
        
    Returns:
        Tuple[bool, Optional[str]]: (provider是否不健康, 错误类型)
    """
    try:
        from utils.logging.handlers import warning, debug, LogRecord, LogEvent
    except ImportError:
        try:
            from utils.logging import warning, debug, LogRecord, LogEvent
        except ImportError:
            warning = debug = lambda x: None
            LogRecord = dict
            class MockLogEvent:
                PROVIDER_HEALTH_CHECK_SSE_ERROR = type('MockValue', (), {'value': 'provider_health_check_sse_error'})()
            LogEvent = MockLogEvent()
    
    failover_error_types = failover_error_types or []
    failover_http_codes = failover_http_codes or []
    
    # 0. 优先检查异常信息（如果提供）
    if exception_info:
        exception_type = exception_info.get('error_type', '')
        exception_message = exception_info.get('error_message', '')
        
        # 映射异常类型到failover错误类型
        mapped_error_type = map_exception_to_failover_type(exception_type, exception_message)
        
        if mapped_error_type and mapped_error_type in failover_error_types:
            warning(
                LogRecord(
                    "provider_health_check_exception",
                    f"Exception '{exception_type}' indicates unhealthy provider: {provider_name}",
                    request_id,
                    {
                        "provider": provider_name,
                        "exception_type": exception_type,
                        "exception_message": exception_message,
                        "mapped_error_type": mapped_error_type,
                        "unhealthy_reason": "exception_based"
                    }
                )
            )
            return True, mapped_error_type
        else:
            debug(
                LogRecord(
                    "provider_health_check_exception_ignored", 
                    f"Exception '{exception_type}' not mapped to failover error type or not in failover list: {provider_name}",
                    request_id,
                    {
                        "provider": provider_name,
                        "exception_type": exception_type,
                        "mapped_error_type": mapped_error_type,
                        "failover_error_types": failover_error_types
                    }
                )
            )
    
    # 统一处理不同类型的响应内容
    if isinstance(response_content, list):
        # Stream response (List[str])
        collected_chunks = response_content
        full_content = "".join(collected_chunks)
    elif isinstance(response_content, str):
        # String response
        collected_chunks = [response_content]
        full_content = response_content
    elif isinstance(response_content, dict):
        # Dict response (convert to JSON string for analysis)
        full_content = json.dumps(response_content)
        collected_chunks = [full_content]
    else:
        # Unknown type, convert to string
        full_content = str(response_content)
        collected_chunks = [full_content]
    
    # 1. 检查HTTP状态码是否命中failover规则
    if http_status_code is not None and http_status_code in failover_http_codes:
        warning(
            LogRecord(
                "provider_health_check_http_code",
                f"HTTP status {http_status_code} indicates unhealthy provider: {provider_name}",
                request_id,
                {"provider": provider_name, "http_status_code": http_status_code, "unhealthy_reason": "http_code"}
            )
        )
        return True, f"http_status_{http_status_code}"
    
    # 2. 检查空响应（如果在failover规则中）
    if not collected_chunks or not full_content.strip():
        if "empty_response" in failover_error_types:
            warning(
                LogRecord(
                    "provider_health_check_empty",
                    f"Empty response indicates unhealthy provider: {provider_name}",
                    request_id,
                    {"provider": provider_name, "chunk_count": len(collected_chunks), "unhealthy_reason": "empty_response"}
                )
            )
            return True, "empty_response"
        else:
            debug(
                LogRecord(
                    "provider_health_check_empty_ignored",
                    f"Empty response detected but not configured as unhealthy for provider: {provider_name}",
                    request_id,
                    {"provider": provider_name, "chunk_count": len(collected_chunks)}
                )
            )
            return False, None
    
    # 3. 检查内容中的HTTP错误（映射到failover错误类型）
    http_error_mapping = {
        "503 Service Unavailable": "service_unavailable",
        "502 Bad Gateway": "bad_gateway", 
        "500 Internal Server Error": "internal_server_error",
        "504 Gateway Timeout": "gateway_timeout",
        "404 Not Found": "not_found",
        "401 Unauthorized": "unauthorized",
        "403 Forbidden": "forbidden",
        "429 Too Many Requests": "too_many_requests"
    }
    
    for error_msg, error_type in http_error_mapping.items():
        if error_msg in full_content and error_type in failover_error_types:
            warning(
                LogRecord(
                    "provider_health_check_http_error_in_content",
                    f"HTTP error '{error_msg}' in content indicates unhealthy provider: {provider_name}",
                    request_id,
                    {
                        "provider": provider_name, 
                        "chunk_count": len(collected_chunks),
                        "error_type": error_type,
                        "unhealthy_reason": "http_error_in_content",
                        "content_preview": full_content[:200] + "..." if len(full_content) > 200 else full_content
                    }
                )
            )
            return True, error_type
    
    # 4. 检查标准格式错误（SSE event: error）
    if "event: error" in full_content and "invalid_request_error" in failover_error_types:
        warning(
            LogRecord(
                LogEvent.PROVIDER_HEALTH_CHECK_SSE_ERROR.value,
                f"SSE error event indicates unhealthy provider: {provider_name}",
                request_id,
                {
                    "provider": provider_name, 
                    "chunk_count": len(collected_chunks),
                    "error_type": "invalid_request_error",
                    "unhealthy_reason": "sse_error_event",
                    "content_preview": full_content[:200] + "..." if len(full_content) > 200 else full_content
                }
            )
        )
        return True, "invalid_request_error"
    
    # 5. 检查JSON错误响应（HTTP 200但内容是错误）
    if not any(line.startswith("data:") for line in full_content.split('\n')):
        try:
            json_content = json.loads(full_content.strip())
            if isinstance(json_content, dict) and "error" in json_content:
                # Handle nested error structure (Anthropic format)
                error_obj = json_content.get("error", {})
                if isinstance(error_obj, dict):
                    error_type = error_obj.get("type", "unknown")
                    error_message = error_obj.get("message", "")
                else:
                    # Fallback for simple error format
                    error_type = str(error_obj)
                    error_message = json_content.get("message", "")
                
                # 检查配置文件中定义的错误类型
                for failover_type in failover_error_types:
                    # 检查错误类型或错误消息中是否包含配置的错误类型
                    if failover_type.lower() in error_type.lower() or failover_type.lower() in error_message.lower():
                        warning(
                            LogRecord(
                                "provider_health_check_json_error",
                                f"Error type '{failover_type}' found in response indicates unhealthy provider: {provider_name}",
                                request_id,
                                {
                                    "provider": provider_name, 
                                    "chunk_count": len(collected_chunks),
                                    "error_type": failover_type,
                                    "original_error": error_type,
                                    "error_message": error_message,
                                    "unhealthy_reason": "json_error_response",
                                    "content_preview": full_content[:200] + "..." if len(full_content) > 200 else full_content
                                }
                            )
                        )
                        return True, failover_type
        except (json.JSONDecodeError, ValueError):
            # 不是JSON格式，继续后续检查
            pass
    
    # 6. 检查无效SSE格式（仅限于stream响应）
    if isinstance(response_content, list) and not any(line.startswith("data:") for line in full_content.split('\n')):
        if "invalid_response_format" in failover_error_types:
            warning(
                LogRecord(
                    "provider_health_check_invalid_sse",
                    f"Invalid SSE format indicates unhealthy provider: {provider_name}",
                    request_id,
                    {
                        "provider": provider_name, 
                        "chunk_count": len(collected_chunks),
                        "error_type": "invalid_response_format",
                        "unhealthy_reason": "invalid_sse_format",
                        "content_preview": full_content[:200] + "..." if len(full_content) > 200 else full_content
                    }
                )
            )
            return True, "invalid_response_format"
    
    # 7. 检查响应不完整（仅限于stream响应）
    if isinstance(response_content, list) and "incomplete_response" in failover_error_types:
        completion_markers = [
            "event: message_stop",           # Anthropic
            "event: content_block_stop",     # Anthropic 
            "stop_reason",                   # Anthropic
            '"type": "message_stop"',        # Anthropic
            '"finish_reason"',               # OpenAI
            'data: [DONE]'                   # OpenAI
        ]
        
        has_completion_marker = any(marker in full_content for marker in completion_markers)
        if not has_completion_marker:
            warning(
                LogRecord(
                    "provider_health_check_incomplete",
                    f"Incomplete stream response indicates unhealthy provider: {provider_name}",
                    request_id,
                    {
                        "provider": provider_name, 
                        "chunk_count": len(collected_chunks),
                        "error_type": "incomplete_response",
                        "unhealthy_reason": "missing_completion_marker",
                        "content_length": len(full_content),
                        "content_preview": full_content[:200] + "..." if len(full_content) > 200 else full_content
                    }
                )
            )
            return True, "incomplete_response"
    
    # 没有检测到不健康指标
    debug(
        LogRecord(
            "provider_health_check_passed",
            f"Provider health check passed: {provider_name}",
            request_id,
            {
                "provider": provider_name, 
                "chunk_count": len(collected_chunks),
                "content_length": len(full_content),
                "response_type": type(response_content).__name__
            }
        )
    )
    return False, None