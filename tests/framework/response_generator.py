"""
Mock response generator for different provider behaviors.
"""

import asyncio
import json
import uuid
from typing import Dict, Any, Optional, Union
from fastapi import HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

from .test_scenario import ProviderBehavior, ProviderConfig


class MockResponseGenerator:
    """Generates mock responses based on provider behavior configuration."""
    
    @staticmethod
    async def generate(
        behavior: ProviderBehavior, 
        request_data: Dict[str, Any], 
        provider_config: ProviderConfig
    ) -> Union[JSONResponse, StreamingResponse]:
        """Generate response based on behavior type."""
        
        # Apply delay if configured
        if provider_config.delay_ms > 0:
            await asyncio.sleep(provider_config.delay_ms / 1000)
        
        # Handle different behaviors
        match behavior:
            case ProviderBehavior.SUCCESS:
                return MockResponseGenerator._create_success_response(request_data, provider_config)
            
            case ProviderBehavior.STREAMING_SUCCESS:
                return MockResponseGenerator._create_streaming_success_response(request_data, provider_config)
            
            case ProviderBehavior.DUPLICATE_CACHE:
                return MockResponseGenerator._create_deterministic_response(request_data, provider_config)
            
            case ProviderBehavior.ERROR:
                return MockResponseGenerator._create_error_response(
                    provider_config.error_http_code, 
                    provider_config.error_message
                )
            
            case ProviderBehavior.TIMEOUT:
                # Simulate timeout by sleeping longer than expected timeout
                await asyncio.sleep(10)
                return MockResponseGenerator._create_error_response(408, "Request Timeout")
            
            case ProviderBehavior.RATE_LIMIT:
                return MockResponseGenerator._create_error_response(429, "Rate Limited")
            
            case ProviderBehavior.CONNECTION_ERROR:
                return MockResponseGenerator._create_error_response(502, "Connection Error")
            
            case ProviderBehavior.SSL_ERROR:
                return MockResponseGenerator._create_error_response(502, "SSL Error")
            
            case ProviderBehavior.INTERNAL_SERVER_ERROR:
                return MockResponseGenerator._create_error_response(500, "Internal Server Error")
            
            case ProviderBehavior.BAD_GATEWAY:
                return MockResponseGenerator._create_error_response(502, "Bad Gateway")
            
            case ProviderBehavior.SERVICE_UNAVAILABLE:
                return MockResponseGenerator._create_error_response(503, "Service Unavailable")
            
            case ProviderBehavior.INSUFFICIENT_CREDITS:
                return MockResponseGenerator._create_insufficient_credits_response()
            
            case _:
                return MockResponseGenerator._create_error_response(500, f"Unknown behavior: {behavior}")
    
    @staticmethod
    def _create_success_response(request_data: Dict[str, Any], provider_config: ProviderConfig) -> JSONResponse:
        """Create a successful Anthropic API response."""
        is_streaming = request_data.get('stream', False)
        
        if is_streaming:
            return MockResponseGenerator._create_streaming_success_response(request_data, provider_config)
        else:
            return MockResponseGenerator._create_non_streaming_success_response(request_data, provider_config)
    
    @staticmethod
    def _create_non_streaming_success_response(
        request_data: Dict[str, Any], 
        provider_config: ProviderConfig
    ) -> JSONResponse:
        """Create non-streaming success response."""
        # Use custom response data if provided
        if provider_config.response_data:
            content = provider_config.response_data.get('content', 'Mock success response')
        else:
            content = f"Mock success response from {provider_config.name}"
        
        response_data = {
            "id": f"msg_{uuid.uuid4().hex[:12]}",
            "type": "message",
            "role": "assistant",
            "content": [
                {
                    "type": "text",
                    "text": content
                }
            ],
            "model": request_data.get("model", "mock-model"),
            "stop_reason": "end_turn",
            "usage": {
                "input_tokens": len(str(request_data.get('messages', []))),
                "output_tokens": len(content)
            }
        }
        
        return JSONResponse(status_code=200, content=response_data)
    
    @staticmethod
    def _create_streaming_success_response(
        request_data: Dict[str, Any], 
        provider_config: ProviderConfig
    ) -> StreamingResponse:
        """Create streaming success response."""
        async def generate_stream():
            # Use custom response data if provided
            if provider_config.response_data:
                content = provider_config.response_data.get('content', 'Mock streaming response')
            else:
                content = f"Mock streaming response from {provider_config.name}"
            
            # Message start event
            start_event = {
                "type": "message_start",
                "message": {
                    "id": f"msg_{uuid.uuid4().hex[:12]}",
                    "type": "message",
                    "role": "assistant",
                    "content": [],
                    "model": request_data.get("model", "mock-model"),
                    "stop_reason": None,
                    "usage": {"input_tokens": 0, "output_tokens": 0}
                }
            }
            yield f"data: {json.dumps(start_event)}\\n\\n"
            
            # Content block start
            content_start = {
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "text", "text": ""}
            }
            yield f"data: {json.dumps(content_start)}\\n\\n"
            
            # Stream content in chunks
            words = content.split()
            for i, word in enumerate(words):
                chunk = {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": word + (" " if i < len(words) - 1 else "")}
                }
                yield f"data: {json.dumps(chunk)}\\n\\n"
                await asyncio.sleep(0.01)  # Small delay between chunks
            
            # Content block stop
            content_stop = {"type": "content_block_stop", "index": 0}
            yield f"data: {json.dumps(content_stop)}\\n\\n"
            
            # Message stop
            message_stop = {
                "type": "message_stop",
                "usage": {"input_tokens": 10, "output_tokens": len(words)}
            }
            yield f"data: {json.dumps(message_stop)}\\n\\n"
        
        return StreamingResponse(
            generate_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
        )
    
    @staticmethod
    def _create_deterministic_response(
        request_data: Dict[str, Any], 
        provider_config: ProviderConfig
    ) -> JSONResponse:
        """Create deterministic response for duplicate request testing."""
        # Create a hash of request content for deterministic responses
        request_hash = hash(str(sorted(request_data.items())))
        
        # Use custom response data if provided
        if provider_config.response_data:
            content = provider_config.response_data.get('content', 'Cached response')
        else:
            content = f"Deterministic response for hash: {abs(request_hash) % 10000}"
        
        response_data = {
            "id": f"msg_cache_{abs(request_hash) % 10000}",
            "type": "message", 
            "role": "assistant",
            "content": [{"type": "text", "text": content}],
            "model": request_data.get("model", "mock-model"),
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": len(content)},
            "_mock_cache_key": str(request_hash)  # For testing purposes
        }
        
        return JSONResponse(status_code=200, content=response_data)
    
    @staticmethod
    def _create_error_response(status_code: int, message: str) -> JSONResponse:
        """Create error response."""
        error_data = {
            "error": {
                "type": "error",
                "message": message
            }
        }
        return JSONResponse(status_code=status_code, content=error_data)
    
    @staticmethod
    def _create_insufficient_credits_response() -> JSONResponse:
        """Create insufficient credits error response."""
        error_data = {
            "error": {
                "type": "error",
                "message": "Insufficient credits",
                "details": "Your account has insufficient credits to complete this request"
            }
        }
        return JSONResponse(status_code=402, content=error_data)