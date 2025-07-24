"""Response validation utilities for streaming responses."""

from typing import Any, Dict, List, Optional


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
                {
                    "provider": provider_name, 
                    "chunk_count": 0,
                    "content_preview": ""
                }
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
    
    # 检查是否包含明显的错误响应
    # 1. 标准格式错误检查
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
    
    # 2. 纯JSON错误响应检查（如 {"error": "...", "message": "..."}）
    # 这种情况通常发生在provider返回HTTP 200但内容是错误信息
    if not any(line.startswith("data:") for line in full_content.split('\n')):
        try:
            import json
            # 尝试解析为JSON
            json_content = json.loads(full_content.strip())
            if isinstance(json_content, dict) and "error" in json_content:
                warning(
                    LogRecord(
                        "response_quality_check_json_error",
                        f"JSON error response detected from provider: {provider_name}",
                        request_id,
                        {
                            "provider": provider_name, 
                            "chunk_count": len(collected_chunks),
                            "error_type": json_content.get("error", "unknown"),
                            "error_message": json_content.get("message", "no message"),
                            "content_preview": full_content[:200] + "..." if len(full_content) > 200 else full_content
                        }
                    )
                )
                return False
        except (json.JSONDecodeError, ValueError):
            # 不是JSON格式，继续后续检查
            pass
    
    # 3. SSE格式检查（仅当不是JSON错误响应时）
    if not any(line.startswith("data:") for line in full_content.split('\n')):
        # 如果既不是JSON错误也不是SSE格式，那就是无效响应
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
                    "content_length": len(full_content),
                    "content_preview": full_content[:200] + "..." if len(full_content) > 200 else full_content
                }
            )
        )
        return False
    
    # 尝试解析为结构化响应并验证内容
    total_text_length = 0  # 初始化变量
    try:
        from deduplication import extract_content_from_sse_chunks
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