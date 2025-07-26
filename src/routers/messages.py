"""
Core message API routes for Claude Code Provider Balancer.
Handles the main /v1/messages endpoint and token counting.
"""

import json
import uuid
import httpx
from typing import Any, Dict

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import ValidationError

from handlers.message_handler import MessageHandler
from models import MessagesRequest, TokenCountRequest, TokenCountResponse
from core.provider_manager import ProviderManager, ProviderType
from core.streaming import (
    has_active_broadcaster, handle_duplicate_stream_request,
    create_broadcaster, register_broadcaster, unregister_broadcaster
)
from caching import (
    generate_request_signature, handle_duplicate_request,
    complete_and_cleanup_request, extract_content_from_sse_chunks
)
from conversion import (
    convert_anthropic_to_openai_messages, convert_anthropic_tools_to_openai,
    convert_anthropic_tool_choice_to_openai, convert_openai_to_anthropic_response
)
from utils import LogRecord, LogEvent, info, warning, error, debug
from utils.validation import validate_provider_health


def create_messages_router(provider_manager: ProviderManager, settings: Any) -> APIRouter:
    """Create messages router with dependencies."""
    router = APIRouter(prefix="/v1", tags=["API"])
    message_handler = MessageHandler(provider_manager, settings)

    @router.post("/messages", response_model=None, status_code=200)
    async def create_message_proxy(request: Request) -> JSONResponse:
        """Proxy endpoint for Anthropic Messages API."""
        request_id = str(uuid.uuid4())
        
        try:
            # Get request body for logging and caching
            raw_body = await request.body()
            parsed_body = json.loads(raw_body.decode('utf-8'))
            
            # Debug: Log client request headers and body
            # Uncomment for debugging purposes
            # debug(
            #     LogRecord(
            #         event=LogEvent.CLIENT_REQUEST_DEBUG.value,
            #         message="Client request received",
            #         request_id=request_id,
            #         data={
            #             "headers": dict(request.headers),
            #             "request_body": parsed_body,
            #             "method": request.method,
            #             "url": str(request.url)
            #         }
            #     )
            # )
            
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
                    message=message_handler._create_request_summary(parsed_body),
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
            provider_options = message_handler.select_model_and_provider_options(
                messages_request.model, request_id, provider_name
            )
            if not provider_options:
                error_msg = message_handler._create_no_providers_error_message(messages_request.model, provider_name)
                return await message_handler._log_and_return_error_response(
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
                        response = await message_handler.make_anthropic_request(
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
                        
                        response = await message_handler.make_openai_request(
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
                                        
                                        # Create provider stream from response using real-time streaming
                                        async def provider_stream():
                                            try:
                                                # Use the new streaming method that maintains httpx context
                                                async for response_obj in message_handler.make_anthropic_streaming_request(
                                                    current_provider, clean_request_body, request_id, original_headers
                                                ):
                                                    async for chunk in response_obj.aiter_text():
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
                                                    LogEvent.PROVIDER_UNHEALTHY_STREAM_ANTHROPIC.value,
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
                                            
                                            # Cannot failover for streaming, use delayed cleanup to allow client retry
                                            # Get cleanup delay from settings
                                            cleanup_delay = 3  # default
                                            if provider_manager and hasattr(provider_manager, 'settings'):
                                                cleanup_delay = provider_manager.settings.get('deduplication', {}).get('sse_error_cleanup_delay', 3)
                                            
                                            # Use delayed cleanup to keep request available for duplicate detection
                                            from caching.deduplication import complete_and_cleanup_request_delayed
                                            complete_and_cleanup_request_delayed(
                                                signature, 
                                                collected_chunks,  # Cache the actual stream content including errors
                                                collected_chunks, 
                                                True, 
                                                current_provider.name, 
                                                cleanup_delay
                                            )
                                            
                                            # Log that we're using delayed cleanup for SSE error
                                            info(
                                                LogRecord(
                                                    event=LogEvent.REQUEST_COMPLETED.value,
                                                    message=f"SSE error response cached with delayed cleanup: {current_provider.name}",
                                                    request_id=request_id,
                                                    data={
                                                        "provider": current_provider.name,
                                                        "model": target_model,
                                                        "stream": True,
                                                        "provider_type": "anthropic",
                                                        "chunks_count": len(collected_chunks),
                                                        "attempt": attempt + 1,
                                                        "cleanup_delay": cleanup_delay,
                                                        "error_type": error_type
                                                    }
                                                )
                                            )
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
                            # For OpenAI providers - handle streaming response
                            if hasattr(response, '__aiter__'):
                                # Response is an AsyncStream object, collect chunks for caching while streaming
                                collected_chunks = []
                                
                                async def stream_openai_response():
                                    """Handle OpenAI streaming response and convert to Anthropic format"""
                                    broadcaster = None
                                    try:
                                        # Create parallel broadcaster for handling multiple clients
                                        broadcaster = create_broadcaster(request, request_id, current_provider.name)
                                        
                                        # Register broadcaster for duplicate request handling
                                        register_broadcaster(signature, broadcaster)
                                        
                                        # Create provider stream from OpenAI AsyncStream
                                        async def provider_stream():
                                            try:
                                                async for chunk in response:
                                                    # Convert OpenAI chunk to Anthropic SSE format
                                                    if hasattr(chunk, 'choices') and chunk.choices:
                                                        choice = chunk.choices[0]
                                                        if hasattr(choice, 'delta') and choice.delta:
                                                            delta = choice.delta
                                                            if hasattr(delta, 'content') and delta.content:
                                                                # Create Anthropic-style text delta event
                                                                anthropic_chunk = {
                                                                    "type": "content_block_delta",
                                                                    "index": 0,
                                                                    "delta": {
                                                                        "type": "text_delta",
                                                                        "text": delta.content
                                                                    }
                                                                }
                                                                sse_data = f"data: {json.dumps(anthropic_chunk)}\n\n"
                                                                collected_chunks.append(sse_data)
                                                                yield sse_data
                                                            elif hasattr(choice, 'finish_reason') and choice.finish_reason:
                                                                # Create Anthropic-style message stop event
                                                                stop_chunk = {
                                                                    "type": "message_stop"
                                                                }
                                                                sse_data = f"data: {json.dumps(stop_chunk)}\n\n"
                                                                collected_chunks.append(sse_data)
                                                                yield sse_data
                                            except Exception as e:
                                                error(
                                                    LogRecord(
                                                        "openai_stream_error",
                                                        f"Error in OpenAI stream: {type(e).__name__}: {e}",
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
                                        
                                        # Complete the request with collected chunks
                                        complete_and_cleanup_request(signature, collected_chunks, collected_chunks, True, current_provider.name)
                                        
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
                                
                                return StreamingResponse(
                                    stream_openai_response(),
                                    media_type="text/event-stream",
                                    headers=stream_headers
                                )
                            else:
                                # If response is not streamable, convert to streaming format
                                response_data = response.json() if hasattr(response, 'json') else response
                                collected_chunks = [f"data: {json.dumps(response_data)}\n\n"]
                                
                                async def convert_to_stream():
                                    yield f"data: {json.dumps(response_data)}\n\n"
                                
                                complete_and_cleanup_request(signature, response_data, collected_chunks, True, current_provider.name)
                                
                                return StreamingResponse(
                                    convert_to_stream(),
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
                                return await message_handler._log_and_return_error_response(request, health_validation_error, request_id, 500, signature)
                    
                    # Provider is healthy, complete the request and cleanup
                    # For non-streaming responses, cache the actual content dict instead of JSON string array
                    
                    # uncomment this if you want to debug the response content before returning
                    # # Debug: Log response content before return
                    # debug(
                    #     LogRecord(
                    #         event="response_content",
                    #         message=f"Response content before return: type={type(response_content)}, content={str(response_content)[:500]}...",
                    #         request_id=request_id,
                    #         data={
                    #             "provider": current_provider.name,
                    #             "response_type": type(response_content).__name__,
                    #             "content_length": len(str(response_content)) if response_content else 0
                    #         }
                    #     )
                    # )
                    
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
                                return await message_handler._log_and_return_error_response(request, e, request_id, http_status_code, signature)
                    
                    # Use provider_manager to determine if we should failover
                    if provider_manager:
                        error_type, should_failover = provider_manager.get_error_classification(e, http_status_code)
                    else:
                        # Default failover behavior if provider_manager is not available
                        should_failover = True
                        error_type = "unknown_error"
                    
                    # If we shouldn't failover, return the error immediately
                    if not should_failover:
                        # Mark provider as used for sticky logic
                        if provider_manager:
                            provider_manager.mark_provider_used(current_provider.name)
                        
                        info(
                            LogRecord(
                                event=LogEvent.ERROR_NOT_RETRYABLE.value,
                                message=f"Error type '{error_type}' not configured for failover, returning to client",
                                request_id=request_id,
                                data={
                                    "provider": current_provider.name,
                                    "error_type": error_type,
                                    "http_status_code": http_status_code
                                }
                            )
                        )
                        return await message_handler._log_and_return_error_response(request, e, request_id, 500, signature)
                    
                    # Mark current provider as failed since we are failing over
                    current_provider.mark_failure()
                    
                    # If we have more providers to try, continue to next iteration
                    if attempt < max_attempts - 1:
                        next_target_model, next_provider = provider_options[attempt + 1]
                        info(
                            LogRecord(
                                event=LogEvent.PROVIDER_FALLBACK.value,
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
                    event=LogEvent.ALL_PROVIDERS_FAILED.value,
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
            client_error_message = message_handler._create_no_providers_error_message(messages_request.model)
            client_error = Exception(client_error_message)
            
            return await message_handler._log_and_return_error_response(request, client_error, request_id, 500, signature)
                
        except ValidationError as e:
            # ValidationError发生在生成signature之前，无需cleanup
            return await message_handler._log_and_return_error_response(request, e, request_id, 400)
        except json.JSONDecodeError as e:
            # JSONDecodeError发生在生成signature之前，无需cleanup
            return await message_handler._log_and_return_error_response(request, e, request_id, 400)
        except Exception as e:
            # 通用异常可能在任何阶段发生，尝试cleanup（如果signature不存在会被安全忽略）
            return await message_handler._log_and_return_error_response(request, e, request_id, 500, locals().get('signature'))

    @router.post("/messages/count_tokens", response_model=TokenCountResponse)
    async def count_tokens_endpoint(request: Request) -> TokenCountResponse:
        """Estimates token count for given Anthropic messages and system prompt."""
        return await message_handler.count_tokens(request)

    return router