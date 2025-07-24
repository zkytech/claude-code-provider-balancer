"""
FastAPI endpoint handlers for Claude Code Provider Balancer.

This module contains all the route handlers and related request processing logic.
"""

import json
import time
import uuid
from typing import Any, Dict, List, Optional, Union

import httpx
import openai
from fastapi import Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import ValidationError

# Import our modular components
from ..core.provider_manager import ProviderManager, Provider, ProviderType
from ..oauth import OAuthManager
from ..models import (
    MessagesRequest, TokenCountRequest, TokenCountResponse,
    MessagesResponse, AnthropicErrorResponse
)
from ..caching import (
    generate_request_signature, handle_duplicate_request,
    cleanup_stuck_requests, simulate_testing_delay,
    complete_and_cleanup_request, extract_content_from_sse_chunks
)
from ..utils.validation import validate_provider_health
from ..conversion import (
    get_token_encoder, count_tokens_for_anthropic_request,
    convert_anthropic_to_openai_messages, convert_anthropic_tools_to_openai,
    convert_anthropic_tool_choice_to_openai, convert_openai_to_anthropic_response,
    get_anthropic_error_details_from_exc, build_anthropic_error_response
)
from ..core.streaming import (
    create_broadcaster, 
    register_broadcaster, 
    unregister_broadcaster, 
    handle_duplicate_stream_request,
    has_active_broadcaster
)
from ..utils import (
    LogRecord, LogEvent, LogError,
    debug, info, warning, error, critical
)


def _format_duration_for_response(seconds: float) -> str:
    """Format duration in human readable format for API responses"""
    if seconds <= 0:
        return "已过期"
    elif seconds < 60:
        return f"{int(seconds)}秒"
    elif seconds < 3600:
        return f"{int(seconds // 60)}分钟"
    else:
        return f"{int(seconds // 3600)}小时{int((seconds % 3600) // 60)}分钟"


def _create_request_summary(request_data: Dict[str, Any]) -> str:
    """Create a summary of the request for logging"""
    model = request_data.get("model", "unknown")
    messages = request_data.get("messages", [])
    message_count = len(messages)
    
    if message_count == 0:
        return f"Model: {model}, No messages"
    
    last_message = messages[-1] if messages else {}
    content = last_message.get("content", "")
    if isinstance(content, list):
        content = " ".join([str(item.get("text", "")) for item in content if isinstance(item, dict)])
    
    content_preview = str(content)[:50] + ("..." if len(str(content)) > 50 else "")
    return f"Model: {model}, Messages: {message_count}, Last: {content_preview}"


def _create_body_summary(body: bytes, max_length: int = 200) -> str:
    """Create a safe summary of request body for logging"""
    try:
        body_str = body.decode('utf-8')
        
        # Try to parse as JSON for better formatting
        try:
            body_dict = json.loads(body_str)
            
            # Extract key information
            model = body_dict.get('model', 'unknown')
            
            # Handle messages
            messages = body_dict.get('messages', [])
            if messages:
                last_msg = messages[-1]
                role = last_msg.get('role', 'unknown')
                content = last_msg.get('content', '')
                
                # Handle different content types
                if isinstance(content, str):
                    content_preview = content[:100] + '...' if len(content) > 100 else content
                elif isinstance(content, list):
                    # Extract text from content blocks
                    text_parts = []
                    for item in content:
                        if isinstance(item, dict) and item.get('type') == 'text':
                            text_parts.append(item.get('text', ''))
                    content_preview = ' '.join(text_parts)[:100]
                    if len(' '.join(text_parts)) > 100:
                        content_preview += '...'
                else:
                    content_preview = str(content)[:100]
                
                summary = f"Model: {model}, Messages: {len(messages)}, Last: {role}: {content_preview}"
            else:
                summary = f"Model: {model}, No messages"
            
            # Add other important fields
            if 'max_tokens' in body_dict:
                summary += f", Max tokens: {body_dict['max_tokens']}"
            if 'stream' in body_dict:
                summary += f", Stream: {body_dict['stream']}"
            
            return summary[:max_length]
            
        except json.JSONDecodeError:
            # If not valid JSON, just truncate the string
            return body_str[:max_length] + ('...' if len(body_str) > max_length else '')
            
    except UnicodeDecodeError:
        return f"<Binary data, {len(body)} bytes>"
    except Exception as e:
        return f"<Error creating summary: {e}>"


def _log_and_return_error_response(
    request: Request, 
    exception: Exception, 
    request_id: str, 
    status_code: int = 500
) -> JSONResponse:
    """Log error and return structured error response"""
    error_details = get_anthropic_error_details_from_exc(exception)
    
    error(LogRecord(
        event="request_error",
        message=f"Request failed: {str(exception)}",
        request_id=request_id,
        data={
            "error_type": type(exception).__name__,
            "error_message": str(exception),
            "status_code": status_code,
            "path": str(request.url.path),
            "method": request.method,
            "error_details": error_details
        }
    ))
    
    # Return anthropic-style error response
    anthropic_error = build_anthropic_error_response(
        error_type=error_details.get("type", "api_error"),
        message=error_details.get("message", str(exception))
    )
    
    return JSONResponse(
        status_code=status_code,
        content=anthropic_error
    )


# This will store references to manager instances
_provider_manager: Optional[ProviderManager] = None
_oauth_manager: Optional[OAuthManager] = None
_settings: Optional[Dict] = None


def init_endpoint_dependencies(provider_manager: ProviderManager, oauth_manager: OAuthManager, settings: Dict):
    """Initialize dependencies needed by endpoints"""
    global _provider_manager, _oauth_manager, _settings
    _provider_manager = provider_manager
    _oauth_manager = oauth_manager  
    _settings = settings


# Placeholder for endpoint functions - they will be added in the next step
# This file will be expanded with all the actual endpoint handlers