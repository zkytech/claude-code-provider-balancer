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
                    "error": self.error.model_dump()
                }


def get_anthropic_error_details_from_exc(
    exc: Exception,
) -> Tuple[AnthropicErrorType, str, int, Optional[ProviderErrorMetadata]]:
    """Maps caught exceptions to Anthropic error type, message, status code, and provider details."""
    
    provider_details = None
    
    # Handle httpx.HTTPStatusError (from Anthropic/HTTP providers)
    if hasattr(exc, 'response') and hasattr(exc, 'request'):
        # This is likely an httpx.HTTPStatusError
        response = getattr(exc, 'response', None)
        status_code = getattr(exc, 'status_code', None) or (response.status_code if response else 500)
        
        # Try to extract detailed error from response body
        detailed_message = str(exc)
        provider_name = "unknown"
        
        # Extract provider name from error message if available
        error_str = str(exc)
        if "provider" in error_str:
            # Extract provider name from "HTTP 400 from provider YourAPI" format
            parts = error_str.split("provider")
            if len(parts) > 1:
                provider_part = parts[1].strip().split()
                if provider_part:  # Check if the split result is not empty
                    provider_name = provider_part[0]
        
        if response:
            try:
                # Try to get detailed error from response body
                if hasattr(response, 'text'):
                    response_text = response.text
                elif hasattr(response, 'content'):
                    response_text = response.content.decode('utf-8') if isinstance(response.content, bytes) else str(response.content)
                else:
                    response_text = ""
                
                if response_text:
                    try:
                        # Try to parse as JSON for structured error
                        response_json = json.loads(response_text)
                        if isinstance(response_json, dict):
                            if "error" in response_json:
                                error_detail = response_json["error"]
                                if isinstance(error_detail, dict):
                                    detailed_message = error_detail.get("message", detailed_message)
                                    if "type" in error_detail:
                                        detailed_message = f"{error_detail['type']}: {detailed_message}"
                                else:
                                    detailed_message = str(error_detail)
                            elif "message" in response_json:
                                detailed_message = response_json["message"]
                            elif "detail" in response_json:
                                detailed_message = response_json["detail"]
                    except (json.JSONDecodeError, KeyError):
                        # If not JSON, use the raw text if it's informative
                        if len(response_text.strip()) > 0 and len(response_text) < 1000:
                            detailed_message = f"{detailed_message}. Response: {response_text.strip()}"
            except Exception:
                # If we can't extract response details, use the original error message
                pass
        
        # Create provider details
        provider_details = ProviderErrorMetadata(
            provider_name=provider_name,
            raw_error={
                "type": type(exc).__name__,
                "message": detailed_message,
                "status_code": status_code,
                "original_error": str(exc),
                "response_text": getattr(response, 'text', None) if response else None
            }
        )
        
        # Map HTTP status codes to Anthropic error types
        if status_code == 401:
            return AnthropicErrorType.AUTHENTICATION, detailed_message, 401, provider_details
        elif status_code == 403:
            return AnthropicErrorType.PERMISSION, detailed_message, 403, provider_details
        elif status_code == 404:
            return AnthropicErrorType.NOT_FOUND, detailed_message, 404, provider_details
        elif status_code == 408:
            return AnthropicErrorType.TIMEOUT, detailed_message, 408, provider_details
        elif status_code == 429:
            return AnthropicErrorType.RATE_LIMIT, detailed_message, 429, provider_details
        elif status_code == 400:
            return AnthropicErrorType.INVALID_REQUEST, detailed_message, 400, provider_details
        elif status_code >= 500:
            return AnthropicErrorType.API_ERROR, detailed_message, status_code, provider_details
        else:
            return AnthropicErrorType.API_ERROR, detailed_message, status_code, provider_details
    
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
        content=error_response.model_dump()
    )