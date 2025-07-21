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
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

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
try:
    # Try relative imports first (when run as module)
    from .provider_manager import ProviderManager, Provider, ProviderType, StreamingMode
    from .log_utils import (
        LogRecord, LogEvent, LogError,
        ColoredConsoleFormatter, JSONFormatter, ConsoleJSONFormatter,
        init_logger, debug, info, warning, error, critical
    )
    from .models import (
        MessagesRequest, TokenCountRequest, TokenCountResponse,
        MessagesResponse, AnthropicErrorResponse
    )
    from .caching import (
        generate_request_signature, handle_duplicate_request,
        cleanup_stuck_requests, simulate_testing_delay,
        complete_and_cleanup_request, serve_waiting_duplicate_requests,
        update_response_cache, validate_response_quality, extract_content_from_sse_chunks
    )
    from .conversion import (
        get_token_encoder, count_tokens_for_anthropic_request,
        convert_anthropic_to_openai_messages, convert_anthropic_tools_to_openai,
        convert_anthropic_tool_choice_to_openai, convert_openai_to_anthropic_response,
        get_anthropic_error_details_from_exc, build_anthropic_error_response
    )
except ImportError:
    # Fall back to absolute imports (when run directly)
    from provider_manager import ProviderManager, Provider, ProviderType, StreamingMode
    from log_utils import (
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
        complete_and_cleanup_request, serve_waiting_duplicate_requests,
        update_response_cache, validate_response_quality, extract_content_from_sse_chunks
    )
    from conversion import (
        get_token_encoder, count_tokens_for_anthropic_request,
        convert_anthropic_to_openai_messages, convert_anthropic_tools_to_openai,
        convert_anthropic_tool_choice_to_openai, convert_openai_to_anthropic_response,
        get_anthropic_error_details_from_exc, build_anthropic_error_response
    )

load_dotenv()

# Initialize rich console
_console = Console()


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
        self.providers_config_path: str = "providers.yaml"
        self.referrer_url: str = "http://localhost:8082/claude_proxy"
        self.reload: bool = True
        self.host: str = "127.0.0.1"
        self.port: int = 8080
        self.app_name: str = "Claude Code Provider Balancer"
        self.app_version: str = "0.5.0"
        
    def load_from_provider_config(self, config_path: str = "providers.yaml"):
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
            "()": "log_utils.formatters.UvicornAccessFormatter",
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

# FastAPI app
app = fastapi.FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Intelligent load balancer and failover proxy for Claude Code providers",
)

# 存储token刷新任务的全局变量
_token_refresh_tasks = []

