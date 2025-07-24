"""
Refactored FastAPI application for Claude Code Provider Balancer.
Main application entry point using modular components.
"""

import asyncio
import json
import os
import sys
import threading
import time
import uuid
import yaml
import signal
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from contextlib import asynccontextmanager

import fastapi
import httpx
import openai
import uvicorn
from dotenv import load_dotenv
from fastapi import Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import ValidationError
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text

# Import our modular components
# Add current directory to path for direct execution
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from core.provider_manager import ProviderManager, Provider, ProviderType
from oauth import oauth_manager, init_oauth_manager, start_oauth_auto_refresh
from utils import (
    LogRecord, LogEvent, LogError,
    ColoredConsoleFormatter, JSONFormatter, ConsoleJSONFormatter,
    init_logger, debug, info, warning, error, critical,
    create_debug_request_info
)
from models import (
    MessagesRequest, TokenCountRequest, TokenCountResponse,
    MessagesResponse, AnthropicErrorResponse
)
from caching import (
    generate_request_signature, handle_duplicate_request,
    cleanup_stuck_requests, simulate_testing_delay,
    complete_and_cleanup_request, extract_content_from_sse_chunks
)
from utils.validation import validate_provider_health
from conversion import (
    get_token_encoder, count_tokens_for_anthropic_request,
    convert_anthropic_to_openai_messages, convert_anthropic_tools_to_openai,
    convert_anthropic_tool_choice_to_openai, convert_openai_to_anthropic_response,
    get_anthropic_error_details_from_exc, build_anthropic_error_response
)
from core.streaming import (
    create_broadcaster, 
    register_broadcaster, 
    unregister_broadcaster, 
    handle_duplicate_stream_request,
    has_active_broadcaster
)

load_dotenv()

# Load global configuration
def load_global_config(config_path: str = "config.yaml") -> Dict[str, Any]:
    """Load configuration from config.yaml"""
    if not os.path.isabs(config_path):
        # Look for config in project root (one level up from src)
        current_dir = Path(__file__).parent
        project_root = current_dir.parent
        config_path = project_root / config_path
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"Failed to load config file: {e}")
        return {}

# Global config instance
global_config = load_global_config()

# Initialize rich console
_console = Console()


def _format_duration_for_response(seconds: float) -> str:
    """Format duration in human readable format for API responses"""
    if seconds <= 0:
        return "已过期"
    elif seconds < 60:
        return f"{int(seconds)}秒"
    elif seconds < 3600:
        return f"{int(seconds/60)}分钟"
    elif seconds < 86400:
        hours = int(seconds / 3600)
        minutes = int((seconds % 3600) / 60)
        return f"{hours}小时{minutes}分钟"
    else:
        days = int(seconds / 86400)
        hours = int((seconds % 86400) / 3600)
        return f"{days}天{hours}小时"


def _create_request_summary(raw_body: dict) -> str:
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


def _initialize_oauth_manager(provider_manager_instance: ProviderManager, is_reload: bool = False) -> bool:
    """
    Initialize or re-initialize OAuth manager with provider configuration.
    
    Args:
        provider_manager_instance: The provider manager instance with settings
        is_reload: Whether this is a config reload (affects logging messages)
    
    Returns:
        bool: True if initialization was successful, False otherwise
    """
    try:
        # Check if OAuth manager already exists with tokens before calling init
        from oauth import oauth_manager
        had_existing_tokens = oauth_manager and oauth_manager.token_credentials
        
        result_manager = init_oauth_manager(provider_manager_instance.settings)
        
        # Only log success if we actually did initialization (not skipped due to existing tokens)
        if not had_existing_tokens:
            event_name = "oauth_manager_reinitialized" if is_reload else "oauth_manager_ready"
            message = "OAuth manager re-initialized after config reload" if is_reload else "OAuth manager initialization completed successfully"
            
            info(LogRecord(
                event=event_name,
                message=message
            ))
        
        return True
    except Exception as e:
        event_name = "oauth_manager_reinit_failed" if is_reload else "oauth_manager_init_failed"
        message = f"Failed to re-initialize OAuth manager after config reload: {e}" if is_reload else f"Failed to initialize OAuth manager: {str(e)}"
        
        error(LogRecord(
            event=event_name,
            message=message
        ))
        return False


def _create_body_summary(raw_body: dict) -> dict:
    """Create a detailed summary of the request body for debugging purposes."""
    summary = {}

    # Include basic request info
    if "model" in raw_body:
        summary["model"] = raw_body["model"]

    if "max_tokens" in raw_body:
        summary["max_tokens"] = raw_body["max_tokens"]

    if "stream" in raw_body:
        summary["stream"] = raw_body["stream"]

    # Summarize messages
    if "messages" in raw_body and isinstance(raw_body["messages"], list):
        messages = raw_body["messages"]
        summary["messages_count"] = len(messages)

        # Include role info and content length for each message
        messages_summary = []
        for msg in messages:
            msg_summary = {}
            if "role" in msg:
                msg_summary["role"] = msg["role"]
            if "content" in msg:
                content = msg["content"]
                if isinstance(content, str):
                    msg_summary["content_length"] = len(content)
                    msg_summary["content_preview"] = content[:100] + "..." if len(content) > 100 else content
                elif isinstance(content, list):
                    msg_summary["content_blocks"] = len(content)
                    msg_summary["content_types"] = [block.get("type", "unknown") for block in content if isinstance(block, dict)]
                else:
                    msg_summary["content_type"] = type(content).__name__
            messages_summary.append(msg_summary)

        summary["messages"] = messages_summary

    # Include other important fields
    for key in ["temperature", "top_p", "top_k", "stop_sequences", "tools", "system"]:
        if key in raw_body:
            if key == "tools" and isinstance(raw_body[key], list):
                summary[key + "_count"] = len(raw_body[key])
            elif key == "system" and isinstance(raw_body[key], str):
                system_content = raw_body[key]
                summary[key + "_length"] = len(system_content)
                summary[key + "_preview"] = system_content[:100] + "..." if len(system_content) > 100 else system_content
            else:
                summary[key] = raw_body[key]

    return summary


class Settings:
    """Application settings loaded from provider config only."""

    def __init__(self):
        # Default values
        self.log_level: str = "INFO"
        self.log_file_path: str = ""
        self.log_color: bool = True
        self.providers_config_path: str = "config.yaml"
        self.referrer_url: str = "http://localhost:8082/claude_proxy"
        self.host: str = "127.0.0.1"
        self.port: int = 9090
        self.app_name: str = "Claude Code Provider Balancer"
        self.app_version: str = "0.5.0"
        
        
    def load_from_provider_config(self, config_path: str = "config.yaml"):
        """Load settings from provider configuration file"""
        import yaml
        
        # Determine the absolute path to the config file
        if not os.path.isabs(config_path):
            # If relative path, look for it in project root (one level up from src)
            current_dir = Path(__file__).parent
            project_root = current_dir.parent
            config_path = project_root / config_path
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            # Load settings from the config file
            settings_config = config.get('settings', {})
            
            # Update settings from config
            for key, value in settings_config.items():
                if hasattr(self, key):
                    # Special handling for log file path to resolve relative to project root
                    if key == "log_file_path" and value and not os.path.isabs(value):
                        current_dir = Path(__file__).parent
                        project_root = current_dir.parent
                        value = str(project_root / value)
                    setattr(self, key, value)
                    
        except Exception as e:
            print(f"Warning: Failed to load settings from {config_path}: {e}")
            print("Using default settings.")


