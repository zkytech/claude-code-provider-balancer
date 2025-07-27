"""
Message handling business logic for the Claude Code Provider Balancer.
Contains the core logic for processing chat completion requests.
"""

import json
import uuid
import time
import os
from typing import Any, Dict, List, Optional, Union, Tuple

import httpx
import openai
from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from models import TokenCountRequest, TokenCountResponse
from core.provider_manager import ProviderManager, Provider
from caching import (
    complete_and_cleanup_request,
    simulate_testing_delay
)
from conversion import (
    count_tokens_for_anthropic_request,
    get_anthropic_error_details_from_exc, build_anthropic_error_response
)
from utils import (
    LogRecord, LogEvent, info, warning, error, debug,
    create_debug_request_info
)

class MessageHandler:
    """Handles message processing requests."""
    
    def __init__(self, provider_manager: ProviderManager, settings: Any):
        self.provider_manager = provider_manager
        self.settings = settings

    def _create_request_summary(self, raw_body: dict) -> str:
        """Create a concise summary of the request for logging."""
        model = raw_body.get("model", "unknown")
        stream = raw_body.get("stream", False)
        max_tokens = raw_body.get("max_tokens", 0)
        
        # Count messages
        messages_count = 0
        if "messages" in raw_body and isinstance(raw_body["messages"], list):
            messages_count = len(raw_body["messages"])
        
        # Check for tools
        tools_info = ""
        if "tools" in raw_body and isinstance(raw_body["tools"], list):
            tools_info = f", {len(raw_body['tools'])} tools"
        
        # Stream indicator - make it more prominent
        stream_info = " [STREAM]" if stream else " [NON-STREAM]"

        return f"{model}: {messages_count} msgs, max_tokens: {max_tokens}{tools_info}{stream_info}"

    def _create_no_providers_error_message(self, model: str, provider_name: str = None) -> str:
        """Create a unified error message for when no providers are available."""
        if provider_name:
            return f"Provider '{provider_name}' not found, unhealthy, or not configured for model: {model}"
        else:
            return f"All configured providers for model '{model}' are currently unable to process requests."

    def select_model_and_provider_options(self, client_model_name: str, request_id: str, provider_name: Optional[str] = None) -> List[Tuple[str, Provider]]:
        """Selects all available model and provider options for failover."""
        if not self.provider_manager:
            return []
        
        # If provider is specified, return only that provider option
        if provider_name:
            # Find the specified provider
            target_provider = None
            for provider in self.provider_manager.providers:
                if provider.name == provider_name:
                    target_provider = provider
                    break
            
            if not target_provider:
                # Provider not found
                return []
                
            # Check if provider is healthy and enabled
            if not target_provider.enabled or not target_provider.is_healthy(self.provider_manager.get_failure_cooldown()):
                return []
            
            # Find model route for this specific provider
            # Look for the target model in the provider's configured models
            target_model = client_model_name  # Default to passthrough
            
            # Check if there's a specific model mapping for this provider
            for pattern, routes in self.provider_manager.model_routes.items():
                if self.provider_manager._matches_pattern(client_model_name, pattern):
                    for route in routes:
                        if route.provider == provider_name:
                            target_model = route.model if route.model != "passthrough" else client_model_name
                            break
                    break
            
            return [(target_model, target_provider)]
        
        # Default behavior: return all available options for failover
        return self.provider_manager.select_model_and_provider_options(client_model_name)

    async def make_provider_request(self, provider: Provider, endpoint: str, data: Dict[str, Any], request_id: str, stream: bool = False, original_headers: Optional[Dict[str, str]] = None) -> Union[httpx.Response, Dict[str, Any]]:
        """Make a request to a specific provider"""
        url = self.provider_manager.get_request_url(provider, endpoint)
        headers = self.provider_manager.get_provider_headers(provider, original_headers)
        # 根据请求类型获取相应的超时配置
        http_timeouts = self.provider_manager.get_timeouts_for_request(stream)
        
        # 构建httpx超时配置
        timeout_config = httpx.Timeout(
            connect=http_timeouts['connect_timeout'],
            read=http_timeouts['read_timeout'],
            write=http_timeouts['read_timeout'],  # 使用相同的read_timeout作为write_timeout
            pool=http_timeouts['pool_timeout']
        )

        # Configure proxy if specified
        proxy_config = None
        if provider.proxy:
            proxy_config = provider.proxy

        info(
            LogRecord(
                event=LogEvent.PROVIDER_REQUEST.value,
                message=f"Making request to provider: {provider.name}",
                request_id=request_id,
                data={
                    "provider": provider.name, 
                    "type": provider.type.value,
                    "timeouts": http_timeouts
                }
            )
        )

        # Simulate testing delay if configured
        await simulate_testing_delay(data, request_id)

        async with httpx.AsyncClient(timeout=timeout_config, proxy=proxy_config) as client:
            try:
                response = await client.post(url, json=data, headers=headers)
                
                if stream:
                    # For streaming requests, return the response object directly
                    # The caller will handle streaming with aiter_bytes
                    return response
                
                # Check for HTTP error status codes first
                if response.status_code >= 400:
                    # Get response body for detailed error info
                    try:
                        error_response_body = response.json()
                    except:
                        # If response is not JSON, get text content
                        error_response_body = response.text
                    
                    # Log complete error details to file (not console)
                    debug_info = create_debug_request_info(url, headers, data)
                    from utils.logging.handlers import error_file_only
                    error_file_only(
                        LogRecord(
                            event=LogEvent.PROVIDER_HTTP_ERROR_DETAILS.value,
                            message=f"Provider {provider.name} returned HTTP {response.status_code}",
                            request_id=request_id,
                            data={
                                "provider": provider.name,
                                "status_code": response.status_code,
                                "response_headers": dict(response.headers),
                                "response_body": error_response_body,
                                "request_details": debug_info
                            }
                        )
                    )
                    
                    # Create custom exception with status code for failover handling
                    from httpx import HTTPStatusError
                    request_obj = httpx.Request("POST", url)
                    
                    # Extract error message from response body if available
                    error_msg_suffix = ""
                    if error_response_body and isinstance(error_response_body, dict):
                        if "error" in error_response_body:
                            if isinstance(error_response_body["error"], str):
                                error_msg_suffix = f": {error_response_body['error']}"
                            elif isinstance(error_response_body["error"], dict) and "message" in error_response_body["error"]:
                                error_msg_suffix = f": {error_response_body['error']['message']}"
                    
                    http_error = HTTPStatusError(
                        f"HTTP {response.status_code} from provider {provider.name}{error_msg_suffix}",
                        request=request_obj,
                        response=response
                    )
                    # Add status code as attribute for error handling
                    http_error.status_code = response.status_code
                    raise http_error
                
                # Parse response content
                response_data = response.json()
                
                # Check if response contains error even with 200 status code
                if isinstance(response_data, dict) and "error" in response_data:
                    # Create an httpx.HTTPStatusError-like exception with the error info
                    from httpx import HTTPStatusError
                    error_message = response_data.get("error", {}).get("message", "Unknown error from provider")
                    error_type = response_data.get("error", {}).get("type", "unknown_error")
                    
                    # Log detailed request information for API errors (only to file, not console)
                    debug_info = create_debug_request_info(url, headers, data)
                    error(
                        LogRecord(
                            event=LogEvent.PROVIDER_API_ERROR_DETAILS.value,
                            message=f"Provider {provider.name} returned API error: {error_message}",
                            request_id=request_id,
                            data={
                                "provider": provider.name,
                                "error_type": error_type,
                                "error_message": error_message,
                                "status_code": response.status_code,
                                "response_headers": dict(response.headers),
                                "request_details": debug_info,
                                "response_body": response_data
                            }
                        )
                    )
                    
                    # Create a mock request for the exception
                    mock_request = httpx.Request("POST", url)
                    http_error = HTTPStatusError(
                        message=f"Provider returned error: {error_message}",
                        request=mock_request,
                        response=response
                    )
                    http_error.error_type = error_type
                    raise http_error
                    
                return response_data
            
            except Exception as http_error:
                # Log the specific HTTP/connection error before it propagates up
                error_type = type(http_error).__name__
                error(
                    LogRecord(
                        event=LogEvent.PROVIDER_REQUEST_ERROR.value,
                        message=f"Provider {provider.name} request failed: {error_type}: {str(http_error)}",
                        request_id=request_id,
                        data={
                            "provider": provider.name,
                            "error_type": error_type,
                            "error_message": str(http_error),
                            "url": url
                        }
                    )
                )
                raise  # Re-raise the exception to maintain existing error handling flow

    async def make_streaming_request(self, provider: Provider, endpoint: str, data: Dict[str, Any], request_id: str, original_headers: Optional[Dict[str, str]] = None):
        """Make a streaming request to a specific provider using proper streaming context"""
        url = self.provider_manager.get_request_url(provider, endpoint)
        headers = self.provider_manager.get_provider_headers(provider, original_headers)
        # Get streaming timeouts
        http_timeouts = self.provider_manager.get_timeouts_for_request(True)
        
        # Build httpx timeout configuration
        timeout_config = httpx.Timeout(
            connect=http_timeouts['connect_timeout'],
            read=http_timeouts['read_timeout'],
            write=http_timeouts['read_timeout'],
            pool=http_timeouts['pool_timeout']
        )

        # Configure proxy if specified
        proxy_config = None
        if provider.proxy:
            proxy_config = provider.proxy

        info(
            LogRecord(
                event=LogEvent.PROVIDER_REQUEST.value,
                message=f"Making streaming request to provider: {provider.name}",
                request_id=request_id,
                data={
                    "provider": provider.name, 
                    "type": provider.type.value,
                    "timeouts": http_timeouts
                }
            )
        )

        # Simulate testing delay if configured
        await simulate_testing_delay(data, request_id)

        # Use stream context manager for true real-time streaming
        async with httpx.AsyncClient(timeout=timeout_config, proxy=proxy_config) as client:
            async with client.stream("POST", url, json=data, headers=headers) as response:
                # Check for HTTP error status codes first
                if response.status_code >= 400:
                    error_text = await response.aread()
                    
                    # Try to parse error response body to extract specific error message
                    error_msg_suffix = ""
                    try:
                        import json
                        error_response_body = json.loads(error_text.decode('utf-8'))
                        if isinstance(error_response_body, dict) and "error" in error_response_body:
                            if isinstance(error_response_body["error"], str):
                                error_msg_suffix = f": {error_response_body['error']}"
                            elif isinstance(error_response_body["error"], dict) and "message" in error_response_body["error"]:
                                error_msg_suffix = f": {error_response_body['error']['message']}"
                    except:
                        # If parsing fails, just use the raw error text if it's short enough
                        if len(error_text) < 200:
                            error_msg_suffix = f": {error_text.decode('utf-8', errors='ignore')}"
                    
                    from httpx import HTTPStatusError
                    request_obj = httpx.Request("POST", url)
                    http_error = HTTPStatusError(
                        f"HTTP {response.status_code} from provider {provider.name}{error_msg_suffix}",
                        request=request_obj,
                        response=response
                    )
                    http_error.status_code = response.status_code
                    raise http_error
                
                # Return the streaming response context for real-time processing
                yield response

    async def make_anthropic_streaming_request(self, provider: Provider, messages_data: Dict[str, Any], request_id: str, original_headers: Optional[Dict[str, str]] = None):
        """Make a streaming request to an Anthropic-compatible provider"""
        # Always use new streaming method for real-time streaming
        # This ensures tests can detect fake streaming issues
        
        # Use new streaming method for real-time streaming
        async for response in self.make_streaming_request(provider, "v1/messages", messages_data, request_id, original_headers):
            yield response

    async def make_anthropic_request(self, provider: Provider, messages_data: Dict[str, Any], request_id: str, stream: bool = False, original_headers: Optional[Dict[str, str]] = None) -> Union[httpx.Response, Dict[str, Any]]:
        """Make a request to an Anthropic-compatible provider"""
        response = await self.make_provider_request(provider, "v1/messages", messages_data, request_id, stream, original_headers)
        
        
        return response

    async def make_openai_request(self, provider: Provider, openai_params: Dict[str, Any], request_id: str, stream: bool = False, original_headers: Optional[Dict[str, str]] = None) -> Any:
        """Make a request to an OpenAI-compatible provider using openai client"""
        try:
            # Simulate testing delay if configured
            await simulate_testing_delay(openai_params, request_id)
            # Prepare default headers
            default_headers = {
                "HTTP-Referer": self.settings.referrer_url,
                "X-Title": self.settings.app_name,
            }

            # 根据请求类型获取相应的超时配置
            openai_timeouts = self.provider_manager.get_timeouts_for_request(stream)

            info(
                LogRecord(
                    event=LogEvent.PROVIDER_REQUEST.value,
                    message=f"Making request to provider: {provider.name}",
                    request_id=request_id,
                    data={
                        "provider": provider.name, 
                        "type": provider.type.value,
                        "timeouts": openai_timeouts
                    }
                )
            )
            
            # Configure proxy and timeouts for http_client
            http_client = None
            if provider.proxy:
                timeout_config = httpx.Timeout(
                    connect=openai_timeouts['connect_timeout'],
                    read=openai_timeouts['read_timeout'],
                    write=openai_timeouts['read_timeout'],  # 使用相同的read_timeout作为write_timeout
                    pool=openai_timeouts['pool_timeout']
                )
                http_client = httpx.AsyncClient(proxy=provider.proxy, timeout=timeout_config)
            else:
                # Create http_client with timeout even without proxy
                timeout_config = httpx.Timeout(
                    connect=openai_timeouts['connect_timeout'],
                    read=openai_timeouts['read_timeout'],
                    write=openai_timeouts['read_timeout'],  # 使用相同的read_timeout作为write_timeout
                    pool=openai_timeouts['pool_timeout']
                )
                http_client = httpx.AsyncClient(timeout=timeout_config)

            # Handle auth_value passthrough mode
            api_key_value = provider.auth_value
            if provider.auth_value == "passthrough" and original_headers:
                # Extract auth token from original request headers
                for key, value in original_headers.items():
                    if key.lower() == "authorization":
                        if value.lower().startswith("bearer "):
                            api_key_value = value[7:]  # Remove "Bearer " prefix
                        else:
                            api_key_value = value
                        break
                    elif key.lower() == "x-api-key":
                        api_key_value = value
                        break

                # If no valid auth header found, use placeholder
                if api_key_value == "passthrough":
                    api_key_value = "placeholder-key"

            client = openai.AsyncClient(
                api_key=api_key_value,
                base_url=provider.base_url,
                default_headers=default_headers,
                http_client=http_client,
            )

            return await client.chat.completions.create(**openai_params)
        except Exception as e:
            # Log the specific OpenAI client error before it propagates up
            error_type = type(e).__name__
            error(
                LogRecord(
                    event=LogEvent.PROVIDER_REQUEST_ERROR.value,
                    message=f"Provider {provider.name} OpenAI client request failed: {error_type}: {str(e)}",
                    request_id=request_id,
                    data={
                        "provider": provider.name,
                        "error_type": error_type,
                        "error_message": str(e),
                        "base_url": provider.base_url
                    }
                )
            )
            raise e

    async def _log_and_return_error_response(
        self,
        request: Request,
        exc: Exception,
        request_id: str,
        status_code: int = 500,
        signature: str = None,
    ) -> JSONResponse:
        """Log error and return formatted error response."""
        # 统一清理signature，防止duplicate request死锁
        if signature:
            complete_and_cleanup_request(signature, exc, None, False, "error_cleanup")
        
        error_type, message, _, provider_details = get_anthropic_error_details_from_exc(exc)
        
        # Add hint about detailed logs in file only for provider-related errors
        final_message = f"Request failed: {message}"
        
        # Only add file hint for provider errors (not client validation errors)
        is_provider_error = (
            hasattr(exc, 'response') or  # HTTP errors from providers
            'provider' in str(exc).lower() or  # Provider-related errors
            any(keyword in str(exc).lower() for keyword in ['timeout', 'connection', 'network', 'api'])
        )
        
        if is_provider_error:
            if self.settings.log_file_path:
                final_message += f" (详细错误信息请查看日志文件: {self.settings.log_file_path})"
            else:
                final_message += " (详细错误信息请查看日志文件: logs/logs.jsonl)"
        
        error(
            LogRecord(
                event=LogEvent.REQUEST_FAILURE.value,
                message=final_message,
                request_id=request_id,
                data={"status_code": status_code, "error_type": error_type.value},
            ),
            exc=exc,
        )
        
        return build_anthropic_error_response(error_type, message, status_code, provider_details)

    async def count_tokens(self, request: Request) -> TokenCountResponse:
        """Estimates token count for given Anthropic messages and system prompt."""
        request_id = str(uuid.uuid4())
        
        try:
            raw_body = await request.body()
            parsed_body = json.loads(raw_body.decode('utf-8'))
            token_request = TokenCountRequest(**parsed_body)
            
            token_count = count_tokens_for_anthropic_request(
                token_request.messages,
                token_request.system,
                token_request.model,
                token_request.tools,
                request_id
            )
            
            return TokenCountResponse(input_tokens=token_count)
            
        except ValidationError as e:
            return await self._log_and_return_error_response(request, e, request_id, 400)
        except json.JSONDecodeError as e:
            return await self._log_and_return_error_response(request, e, request_id, 400)
        except Exception as e:
            return await self._log_and_return_error_response(request, e, request_id)