@app.on_event("startup")
async def startup_event():
    """FastAPI应用启动时的初始化"""
    global _token_refresh_tasks
    
    try:
        # 导入token刷新模块
        from .token_refresher import start_token_refresh_loop
    except ImportError:
        from token_refresher import start_token_refresh_loop
    
    # 为每个启用了auto_refresh的provider启动刷新任务
    if provider_manager:
        for provider_config in provider_manager.providers:
            # 查找原始配置以获取auto_refresh_config
            try:
                with open(provider_manager.config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                
                for provider_raw in config.get('providers', []):
                    if provider_raw.get('name') == provider_config.name:
                        auto_refresh_config = provider_raw.get('auto_refresh_config', {})
                        if auto_refresh_config.get('enabled', False):
                            info(f"Starting token refresh for provider: {provider_config.name}")
                            task = asyncio.create_task(
                                start_token_refresh_loop(
                                    provider_config.name, 
                                    provider_raw, 
                                    provider_manager
                                )
                            )
                            _token_refresh_tasks.append(task)
                        break
            except Exception as e:
                error(f"Failed to start token refresh for provider {provider_config.name}: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    """FastAPI应用关闭时的清理"""
    global _token_refresh_tasks
    
    # 取消所有token刷新任务
    for task in _token_refresh_tasks:
        task.cancel()
    
    # 等待任务完成取消
    if _token_refresh_tasks:
        await asyncio.gather(*_token_refresh_tasks, return_exceptions=True)
    
    _token_refresh_tasks.clear()
    info("Token refresh tasks stopped")


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
                response.raise_for_status()
            
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


async def _log_and_return_error_response(
    request: Request,
    exc: Exception,
    request_id: str,
    status_code: int = 500,
) -> JSONResponse:
    """Log error and return formatted error response."""
    error_type, message, _, provider_details = get_anthropic_error_details_from_exc(exc)
    
    error(
        LogRecord(
            event=LogEvent.REQUEST_FAILURE.value,
            message=f"Request failed: {message}",
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
        
        # Check for duplicate requests
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
            if provider_name:
                error_msg = f"Provider '{provider_name}' not found, unhealthy, or not configured for model: {messages_request.model}"
            else:
                error_msg = f"No available providers for model: {messages_request.model}"
            return await _log_and_return_error_response(
                request, Exception(error_msg), request_id, 404
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
                            # Collect chunks for caching while streaming
                            collected_chunks = []
                            
                            async def stream_anthropic_response():
                                async for chunk in response.aiter_text():
                                    collected_chunks.append(chunk)
                                    yield chunk
                                
                                # Stream completed, validate quality and cache if successful
                                # Check HTTP status code to skip quality validation on errors
                                status_code = getattr(response, 'status_code', None)
                                if validate_response_quality(collected_chunks, current_provider.name, request_id, status_code):
                                    # Quality validation passed, extract content as result
                                    try:
                                        response_content = extract_content_from_sse_chunks(collected_chunks)
                                        complete_and_cleanup_request(signature, response_content, collected_chunks, True, current_provider.name)
                                    except Exception as e:
                                        # Content extraction failed
                                        extraction_error = Exception(f"Response content extraction failed: {str(e)}")
                                        complete_and_cleanup_request(signature, extraction_error, None, True, current_provider.name)
                                else:
                                    # Quality validation failed, mark as error to allow retry
                                    quality_error = Exception("Response quality validation failed")
                                    complete_and_cleanup_request(signature, quality_error, None, True, current_provider.name)
                            
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
                            message_id = str(uuid.uuid4())
                            first_chunk = True
                            
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
                            
                            # Stream completed, validate quality and cache if successful
                            # For OpenAI streaming, HTTP errors typically raise exceptions before we reach here
                            if validate_response_quality(collected_chunks, current_provider.name, request_id, None):
                                try:
                                    response_content = extract_content_from_sse_chunks(collected_chunks)
                                    complete_and_cleanup_request(signature, response_content, collected_chunks, True, current_provider.name)
                                except Exception as e:
                                    extraction_error = Exception(f"Response content extraction failed: {str(e)}")
                                    complete_and_cleanup_request(signature, extraction_error, None, True, current_provider.name)
                            else:
                                quality_error = Exception("Response quality validation failed")
                                complete_and_cleanup_request(signature, quality_error, None, True, current_provider.name)
                        
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
                
                # Complete the request and cleanup
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
                    debug(f"Failed to create debug info: {debug_error}")

                # Extract HTTP response details for comprehensive error logging
                response_details = None
                if hasattr(e, 'response') and e.response is not None:
                    try:
                        response_details = {
                            "response_headers": dict(e.response.headers),
                            "response_body": e.response.text[:1000] if hasattr(e.response, 'text') and e.response.text else None
                        }
                    except Exception:
                        # Ignore errors when extracting response details
                        pass
                
                warning(
                    LogRecord(
                        event="provider_request_failed",
                        message=f"Request failed for provider {current_provider.name} (attempt {attempt + 1}/{max_attempts}): {str(e)}",
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
                            "response_details": response_details
                        }
                    ),
                    exc=e
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
                    complete_and_cleanup_request(signature, e, None, False, current_provider.name)
                    return await _log_and_return_error_response(request, e, request_id)
                
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
        
        complete_and_cleanup_request(signature, last_exception, None, False, "unknown")
        return await _log_and_return_error_response(request, last_exception or Exception("All providers failed"), request_id)
            
    except ValidationError as e:
        return await _log_and_return_error_response(request, e, request_id, 400)
    except json.JSONDecodeError as e:
        return await _log_and_return_error_response(request, e, request_id, 400)
    except Exception as e:
        return await _log_and_return_error_response(request, e, request_id)


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


@app.post("/providers/reload", tags=["Health"])
async def reload_providers_config() -> JSONResponse:
    """Reload providers configuration from file."""
    global provider_manager
    try:
        provider_manager = ProviderManager()
        # Update the provider manager reference in deduplication module
        from caching.deduplication import set_provider_manager, set_make_anthropic_request
        set_provider_manager(provider_manager)
        set_make_anthropic_request(make_anthropic_request)
        return JSONResponse(content={"status": "configuration reloaded successfully"})
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to reload configuration: {str(e)}"}
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
            ("\n   Listening on  : ", "default"),
            (f"http://{settings.host}:{settings.port}", "default"),
            ("\n   Reload        : ", "default"),
            ("Enabled", "bold orange1") if settings.reload else ("Disabled", "dim")
        )
        title = "Claude Code Provider Balancer Configuration"
    else:
        config_details_text = Text.assemble(
            ("   Version       : ", "default"),
            (f"v{settings.app_version}", "bold cyan"),
            ("\n   Status        : ", "default"),
            ("Provider manager failed to initialize", "bold red"),
            ("\n   Log Level     : ", "default"),
            (settings.log_level.upper(), "yellow"),
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
    
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
        log_config=log_config,
    )