# Initialize provider manager and settings
try:
    provider_manager = ProviderManager()
    settings = Settings()
    
    # Load settings from provider config file
    settings.load_from_provider_config()
    
    # Initialize OAuth manager with config settings
    _initialize_oauth_manager(provider_manager, is_reload=False)
    
    # Set provider manager reference for deduplication module
    from caching.deduplication import set_provider_manager
    set_provider_manager(provider_manager)
    
except Exception as e:
    # Fallback to basic settings if provider config fails
    print(f"Warning: Failed to load provider configuration: {e}")
    print("Using basic settings...")
    provider_manager = None
    settings = Settings()
    
    # Still set the provider manager reference (even if None)
    from caching.deduplication import set_provider_manager
    set_provider_manager(provider_manager)


# Initialize logging
init_logger(settings.app_name)

# Setup logging configuration
import logging
from logging.config import dictConfig

log_config = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "colored_console": {
            "()": ColoredConsoleFormatter,
        },
        "json": {
            "()": JSONFormatter,
        },
        "uvicorn_access": {
            "()": "utils.logging.formatters.UvicornAccessFormatter",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "level": settings.log_level,
            "formatter": "colored_console",
            "stream": "ext://sys.stdout",
        },
        "uvicorn_access": {
            "class": "logging.StreamHandler",
            "level": "INFO",
            "formatter": "uvicorn_access",
            "stream": "ext://sys.stdout",
        },
    },
    "loggers": {
        settings.app_name: {
            "level": settings.log_level,
            "handlers": ["console"],
            "propagate": False,
        },
        "uvicorn.access": {
            "level": "INFO",
            "handlers": ["uvicorn_access"],
            "propagate": False,
        },
    },
}

# Add file handler if log_file_path is configured
if settings.log_file_path:
    log_config["handlers"]["file"] = {
        "class": "logging.FileHandler",
        "level": settings.log_level,
        "formatter": "json",
        "filename": settings.log_file_path,
        "mode": "a",
        "encoding": "utf-8",
    }
    log_config["loggers"][settings.app_name]["handlers"].append("file")

dictConfig(log_config)

# Recursion protection for exception handling
_exception_handler_lock = threading.RLock()
_exception_handler_depth = threading.local()

@asynccontextmanager
async def lifespan(app: fastapi.FastAPI):
    """FastAPI lifespan event handler"""
    # Startup
    info(LogRecord(
        event="fastapi_startup_complete",
        message="FastAPI application startup complete"
    ))
    info(LogRecord(
        event="oauth_manager_ready",
        message="OAuth manager ready for Claude Code Official authentication"
    ))
    
    # Start auto-refresh for any loaded OAuth tokens
    try:
        # Get auto-refresh setting from provider manager
        auto_refresh_enabled = provider_manager.oauth_auto_refresh_enabled if provider_manager else True
        await start_oauth_auto_refresh(auto_refresh_enabled)
    except Exception as e:
        warning(LogRecord(
            event="oauth_auto_refresh_start_failed",
            message=f"Failed to start OAuth auto-refresh: {e}"
        ))
    
    yield
    
    # Shutdown
    info(LogRecord(
        event="fastapi_shutdown",
        message="FastAPI application shutting down"
    ))


# FastAPI app
app = fastapi.FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Intelligent load balancer and failover proxy for Claude Code providers",
    lifespan=lifespan,
)


