"""Error handling utilities for API conversions."""

import json
from typing import Optional, Tuple

import openai
from fastapi.responses import JSONResponse

try:
    from models import AnthropicErrorType, ProviderErrorMetadata, AnthropicErrorDetail, AnthropicErrorResponse
except ImportError:
    try:
        from models.errors import AnthropicErrorType, ProviderErrorMetadata, AnthropicErrorDetail, AnthropicErrorResponse
    except ImportError:
        # Fallback implementations
        class AnthropicErrorType:
            AUTHENTICATION = "authentication_error"
            PERMISSION = "permission_error"
            NOT_FOUND = "not_found_error"
            RATE_LIMIT = "rate_limit_error"
            INVALID_REQUEST = "invalid_request_error"
            API_ERROR = "api_error"
        
        class ProviderErrorMetadata:
            def __init__(self, provider_name, raw_error):
                self.provider_name = provider_name
                self.raw_error = raw_error
        
        class AnthropicErrorDetail:
            def __init__(self, type, message, provider=None, provider_message=None, provider_code=None):
                self.type = type
                self.message = message
                self.provider = provider
                self.provider_message = provider_message
                self.provider_code = provider_code
            
            def dict(self):
                return {
                    "type": self.type,
                    "message": self.message,
                    "provider": self.provider,
                    "provider_message": self.provider_message,
                    "provider_code": self.provider_code
                }
        
        class AnthropicErrorResponse:
            def __init__(self, type, error):
                self.type = type
                self.error = error
            
            def dict(self):
                return {
                    "type": self.type,
                    "error": self.error.dict()
                }


def get_anthropic_error_details_from_exc(
    exc: Exception,
) -> Tuple[AnthropicErrorType, str, int, Optional[ProviderErrorMetadata]]:
    """Maps caught exceptions to Anthropic error type, message, status code, and provider details."""
    
    provider_details = None
    
    if isinstance(exc, openai.APIError):
        # Extract provider details from OpenAI errors
        provider_details = ProviderErrorMetadata(
            provider_name="openai",
            raw_error={
                "type": type(exc).__name__,
                "message": str(exc),
                "code": getattr(exc, 'code', None),
                "status_code": getattr(exc, 'status_code', None),
            }
        )
        
        if isinstance(exc, openai.AuthenticationError):
            return AnthropicErrorType.AUTHENTICATION, str(exc), 401, provider_details
        elif isinstance(exc, openai.PermissionDeniedError):
            return AnthropicErrorType.PERMISSION, str(exc), 403, provider_details
        elif isinstance(exc, openai.NotFoundError):
            return AnthropicErrorType.NOT_FOUND, str(exc), 404, provider_details
        elif isinstance(exc, openai.RateLimitError):
            return AnthropicErrorType.RATE_LIMIT, str(exc), 429, provider_details
        elif isinstance(exc, openai.BadRequestError):
            return AnthropicErrorType.INVALID_REQUEST, str(exc), 400, provider_details
        elif isinstance(exc, openai.InternalServerError):
            return AnthropicErrorType.API_ERROR, str(exc), 500, provider_details
        else:
            return AnthropicErrorType.API_ERROR, str(exc), 500, provider_details
    
    # Default handling for other exceptions
    return AnthropicErrorType.API_ERROR, str(exc), 500, provider_details


def format_anthropic_error_sse_event(
    error_type: AnthropicErrorType,
    message: str,
    provider_details: Optional[ProviderErrorMetadata] = None,
) -> str:
    """Formats an error into the Anthropic SSE 'error' event structure."""
    error_detail = AnthropicErrorDetail(
        type=error_type,
        message=message,
        provider=provider_details.provider_name if provider_details else None,
        provider_message=provider_details.raw_error.get("message") if provider_details and provider_details.raw_error else None,
        provider_code=provider_details.raw_error.get("code") if provider_details and provider_details.raw_error else None,
    )
    
    error_response = AnthropicErrorResponse(
        type="error",
        error=error_detail
    )
    
    return f"event: error\ndata: {json.dumps(error_response.dict())}\n\n"


def build_anthropic_error_response(
    error_type: AnthropicErrorType,
    message: str,
    status_code: int,
    provider_details: Optional[ProviderErrorMetadata] = None,
) -> JSONResponse:
    """Creates a JSONResponse with Anthropic-formatted error."""
    error_detail = AnthropicErrorDetail(
        type=error_type,
        message=message,
        provider=provider_details.provider_name if provider_details else None,
        provider_message=provider_details.raw_error.get("message") if provider_details and provider_details.raw_error else None,
        provider_code=provider_details.raw_error.get("code") if provider_details and provider_details.raw_error else None,
    )
    
    error_response = AnthropicErrorResponse(
        type="error",
        error=error_detail
    )
    
    return JSONResponse(
        status_code=status_code,
        content=error_response.dict()
    )