async def make_provider_request(provider: Provider, endpoint: str, data: Dict[str, Any], request_id: str, stream: bool = False, original_headers: Optional[Dict[str, str]] = None) -> Union[httpx.Response, Dict[str, Any]]:
    """Make a request to a specific provider"""
    url = provider_manager.get_request_url(provider, endpoint)
    headers = provider_manager.get_provider_headers(provider, original_headers)
    # 根据请求类型获取相应的超时配置
    http_timeouts = provider_manager.get_timeouts_for_request(stream)
    
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
            event="provider_request",
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
        if stream:
            response = await client.post(url, json=data, headers=headers)
            return response
        else:
            response = await client.post(url, json=data, headers=headers)
            
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
                        event="provider_http_error_details",
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
                http_error = HTTPStatusError(
                    f"HTTP {response.status_code} from provider {provider.name}",
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
                        event="provider_api_error_details",
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


async def make_anthropic_request(provider: Provider, messages_data: Dict[str, Any], request_id: str, stream: bool = False, original_headers: Optional[Dict[str, str]] = None) -> Union[httpx.Response, Dict[str, Any]]:
    """Make a request to an Anthropic-compatible provider"""
    return await make_provider_request(provider, "v1/messages", messages_data, request_id, stream, original_headers)


async def make_openai_request(provider: Provider, openai_params: Dict[str, Any], request_id: str, stream: bool = False, original_headers: Optional[Dict[str, str]] = None) -> Any:
    """Make a request to an OpenAI-compatible provider using openai client"""
    try:
        # Simulate testing delay if configured
        await simulate_testing_delay(openai_params, request_id)
        # Prepare default headers
        default_headers = {
            "HTTP-Referer": settings.referrer_url,
            "X-Title": settings.app_name,
        }

        # 根据请求类型获取相应的超时配置
        openai_timeouts = provider_manager.get_timeouts_for_request(stream)
        
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
        raise e


def select_model_and_provider_options(client_model_name: str, request_id: str, provider_name: Optional[str] = None) -> List[tuple[str, Provider]]:
    """Selects all available model and provider options for failover."""
    if not provider_manager:
        return []
    
    # If provider is specified, return only that provider option
    if provider_name:
        # Find the specified provider
        target_provider = None
        for provider in provider_manager.providers:
            if provider.name == provider_name:
                target_provider = provider
                break
        
        if not target_provider:
            # Provider not found
            return []
            
        # Check if provider is healthy and enabled
        if not target_provider.enabled or not target_provider.is_healthy(provider_manager.get_failure_cooldown()):
            return []
        
        # Find model route for this specific provider
        model_provider_options = provider_manager.select_model_and_provider_options(client_model_name)
        for target_model, candidate_provider in model_provider_options:
            if candidate_provider.name == provider_name:
                return [(target_model, candidate_provider)]
        
        # If no specific model route found, try to use the provider with passthrough
        # Check if provider supports the model or has passthrough capability
        # For now, assume the provider can handle the model as-is (passthrough mode)
        return [(client_model_name, target_provider)]
    
    # Default behavior: return all available options for failover
    return provider_manager.select_model_and_provider_options(client_model_name)


def _create_no_providers_error_message(model: str, provider_name: str = None) -> str:
    """Create a unified error message for when no providers are available."""
    if provider_name:
        return f"Provider '{provider_name}' not found, unhealthy, or not configured for model: {model}"
    else:
        return f"All configured providers for model '{model}' are currently unable to process requests."


async def _log_and_return_error_response(
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
        if settings.log_file_path:
            final_message += f" (详细错误信息请查看日志文件: {settings.log_file_path})"
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


@app.post("/v1/messages", response_model=None, tags=["API"], status_code=200)
async def create_message_proxy(
    request: Request,
) -> JSONResponse:
    """Proxy endpoint for Anthropic Messages API."""
    request_id = str(uuid.uuid4())
    
    try:
        # Get request body for logging and caching
        raw_body = await request.body()
        parsed_body = json.loads(raw_body.decode('utf-8'))
        
        # Extract provider parameter separately before validation
        provider_name = parsed_body.pop("provider", None)
        
        # Generate request signature for deduplication (without provider)
        signature = generate_request_signature(parsed_body)
        
        # Validate the remaining fields with MessagesRequest
        messages_request = MessagesRequest(**parsed_body)
        
        # Add provider back to parsed_body for logging and other uses
        if provider_name:
            parsed_body["provider"] = provider_name
        
        info(
            LogRecord(
                event=LogEvent.REQUEST_RECEIVED.value,
                message=_create_request_summary(parsed_body),
                request_id=request_id,
                data={
                    "model": messages_request.model,
                    "stream": messages_request.stream,
                    "provider": provider_name,
                },
            )
        )
        
        # Create clean request body without balancer-specific fields for provider requests
        clean_request_body = {k: v for k, v in parsed_body.items() if k not in ['provider']}
        
        # For streaming requests, first check if there's an active broadcaster for this signature
        if messages_request.stream and has_active_broadcaster(signature):
            try:
                # Try to connect to existing broadcaster for duplicate stream request
                stream_generator = handle_duplicate_stream_request(signature, request, request_id)
                return StreamingResponse(
                    stream_generator,
                    media_type="text/event-stream",
                    headers={"x-provider-used": "broadcaster-duplicate"}
                )
            except Exception as e:
                # Fallback if broadcaster connection fails
                debug(
                    LogRecord(
                        "broadcaster_connection_failed",
                        f"Failed to connect to active broadcaster: {str(e)}",
                        request_id,
                        {
                            "signature": signature[:16] + "...",
                            "error": str(e)
                        }
                    )
                )
        
        # Check for cached duplicate requests
        duplicate_result = await handle_duplicate_request(
            signature, request_id, messages_request.stream or False, clean_request_body
        )
        if duplicate_result is not None:
            return duplicate_result
        
        # Select all available provider options for failover
        provider_options = select_model_and_provider_options(
            messages_request.model, request_id, provider_name
        )
        if not provider_options:
            error_msg = _create_no_providers_error_message(messages_request.model, provider_name)
            return await _log_and_return_error_response(
                request, Exception(error_msg), request_id, 404, signature
            )
        
        # Log available options
        info(
            LogRecord(
                event=LogEvent.REQUEST_START.value,
                message=f"Processing request with {len(provider_options)} provider option(s)",
                request_id=request_id,
                data={
                    "client_model": messages_request.model,
                    "available_options": len(provider_options),
                    "primary_provider": provider_options[0][1].name,
                    "stream": messages_request.stream,
                },
            )
        )
        
        # Try providers in order until one succeeds
        max_attempts = len(provider_options)
        last_exception = None
        
        for attempt in range(max_attempts):
            target_model, current_provider = provider_options[attempt]
            
            try:
                # Make actual request to current provider
                original_headers = dict(request.headers)
                if current_provider.type == ProviderType.ANTHROPIC:
                    response = await make_anthropic_request(
                        current_provider, clean_request_body, request_id, 
                        messages_request.stream or False, original_headers
                    )
                elif current_provider.type == ProviderType.OPENAI:
                    # Convert to OpenAI format first
                    openai_messages = convert_anthropic_to_openai_messages(
                        messages_request.messages, messages_request.system, request_id
                    )
                    openai_tools = convert_anthropic_tools_to_openai(messages_request.tools)
                    openai_tool_choice = convert_anthropic_tool_choice_to_openai(
                        messages_request.tool_choice, request_id
                    )
                    
                    openai_params = {
                        "model": target_model,
                        "messages": openai_messages,
                        "max_tokens": messages_request.max_tokens,
                        "stream": messages_request.stream or False,
                    }
                    
                    if messages_request.temperature is not None:
                        openai_params["temperature"] = messages_request.temperature
                    if messages_request.top_p is not None:
                        openai_params["top_p"] = messages_request.top_p
                    if messages_request.stop_sequences:
                        openai_params["stop"] = messages_request.stop_sequences
                    if openai_tools:
                        openai_params["tools"] = openai_tools
                    if openai_tool_choice:
                        openai_params["tool_choice"] = openai_tool_choice
                    
                    response = await make_openai_request(
                        current_provider, openai_params, request_id,
                        messages_request.stream or False, original_headers
                    )
                else:
                    raise ValueError(f"Unsupported provider type: {current_provider.type}")
                
                # Handle streaming response
                if messages_request.stream:
                    # Add provider information to headers for streaming responses
                    stream_headers = {"x-provider-used": current_provider.name}
                    
                    if current_provider.type == ProviderType.ANTHROPIC:
                        # For Anthropic providers, response is an httpx.Response object
                        if hasattr(response, 'aiter_text'):
                            # Check for HTTP error status codes before starting stream
                            if response.status_code >= 400:
                                # Create HTTP error with status code for failover handling
                                from httpx import HTTPStatusError
                                provider_url = provider_manager.get_request_url(current_provider, "v1/messages")
                                request_obj = httpx.Request("POST", provider_url)
                                http_error = HTTPStatusError(
                                    f"HTTP {response.status_code} from provider {current_provider.name}",
                                    request=request_obj,
                                    response=response
                                )
                                http_error.status_code = response.status_code
                                raise http_error
                            # Collect chunks for caching while streaming
                            collected_chunks = []
                            
                            async def stream_anthropic_response():
                                """Simplified Anthropic streaming using parallel broadcaster"""
                                broadcaster = None
                                try:
                                    # Create parallel broadcaster for handling multiple clients
                                    broadcaster = create_broadcaster(request, request_id, current_provider.name)
                                    
                                    # Register broadcaster for duplicate request handling
                                    register_broadcaster(signature, broadcaster)
                                    
                                    # Create provider stream from response
                                    async def provider_stream():
                                        try:
                                            async for chunk in response.aiter_text():
                                                collected_chunks.append(chunk)
                                                yield chunk
                                        except Exception as e:
                                            error(
                                                LogRecord(
                                                    "provider_stream_error",
                                                    f"Error in provider stream: {type(e).__name__}: {e}",
                                                    request_id,
                                                    {
                                                        "provider": current_provider.name,
                                                        "error": str(e)
                                                    }
                                                )
                                            )
                                            raise
                                    
                                    # Use broadcaster to handle parallel streaming with disconnect detection
                                    async for chunk in broadcaster.stream_from_provider(provider_stream()):
                                        yield chunk
                                        
                                except Exception as e:
                                    error(
                                        LogRecord(
                                            "stream_anthropic_error",
                                            f"Error in Anthropic streaming: {type(e).__name__}: {e}",
                                            request_id,
                                            {
                                                "provider": current_provider.name,
                                                "error": str(e)
                                            }
                                        )
                                    )
                                    raise
                                finally:
                                    # Unregister broadcaster when streaming completes
                                    if broadcaster:
                                        unregister_broadcaster(signature)
                                    
                                    # Check provider health based on collected chunks
                                    failover_config = {}
                                    if provider_manager:
                                        failover_config = {
                                            'failover_error_types': provider_manager.settings.get('failover_error_types', []),
                                            'failover_http_codes': provider_manager.settings.get('failover_http_codes', [])
                                        }
                                    
                                    is_unhealthy, error_type = validate_provider_health(
                                        collected_chunks, 
                                        current_provider.name, 
                                        request_id,
                                        None,  # No HTTP status for successful stream
                                        failover_config.get('failover_error_types', []),
                                        failover_config.get('failover_http_codes', [])
                                    )
                                    
                                    if is_unhealthy:
                                        # Provider is unhealthy, mark as failed but cannot failover for stream
                                        current_provider.mark_failure()
                                        
                                        warning(
                                            LogRecord(
                                                "provider_unhealthy_stream_anthropic",
                                                f"Anthropic provider {current_provider.name} marked unhealthy due to stream content, cannot failover",
                                                request_id,
                                                {
                                                    "provider": current_provider.name,
                                                    "error_type": error_type,
                                                    "can_failover": False,
                                                    "action": "marked_unhealthy_only"
                                                }
                                            )
                                        )
                                        
                                        # Cannot failover for streaming, but still complete the request
                                        health_validation_error = Exception(f"Anthropic stream provider health validation failed: {error_type}")
                                        complete_and_cleanup_request(signature, health_validation_error, None, True, current_provider.name)
                                    else:
                                        # Provider is healthy, complete the request with collected chunks
                                        complete_and_cleanup_request(signature, collected_chunks, collected_chunks, True, current_provider.name)
                                        
                                        # Log request completion for consistency with non-streaming requests
                                        info(
                                            LogRecord(
                                                event=LogEvent.REQUEST_COMPLETED.value,
                                                message=f"Anthropic streaming request completed: {current_provider.name}",
                                                request_id=request_id,
                                                data={
                                                    "provider": current_provider.name,
                                                    "model": target_model,
                                                    "stream": True,
                                                    "provider_type": "anthropic",
                                                    "chunks_count": len(collected_chunks),
                                                    "attempt": attempt + 1,
                                                }
                                            )
                                        )
                            
                            return StreamingResponse(
                                stream_anthropic_response(),
                                media_type="text/event-stream",
                                headers=stream_headers
                            )
                        else:
                            # If it's already JSON, convert to streaming format
                            response_data = response.json() if hasattr(response, 'json') else response
                            collected_chunks = [f"data: {json.dumps(response_data)}\n\n"]
                            
                            async def convert_to_stream():
                                yield f"data: {json.dumps(response_data)}\n\n"
                            
                            # For non-streaming responses converted to stream, use the response_data directly
                            complete_and_cleanup_request(signature, response_data, collected_chunks, True, current_provider.name)
                            
                            # Log request completion
                            info(
                                LogRecord(
                                    event=LogEvent.REQUEST_COMPLETED.value,
                                    message=f"Non-streaming response converted to stream completed: {current_provider.name}",
                                    request_id=request_id,
                                    data={
                                        "provider": current_provider.name,
                                        "model": target_model,
                                        "stream": True,
                                        "converted_from_non_stream": True,
                                        "attempt": attempt + 1,
                                    }
                                )
                            )
                            return StreamingResponse(
                                convert_to_stream(),
                                media_type="text/event-stream",
                                headers=stream_headers
                            )
                    else:
                        # For OpenAI providers, response is from openai client
                        # Collect chunks for caching while streaming
                        collected_chunks = []
                        
                        async def stream_openai_response():
                            """OpenAI streaming using parallel broadcaster"""
                            broadcaster = None
                            try:
                                # Create parallel broadcaster for handling multiple clients
                                broadcaster = create_broadcaster(request, request_id, current_provider.name)
                                
                                # Register broadcaster for duplicate request handling
                                register_broadcaster(signature, broadcaster)
                                
                                # Create provider stream from OpenAI response
                                async def provider_stream():
                                    message_id = str(uuid.uuid4())
                                    first_chunk = True
                                    
                                    try:
                                            async for chunk in response:
                                                chunk_data = chunk.model_dump() if hasattr(chunk, 'model_dump') else chunk
                                                
                                                # Convert OpenAI streaming format to Anthropic format
                                                if chunk_data.get("choices") and len(chunk_data["choices"]) > 0:
                                                    choice = chunk_data["choices"][0]
                                                    delta = choice.get("delta", {})
                                                    
                                                    if first_chunk and delta.get("role") == "assistant":
                                                        # Send message_start event
                                                        message_start = {
                                                            "type": "message_start",
                                                            "message": {
                                                                "id": message_id,
                                                                "type": "message",
                                                                "role": "assistant",
                                                                "content": [],
                                                                "model": chunk_data.get("model", target_model),
                                                                "stop_reason": None,
                                                                "stop_sequence": None,
                                                                "usage": {"input_tokens": 0, "output_tokens": 0}
                                                            }
                                                        }
                                                        formatted_chunk = f"event: message_start\ndata: {json.dumps(message_start)}\n\n"
                                                        collected_chunks.append(formatted_chunk)
                                                        yield formatted_chunk
                                                        
                                                        # Send content_block_start event
                                                        content_block_start = {
                                                            "type": "content_block_start",
                                                            "index": 0,
                                                            "content_block": {"type": "text", "text": ""}
                                                        }
                                                        formatted_chunk = f"event: content_block_start\ndata: {json.dumps(content_block_start)}\n\n"
                                                        collected_chunks.append(formatted_chunk)
                                                        yield formatted_chunk
                                                        first_chunk = False
                                                    
                                                    # Handle content deltas
                                                    if "content" in delta and delta["content"]:
                                                        content_delta = {
                                                            "type": "content_block_delta",
                                                            "index": 0,
                                                            "delta": {
                                                                "type": "text_delta",
                                                                "text": delta["content"]
                                                            }
                                                        }
                                                        formatted_chunk = f"event: content_block_delta\ndata: {json.dumps(content_delta)}\n\n"
                                                        collected_chunks.append(formatted_chunk)
                                                        yield formatted_chunk
                                                    
                                                    # Handle finish_reason
                                                    if choice.get("finish_reason"):
                                                        # Send content_block_stop event
                                                        content_block_stop = {
                                                            "type": "content_block_stop",
                                                            "index": 0
                                                        }
                                                        formatted_chunk = f"event: content_block_stop\ndata: {json.dumps(content_block_stop)}\n\n"
                                                        collected_chunks.append(formatted_chunk)
                                                        yield formatted_chunk
                                                        
                                                        # Send message_delta with stop_reason
                                                        message_delta = {
                                                            "type": "message_delta",
                                                            "delta": {
                                                                "stop_reason": choice["finish_reason"],
                                                                "stop_sequence": None
                                                            }
                                                        }
                                                        
                                                        # Add usage info if available
                                                        if chunk_data.get("usage"):
                                                            message_delta["usage"] = chunk_data["usage"]
                                                        
                                                        formatted_chunk = f"event: message_delta\ndata: {json.dumps(message_delta)}\n\n"
                                                        collected_chunks.append(formatted_chunk)
                                                        yield formatted_chunk
                                                        
                                                        # Send message_stop event
                                                        message_stop = {"type": "message_stop"}
                                                        formatted_chunk = f"event: message_stop\ndata: {json.dumps(message_stop)}\n\n"
                                                        collected_chunks.append(formatted_chunk)
                                                        yield formatted_chunk
                                                        
                                                        break
                                    except Exception as e:
                                        error(
                                            LogRecord(
                                                "provider_stream_error",
                                                f"Error in OpenAI provider stream: {type(e).__name__}: {e}",
                                                request_id,
                                                {
                                                    "provider": current_provider.name,
                                                    "error": str(e),
                                                    "chunks_processed": len(collected_chunks)
                                                }
                                            )
                                        )
                                        raise
                                
                                # Use broadcaster to handle parallel streaming with disconnect detection
                                async for chunk in broadcaster.stream_from_provider(provider_stream()):
                                    yield chunk
                                
                            except Exception as e:
                                error(
                                    LogRecord(
                                        "stream_openai_error",
                                        f"Error in OpenAI streaming: {type(e).__name__}: {e}",
                                        request_id,
                                        {
                                            "provider": current_provider.name,
                                            "error": str(e)
                                        }
                                    )
                                )
                                raise
                            finally:
                                # Unregister broadcaster when streaming completes
                                if broadcaster:
                                    unregister_broadcaster(signature)
                                
                                # Check provider health based on collected chunks
                                failover_config = {}
                                if provider_manager:
                                    failover_config = {
                                        'failover_error_types': provider_manager.settings.get('failover_error_types', []),
                                        'failover_http_codes': provider_manager.settings.get('failover_http_codes', [])
                                    }
                                
                                is_unhealthy, error_type = validate_provider_health(
                                    collected_chunks, 
                                    current_provider.name, 
                                    request_id,
                                    None,  # No HTTP status for successful stream
                                    failover_config.get('failover_error_types', []),
                                    failover_config.get('failover_http_codes', [])
                                )
                                
                                if is_unhealthy:
                                    # Provider is unhealthy, mark as failed but cannot failover for stream
                                    current_provider.mark_failure()
                                    
                                    warning(
                                        LogRecord(
                                            "provider_unhealthy_stream_openai",
                                            f"OpenAI provider {current_provider.name} marked unhealthy due to stream content, cannot failover",
                                            request_id,
                                            {
                                                "provider": current_provider.name,
                                                "error_type": error_type,
                                                "can_failover": False,
                                                "action": "marked_unhealthy_only"
                                            }
                                        )
                                    )
                                    
                                    # Cannot failover for streaming, but still complete the request
                                    health_validation_error = Exception(f"OpenAI stream provider health validation failed: {error_type}")
                                    complete_and_cleanup_request(signature, health_validation_error, None, True, current_provider.name)
                                else:
                                    # Provider is healthy, cache the response
                                    try:
                                        response_content = extract_content_from_sse_chunks(collected_chunks)
                                        complete_and_cleanup_request(signature, response_content, collected_chunks, True, current_provider.name)
                                        
                                        # Log request completion
                                        info(
                                            LogRecord(
                                                event=LogEvent.REQUEST_COMPLETED.value,
                                                message=f"OpenAI streaming request completed: {current_provider.name}",
                                                request_id=request_id,
                                                data={
                                                    "provider": current_provider.name,
                                                    "model": target_model,
                                                    "stream": True,
                                                    "provider_type": "openai",
                                                    "chunks_count": len(collected_chunks),
                                                    "attempt": attempt + 1,
                                                }
                                            )
                                        )
                                    except Exception as e:
                                        extraction_error = Exception(f"Response content extraction failed: {str(e)}")
                                        complete_and_cleanup_request(signature, extraction_error, None, True, current_provider.name)
                        
                        # Return immediately without waiting for stream completion
                        # The caching will happen asynchronously in the stream generator
                        return StreamingResponse(
                            stream_openai_response(),
                            media_type="text/event-stream",
                            headers=stream_headers
                        )
                
                # Handle non-streaming response
                if current_provider.type == ProviderType.OPENAI:
                    # Convert OpenAI response back to Anthropic format
                    anthropic_response = convert_openai_to_anthropic_response(response, request_id)
                    # Convert Pydantic model to dict for JSON serialization
                    response_content = anthropic_response.model_dump()
                else:
                    # For Anthropic providers, handle httpx.Response objects
                    if hasattr(response, 'json'):
                        response_content = response.json()
                    elif isinstance(response, dict):
                        response_content = response
                    else:
                        # Convert non-serializable response objects to dict
                        response_content = {"error": {"type": "serialization_error", "message": "Unable to serialize response"}}
                
                # Check provider health based on response content
                if provider_manager:
                    failover_config = {
                        'failover_error_types': provider_manager.settings.get('failover_error_types', []),
                        'failover_http_codes': provider_manager.settings.get('failover_http_codes', [])
                    }
                    
                    # Get HTTP status code from response
                    response_status_code = None
                    if hasattr(response, 'status_code'):
                        response_status_code = response.status_code
                    
                    is_unhealthy, error_type = validate_provider_health(
                        response_content, 
                        current_provider.name, 
                        request_id,
                        response_status_code,
                        failover_config['failover_error_types'],
                        failover_config['failover_http_codes']
                    )
                    
                    if is_unhealthy:
                        # Provider is unhealthy, mark as failed and attempt failover
                        current_provider.mark_failure()
                        
                        warning(
                            LogRecord(
                                "provider_unhealthy_non_stream",
                                f"Provider {current_provider.name} marked unhealthy due to response content, attempting failover",
                                request_id,
                                {
                                    "provider": current_provider.name,
                                    "error_type": error_type,
                                    "attempt": attempt + 1,
                                    "remaining_attempts": max_attempts - attempt - 1,
                                    "can_failover": True
                                }
                            )
                        )
                        
                        # Create a health validation exception to trigger failover
                        health_validation_error = Exception(f"Provider health validation failed: {error_type}")
                        
                        # If we have more providers to try, continue to next iteration
                        if attempt < max_attempts - 1:
                            last_exception = health_validation_error
                            continue
                        else:
                            # This was the last provider, return the health validation error
                            # complete_and_cleanup_request(signature, health_validation_error, None, False, current_provider.name)  # 由_log_and_return_error_response统一处理
                            return await _log_and_return_error_response(request, health_validation_error, request_id, 500, signature)
                
                # Provider is healthy, complete the request and cleanup
                # For non-streaming responses, cache the actual content dict instead of JSON string array
                complete_and_cleanup_request(signature, response_content, response_content, False, current_provider.name)
                
                info(
                    LogRecord(
                        event=LogEvent.REQUEST_COMPLETED.value,
                        message=f"Request completed: {current_provider.name}",
                        request_id=request_id,
                        data={
                            "provider": current_provider.name,
                            "model": target_model,
                            "tokens": response_content.get("usage", {}),
                            "attempt": attempt + 1,
                        },
                    )
                )
                
                # Create response with provider information in headers  
                response_headers = {"x-provider-used": current_provider.name}
                return JSONResponse(content=response_content, headers=response_headers)
                
            except Exception as e:
                last_exception = e
                
                # Get HTTP status code if available
                http_status_code = getattr(e, 'status_code', None) or (
                    getattr(e, 'response', None) and getattr(e.response, 'status_code', None)
                )
                
                # Special handling for 401 Unauthorized and 403 Forbidden with Claude Code Official
                if http_status_code in [401, 403] and current_provider.name == "Claude Code Official":
                    # Handle OAuth authorization required
                    if provider_manager:
                        login_url = provider_manager.handle_oauth_authorization_required(current_provider, http_status_code)
                        if login_url:
                            # For OAuth authorization flow, don't failover and return the auth error directly
                            # The user needs to complete the OAuth flow
                            # complete_and_cleanup_request(signature, e, None, False, current_provider.name)  # 由_log_and_return_error_response统一处理
                            return await _log_and_return_error_response(request, e, request_id, http_status_code, signature)
                
                # Use provider_manager to determine if we should failover
                if provider_manager:
                    error_type, should_failover = provider_manager.get_error_classification(e, http_status_code)
                else:
                    # Default failover behavior if provider_manager is not available
                    should_failover = True
                    error_type = "unknown_error"
                
                # Create debug info for request details (will be masked for security)
                debug_info = None
                try:
                    url = provider_manager.get_request_url(current_provider, "v1/messages")
                    headers = provider_manager.get_provider_headers(current_provider, original_headers)
                    request_data = clean_request_body if current_provider.type == ProviderType.ANTHROPIC else openai_params
                    debug_info = create_debug_request_info(url, headers, request_data)
                except Exception as debug_error:
                    debug(LogRecord(
                        event="debug_info_creation_failed",
                        message=f"Failed to create debug info: {debug_error}"
                    ))

                # Extract HTTP response details for comprehensive error logging
                response_details = None
                if hasattr(e, 'response') and e.response is not None:
                    try:
                        # Get full response body for file logging
                        full_response_body = e.response.text if hasattr(e.response, 'text') else None
                        # Try to parse as JSON for better formatting
                        try:
                            if full_response_body:
                                full_response_body = json.loads(full_response_body)
                        except:
                            pass  # Keep as text if not valid JSON
                        
                        response_details = {
                            "response_headers": dict(e.response.headers),
                            "response_body": full_response_body
                        }
                    except Exception:
                        # Ignore errors when extracting response details
                        pass
                
                # Log detailed error information to file only (not console)
                from utils.logging.handlers import error_file_only
                error_file_only(
                    LogRecord(
                        event="provider_request_failed_details",
                        message=f"Detailed error info for provider {current_provider.name} (attempt {attempt + 1}/{max_attempts})",
                        request_id=request_id,
                        data={
                            "provider": current_provider.name,
                            "target_model": target_model,
                            "attempt": attempt + 1,
                            "remaining_attempts": max_attempts - attempt - 1,
                            "error_type": error_type,
                            "should_failover": should_failover,
                            "http_status_code": http_status_code,
                            "request_details": debug_info,
                            "response_details": response_details,
                            "full_error": str(e)
                        }
                    ),
                    exc=e
                )
                
                # Log brief summary to console for user visibility
                error_summary = f"HTTP {http_status_code}" if http_status_code else "Connection error"
                if hasattr(e, 'response') and e.response and response_details and response_details.get('response_body'):
                    try:
                        response_body = response_details['response_body']
                        if isinstance(response_body, dict) and 'error' in response_body:
                            error_msg = response_body['error'].get('message', '')[:100]
                            if error_msg:
                                error_summary = f"{error_summary}: {error_msg}"
                    except:
                        pass
                
                # Add hint about detailed logs in file
                console_message = f"Request failed for provider {current_provider.name} (attempt {attempt + 1}/{max_attempts}): {error_summary}"
                if settings.log_file_path:
                    console_message += f" (详细错误信息请查看日志文件: {settings.log_file_path})"
                else:
                    console_message += " (详细错误信息请查看日志文件: logs/logs.jsonl)"
                
                warning(
                    LogRecord(
                        event="provider_request_failed",
                        message=console_message,
                        request_id=request_id,
                        data={
                            "provider": current_provider.name,
                            "target_model": target_model,
                            "attempt": attempt + 1,
                            "remaining_attempts": max_attempts - attempt - 1,
                            "error_type": error_type,
                            "should_failover": should_failover,
                            "http_status_code": http_status_code
                        }
                    )
                )
                
                # If we shouldn't failover, return the error immediately
                if not should_failover:
                    # Mark provider as used for sticky logic
                    if provider_manager:
                        provider_manager.mark_provider_used(current_provider.name)
                    
                    info(
                        LogRecord(
                            event="error_not_retryable",
                            message=f"Error type '{error_type}' not configured for failover, returning to client",
                            request_id=request_id,
                            data={
                                "provider": current_provider.name,
                                "error_type": error_type,
                                "http_status_code": http_status_code
                            }
                        )
                    )
                    # complete_and_cleanup_request(signature, e, None, False, current_provider.name)  # 由_log_and_return_error_response统一处理
                    return await _log_and_return_error_response(request, e, request_id, 500, signature)
                
                # Mark current provider as failed since we are failing over
                current_provider.mark_failure()
                
                # If we have more providers to try, continue to next iteration
                if attempt < max_attempts - 1:
                    next_target_model, next_provider = provider_options[attempt + 1]
                    info(
                        LogRecord(
                            event="provider_fallback",
                            message=f"Falling back to provider: {next_provider.name} with model: {next_target_model}",
                            request_id=request_id,
                            data={
                                "failed_provider": current_provider.name,
                                "failed_model": target_model,
                                "fallback_provider": next_provider.name,
                                "fallback_model": next_target_model,
                                "attempt": attempt + 2,
                                "total_attempts": max_attempts
                            }
                        )
                    )
                # If this is the last attempt, the loop will end and we'll return the error
        
        # All providers failed, return the last exception
        error(
            LogRecord(
                event="all_providers_failed",
                message=f"All {max_attempts} provider(s) failed for model: {messages_request.model}",
                request_id=request_id,
                data={
                    "model": messages_request.model,
                    "total_attempts": max_attempts,
                    "providers_tried": [opt[1].name for opt in provider_options]
                }
            ),
            exc=last_exception
        )
        
        # Create a generic error message for the client that doesn't expose provider details
        client_error_message = _create_no_providers_error_message(messages_request.model)
        client_error = Exception(client_error_message)
        
        # complete_and_cleanup_request(signature, client_error, None, False, "unknown")  # 由_log_and_return_error_response统一处理
        return await _log_and_return_error_response(request, client_error, request_id, 500, signature)
            
    except ValidationError as e:
        # ValidationError发生在生成signature之前，无需cleanup
        return await _log_and_return_error_response(request, e, request_id, 400)
    except json.JSONDecodeError as e:
        # JSONDecodeError发生在生成signature之前，无需cleanup
        return await _log_and_return_error_response(request, e, request_id, 400)
    except Exception as e:
        # 通用异常可能在任何阶段发生，尝试cleanup（如果signature不存在会被安全忽略）
        return await _log_and_return_error_response(request, e, request_id, 500, locals().get('signature'))


@app.post("/v1/messages/count_tokens", response_model=TokenCountResponse, tags=["API"])
async def count_tokens_endpoint(request: Request) -> TokenCountResponse:
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
        return await _log_and_return_error_response(request, e, request_id, 400)
    except json.JSONDecodeError as e:
        return await _log_and_return_error_response(request, e, request_id, 400)
    except Exception as e:
        return await _log_and_return_error_response(request, e, request_id)


@app.get("/", include_in_schema=False, tags=["Health"])
async def root_health_check() -> JSONResponse:
    """Basic health check and information endpoint."""
    return JSONResponse(
        content={
            "service": settings.app_name,
            "version": settings.app_version,
            "status": "healthy",
            "providers_available": len(provider_manager.get_healthy_providers()) if provider_manager else 0,
        }
    )


@app.get("/providers", tags=["Health"])
async def get_providers_status() -> JSONResponse:
    """Get status of all configured providers."""
    if not provider_manager:
        return JSONResponse(content={"error": "Provider manager not initialized"})
    
    # Get comprehensive status from provider manager
    status_data = provider_manager.get_status()
    
    # Enhance provider status with model information
    for provider_status in status_data["providers"]:
        provider_name = provider_status["name"]
        
        # Get models for this provider from model_routes
        provider_models = []
        for model_pattern, routes in provider_manager.model_routes.items():
            for route in routes:
                if route.provider == provider_name and route.enabled:
                    provider_models.append({
                        "pattern": model_pattern,
                        "model": route.model,
                        "priority": route.priority
                    })
        
        provider_status["models"] = provider_models
        
        # Add human-readable status field
        if provider_status["enabled"] and provider_status["healthy"]:
            provider_status["status"] = "healthy"
        elif provider_status["enabled"] and not provider_status["healthy"]:
            provider_status["status"] = "unhealthy"
        else:
            provider_status["status"] = "disabled"
    
    return JSONResponse(content=status_data)


@app.post("/cleanup", tags=["Management"])
async def cleanup_requests(force: bool = False):
    """Manually cleanup stuck requests."""
    cleanup_stuck_requests(force)
    return JSONResponse(content={"status": "cleanup completed"})


@app.get("/oauth/generate-url", tags=["OAuth"])
async def generate_oauth_url():
    """
    Generate OAuth authorization URL for manual account setup.
    
    This endpoint allows users to manually initiate OAuth authorization
    without waiting for a 401 error. Useful for proactive account setup.
    """
    try:
        if not oauth_manager:
            return JSONResponse(
                status_code=500,
                content={
                    "error": "OAuth manager not initialized"
                }
            )
        
        # Generate OAuth login URL
        if not oauth_manager:
            return JSONResponse(
                status_code=500,
                content={
                    "error": "OAuth manager not initialized. Please check server logs."
                }
            )
        
        login_url = oauth_manager.generate_login_url()
        
        if not login_url:
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Failed to generate OAuth URL"
                }
            )
        
        # Return the URL with instructions
        return JSONResponse(content={
            "status": "success",
            "login_url": login_url,
            "instructions": {
                "step_1": "Open the login_url in your browser",
                "step_2": "Complete OAuth authorization in browser",
                "step_3": "Copy the authorization code from callback URL",
                "step_4": "Use POST /oauth/exchange-code with the authorization code and required account_email"
            },
            "callback_format": "https://console.anthropic.com/oauth/code/callback?code=YOUR_CODE&state=STATE",
            "exchange_example": "curl -X POST /oauth/exchange-code -d '{\"code\": \"YOUR_CODE\", \"account_email\": \"user@example.com\"}'",
            "expires_in_minutes": 10
        })
        
    except Exception as e:
        error(LogRecord(
            event="oauth_url_generation_error",
            message=f"Error generating OAuth URL: {str(e)}"
        ))
        return JSONResponse(
            status_code=500,
            content={
                "error": f"Internal server error: {str(e)}"
            }
        )


@app.post("/oauth/exchange-code", tags=["OAuth"])
async def exchange_oauth_code(request: Request) -> JSONResponse:
    """Exchange OAuth authorization code for access tokens"""
    try:
        body = await request.json()
        authorization_code = body.get("code")
        account_email = body.get("account_email")  # Required email parameter
        
        if not authorization_code:
            return JSONResponse(
                status_code=400,
                content={"error": "Missing authorization code"}
            )
        
        if not account_email:
            return JSONResponse(
                status_code=400,
                content={"error": "Missing account_email parameter. Please provide your email address for account identification."}
            )
        
        # Exchange code for tokens (with required account email)
        if not oauth_manager:
            return JSONResponse(
                status_code=500,
                content={"error": "OAuth manager not initialized. Please check server logs."}
            )
        
        credentials = await oauth_manager.exchange_code(authorization_code, account_email)
        
        if credentials:
            # Start auto-refresh for the new token (if enabled)
            if provider_manager and provider_manager.oauth_auto_refresh_enabled:
                await oauth_manager.start_auto_refresh()
            else:
                info(LogRecord(
                    event="oauth_auto_refresh_disabled",
                    message="Auto-refresh disabled - new token will not be auto-refreshed"
                ))
            
            # Build response with account information
            response_data = {
                "status": "success",
                "message": "Authorization successful", 
                "account_email": credentials.account_email,  # Use email as primary identifier
                "expires_at": credentials.expires_at,
                "scopes": credentials.scopes
            }
            
            # Add account name if available
            if credentials.account_name:
                response_data["account_name"] = credentials.account_name
            
            return JSONResponse(content=response_data)
        else:
            return JSONResponse(
                status_code=400,
                content={"error": "Failed to exchange authorization code"}
            )
    
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"OAuth exchange failed: {str(e)}"}
        )


@app.get("/oauth/status", tags=["OAuth"])
async def get_oauth_status() -> JSONResponse:
    """Get comprehensive status of stored OAuth tokens and system state"""
    try:
        if not oauth_manager:
            return JSONResponse(
                status_code=500,
                content={"error": "OAuth manager not initialized. Please check server logs."}
            )
        
        tokens_status = oauth_manager.get_tokens_status()
        
        # Calculate summary statistics
        total_tokens = len(tokens_status)
        healthy_tokens = sum(1 for token in tokens_status if token.get("is_healthy", False))
        expired_tokens = sum(1 for token in tokens_status if token.get("is_expired", False))
        expiring_soon = sum(1 for token in tokens_status if token.get("will_expire_soon", False))
        
        # Get current time for reference
        current_time = int(time.time())
        
        # Find currently active token
        active_token = next((token for token in tokens_status if token.get("is_current", False)), None)
        
        # System info
        system_info = {
            "oauth_manager_status": "active",
            "current_time": current_time,
            "current_time_iso": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(current_time)),
            "timezone": "Local",
        }
        
        # Summary
        summary = {
            "total_tokens": total_tokens,
            "healthy_tokens": healthy_tokens,
            "expired_tokens": expired_tokens,
            "expiring_soon": expiring_soon,
            "current_token_index": oauth_manager.current_token_index if (oauth_manager and total_tokens > 0) else None,
            "rotation_enabled": total_tokens > 1,
        }
        
        # Active token info (safe)
        active_info = None
        if active_token:
            active_info = {
                "account_email": active_token["account_email"],
                "expires_in_human": active_token["expires_in_human"],
                "is_healthy": active_token["is_healthy"],
                "scopes": active_token["scopes"]
            }
        
        return JSONResponse(content={
            "system": system_info,
            "summary": summary,
            "active_token": active_info,
            "tokens": tokens_status
        })
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to get OAuth status: {str(e)}"}
        )


@app.delete("/oauth/tokens/{account_email}", tags=["OAuth"])
async def remove_oauth_token(account_email: str) -> JSONResponse:
    """Remove a specific OAuth token"""
    try:
        if not oauth_manager:
            return JSONResponse(
                status_code=500,
                content={"error": "OAuth manager not initialized. Please check server logs."}
            )
        
        success = oauth_manager.remove_token(account_email)
        if success:
            return JSONResponse(content={
                "status": "success",
                "message": f"Token for {account_email} removed"
            })
        else:
            return JSONResponse(
                status_code=404,
                content={"error": f"Token for {account_email} not found"}
            )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to remove token: {str(e)}"}
        )


@app.post("/oauth/refresh/{account_email}", tags=["OAuth"])
async def refresh_oauth_token(account_email: str) -> JSONResponse:
    """Manually refresh OAuth token for a specific account"""
    try:
        if not oauth_manager:
            return JSONResponse(
                status_code=500,
                content={"error": "OAuth manager not initialized. Please check server logs."}
            )
        
        # Refresh the token for the specified account
        refreshed_credentials, error_details = await oauth_manager.refresh_token_by_email(account_email)
        
        if not refreshed_credentials:
            return JSONResponse(
                status_code=404,
                content={
                    "error": f"Token not found or refresh failed for account: {account_email}",
                    "details": error_details or "Account may not exist, or refresh token may be invalid/expired"
                }
            )
        
        # Calculate token expiry information
        current_time = time.time()
        expires_in_seconds = max(0, refreshed_credentials.expires_at - current_time)
        expires_in_minutes = round(expires_in_seconds / 60, 1)
        
        return JSONResponse(content={
            "status": "success",
            "message": f"Token refreshed successfully for account: {account_email}",
            "account_email": refreshed_credentials.account_email,
            "account_id": refreshed_credentials.account_id,
            "expires_at": refreshed_credentials.expires_at,
            "expires_in_seconds": int(expires_in_seconds),
            "expires_in_minutes": expires_in_minutes,
            "expires_in_human": _format_duration_for_response(expires_in_seconds),
            "access_token_preview": f"{refreshed_credentials.access_token[:8]}...{refreshed_credentials.access_token[-4:]}" if refreshed_credentials.access_token else None,
            "scopes": refreshed_credentials.scopes,
            "refreshed_at": int(time.time())
        })
        
    except Exception as e:
        error(LogRecord(
            event="oauth_manual_refresh_error",
            message=f"Error during manual token refresh for {account_email}: {str(e)}"
        ))
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to refresh token: {str(e)}"}
        )


@app.delete("/oauth/tokens", tags=["OAuth"])
async def clear_all_oauth_tokens() -> JSONResponse:
    """Clear all stored OAuth tokens"""
    try:
        if not oauth_manager:
            return JSONResponse(
                status_code=500,
                content={"error": "OAuth manager not initialized. Please check server logs."}
            )
        
        oauth_manager.clear_all_tokens()
        return JSONResponse(content={
            "status": "success",
            "message": "All tokens cleared"
        })
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to clear tokens: {str(e)}"}
        )







# Exception handlers
@app.exception_handler(ValidationError)
async def pydantic_validation_error_handler(request: Request, exc: ValidationError):
    """Handle Pydantic validation errors."""
    request_id = str(uuid.uuid4())
    return await _log_and_return_error_response(request, exc, request_id, 400)


@app.exception_handler(json.JSONDecodeError)
async def json_decode_error_handler(request: Request, exc: json.JSONDecodeError):
    """Handle JSON decode errors."""
    request_id = str(uuid.uuid4())
    return await _log_and_return_error_response(request, exc, request_id, 400)


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """Handle generic exceptions."""
    request_id = str(uuid.uuid4())
    return await _log_and_return_error_response(request, exc, request_id, 500)


# Logging middleware
@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    """Log all requests and responses."""
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    
    debug(
        LogRecord(
            event="http_request",
            message=f"{request.method} {request.url.path}",
            data={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "process_time": round(process_time, 3),
            },
        )
    )
    
    return response


# Set function reference for deduplication module after all functions are defined
def _init_deduplication_references():
    """Initialize function references for deduplication module"""
    from caching.deduplication import set_make_anthropic_request
    set_make_anthropic_request(make_anthropic_request)

# Call initialization
_init_deduplication_references()


if __name__ == "__main__":
    # Display ASCII art banner
    banner = """
══════════════════════════════════════════════════════════════════════════════════════════════════════════════════════
 ▄████▄ ██       ▄███▄  ██    ██ ██████  ███████     ██████   ▄███▄  ██       ▄███▄  ███    ██  ▄████▄ ███████ ██████  
██      ██      ██   ██ ██    ██ ██   ██ ██          ██   ██ ██   ██ ██      ██   ██ ████   ██ ██      ██      ██   ██ 
██      ██      ███████ ██    ██ ██   ██ █████       ██████  ███████ ██      ███████ ██ ██  ██ ██      █████   ██████  
██      ██      ██   ██ ██    ██ ██   ██ ██          ██   ██ ██   ██ ██      ██   ██ ██  ██ ██ ██      ██      ██   ██ 
 ▀████▀ ███████ ██   ██  ██████  ██████  ███████     ██████  ██   ██ ███████ ██   ██ ██   ████  ▀████▀ ███████ ██   ██ 
══════════════════════════════════════════════════════════════════════════════════════════════════════════════════════
"""

    _console.print(banner, style="bold green")

    if provider_manager:
        # Display provider information
        providers_text = ""
        healthy_count = len(provider_manager.get_healthy_providers())
        total_count = len(provider_manager.providers)
        for i, provider in enumerate(provider_manager.providers):
            status_icon = "✓" if provider.is_healthy(provider_manager.get_failure_cooldown()) else "✗"
            provider_line = f"\n   [{status_icon}] {provider.name} ({provider.type.value}): {provider.base_url}"
            providers_text += provider_line
        
        # Convert absolute log file path to relative for display
        log_file_display = "Disabled"
        if settings.log_file_path:
            try:
                project_root = Path(__file__).parent.parent
                log_path = Path(settings.log_file_path)
                log_file_display = str(log_path.relative_to(project_root))
            except ValueError:
                # If path is not relative to project root, show basename
                log_file_display = Path(settings.log_file_path).name
        
        reload_enabled = global_config.get('settings', {}).get('reload', False)
        reload_status = "enabled" if reload_enabled else "disabled"
        reload_color = "green" if reload_enabled else "dim"
        
        config_details_text = Text.assemble(
            ("   Version       : ", "default"),
            (f"v{settings.app_version}", "bold cyan"),
            ("\n   Providers     : ", "default"),
            (f"{healthy_count}/{total_count} healthy", "bold green" if healthy_count > 0 else "bold red"),
            (providers_text, "default"),
            ("\n   Log Level     : ", "default"),
            (settings.log_level.upper(), "yellow"),
            ("\n   Log File      : ", "default"),
            (log_file_display, "dim"),
            ("\n   Auto Reload   : ", "default"),
            (reload_status, reload_color),
            ("\n   Listening on  : ", "default"),
            (f"http://{settings.host}:{settings.port}", "default")
        )
        title = "Claude Code Provider Balancer Configuration"
    else:
        reload_enabled = global_config.get('settings', {}).get('reload', False)
        reload_status = "enabled" if reload_enabled else "disabled"
        reload_color = "green" if reload_enabled else "dim"
        
        config_details_text = Text.assemble(
            ("   Version       : ", "default"),
            (f"v{settings.app_version}", "bold cyan"),
            ("\n   Status        : ", "default"),
            ("Provider manager failed to initialize", "bold red"),
            ("\n   Log Level     : ", "default"),
            (settings.log_level.upper(), "yellow"),
            ("\n   Auto Reload   : ", "default"),
            (reload_status, reload_color),
            ("\n   Listening on  : ", "default"),
            (f"http://{settings.host}:{settings.port}", "default"),
        )
        title = "Claude Code Provider Balancer Configuration (ERROR)"

    _console.print(
        Panel(
            config_details_text,
            title=title,
            border_style="blue",
            expand=False,
        )
    )
    _console.print(Rule("Starting uvicorn server ...", style="dim blue"))
    
    # Get reload setting from global config (already retrieved above)
    reload_enabled = global_config.get('settings', {}).get('reload', False)
    reload_includes = global_config.get('settings', {}).get('reload_includes', ["config.yaml", "*.py"]) if reload_enabled else None
    
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=reload_enabled,
        reload_includes=reload_includes,
        log_config=log_config,
    )