"""
Test providers router - Mock providers for testing various scenarios.

Provides endpoints that simulate different provider behaviors:
- Success responses 
- Error responses
- Streaming responses
- Delayed responses
- Specific error codes and types
"""

import asyncio
import json
import random
import time
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel

from models.requests import MessagesRequest
from models.responses import MessagesResponse, Usage
from models.content_blocks import ContentBlock, ContentBlockText
from models.messages import Message
from utils import debug, info, warning, error


class TestProviderConfig(BaseModel):
    """Configuration for test provider behavior."""
    delay_ms: int = 0
    error_rate: float = 0.0
    error_type: str = "internal_server_error"
    error_code: int = 500
    streaming_chunks: int = 5
    response_text: str = "This is a test response from mock provider."


def create_test_providers_router(config: Dict[str, Any]) -> APIRouter:
    """Create test providers router with configuration."""
    router = APIRouter(prefix="/test-providers", tags=["test-providers"])
    
    # Check if test providers are enabled
    test_settings = config.get("settings", {}).get("test_providers", {})
    if not test_settings.get("enabled", False):
        # Return empty router if disabled
        return router
    
    info("🧪 Test providers enabled - registering mock endpoints")
    
    @router.post("/anthropic/success")
    async def mock_anthropic_success(request: MessagesRequest):
        """Mock successful Anthropic response."""
        await _simulate_delay(test_settings.get("default_delay_ms", 100))
        
        response_text = test_settings.get("success_response_text", 
                                        "This is a successful mock response from the test provider.")
        
        response = MessagesResponse(
            id="test_msg_" + str(int(time.time())),
            type="message",
            role="assistant",
            content=[ContentBlockText(type="text", text=response_text)],
            model=request.model,
            stop_reason="end_turn",
            stop_sequence=None,
            usage=Usage(
                input_tokens=10,
                output_tokens=len(response_text.split())
            )
        )
        
        debug(f"📤 Test provider returning success response: {response.id}")
        return response
    
    @router.post("/anthropic/error/{error_type}")
    async def mock_anthropic_error(error_type: str, request: MessagesRequest):
        """Mock various error responses."""
        await _simulate_delay(test_settings.get("error_delay_ms", 50))
        
        error_configs = {
            "rate_limit": {"code": 429, "message": "Rate limit exceeded"},
            "server_error": {"code": 500, "message": "Internal server error"},
            "bad_gateway": {"code": 502, "message": "Bad gateway"},
            "timeout": {"code": 504, "message": "Gateway timeout"},
            "auth_error": {"code": 401, "message": "Authentication failed"},
            "not_found": {"code": 404, "message": "Endpoint not found"},
            "overloaded": {"code": 503, "message": "Server overloaded"}
        }
        
        error_config = error_configs.get(error_type, {"code": 500, "message": "Unknown error"})
        
        error(f"🚨 Test provider simulating {error_type} error")
        raise HTTPException(
            status_code=error_config["code"],
            detail={
                "type": "error",
                "error": {
                    "type": error_type,
                    "message": error_config["message"]
                }
            }
        )
    
    @router.post("/anthropic/streaming")
    async def mock_anthropic_streaming(request: MessagesRequest):
        """Mock streaming response."""
        if not request.stream:
            # Return non-streaming response
            return await mock_anthropic_success(request)
        
        debug("🌊 Test provider starting streaming response")
        
        async def generate_stream():
            """Generate streaming response chunks."""
            message_id = "test_stream_" + str(int(time.time()))
            chunk_count = test_settings.get("streaming_chunks", 5)
            chunk_delay = test_settings.get("chunk_delay_ms", 200)
            
            # Start event
            yield f'event: message_start\ndata: {json.dumps({"type": "message_start", "message": {"id": message_id, "type": "message", "role": "assistant", "content": [], "model": request.model, "stop_reason": None, "stop_sequence": None, "usage": {"input_tokens": 10, "output_tokens": 0}}})}\n\n'
            
            # Content chunks
            response_text = test_settings.get("streaming_response_text", 
                                            "This is a streaming test response from the mock provider.")
            words = response_text.split()
            words_per_chunk = max(1, len(words) // chunk_count)
            
            for i in range(0, len(words), words_per_chunk):
                chunk_words = words[i:i + words_per_chunk]
                chunk_text = " " + " ".join(chunk_words)
                
                if i > 0:  # Add space before non-first chunks
                    chunk_text = " " + chunk_text
                
                chunk_data = {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": chunk_text}
                }
                
                yield f'event: content_block_delta\ndata: {json.dumps(chunk_data)}\n\n'
                
                if chunk_delay > 0:
                    await asyncio.sleep(chunk_delay / 1000)
            
            # End events
            yield f'event: content_block_stop\ndata: {json.dumps({"type": "content_block_stop", "index": 0})}\n\n'
            yield f'event: message_delta\ndata: {json.dumps({"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None}, "usage": {"output_tokens": len(words)}})}\n\n'
            yield f'event: message_stop\ndata: {json.dumps({"type": "message_stop"})}\n\n'
        
        return StreamingResponse(
            generate_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
        )
    
    @router.post("/anthropic/random")
    async def mock_anthropic_random(request: MessagesRequest):
        """Mock provider with random behavior based on configuration."""
        error_rate = test_settings.get("random_error_rate", 0.2)
        
        if random.random() < error_rate:
            # Randomly select an error type
            error_types = ["rate_limit", "server_error", "timeout", "overloaded"]
            error_type = random.choice(error_types)
            return await mock_anthropic_error(error_type, request)
        else:
            return await mock_anthropic_success(request)
    
    @router.post("/anthropic/delay/{delay_ms}")
    async def mock_anthropic_delay(delay_ms: int, request: MessagesRequest):
        """Mock provider with configurable delay."""
        info(f"⏱️  Test provider simulating {delay_ms}ms delay")
        await asyncio.sleep(delay_ms / 1000)
        return await mock_anthropic_success(request)
    
    @router.post("/openai/success")
    async def mock_openai_success(request: dict):
        """Mock successful OpenAI response."""
        await _simulate_delay(test_settings.get("default_delay_ms", 100))
        
        response_text = test_settings.get("success_response_text", 
                                        "This is a successful mock response from the OpenAI test provider.")
        
        response = {
            "id": "test_openai_" + str(int(time.time())),
            "object": "chat.completion",
            "created": int(time.time()),
            "model": request.get("model", "gpt-3.5-turbo"),
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": response_text
                },
                "finish_reason": "stop"
            }],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": len(response_text.split()),
                "total_tokens": 10 + len(response_text.split())
            }
        }
        
        debug(f"📤 OpenAI test provider returning success response: {response['id']}")
        return response
    
    @router.get("/health")
    async def test_providers_health():
        """Health check endpoint for test providers."""
        return {
            "status": "healthy",
            "enabled": test_settings.get("enabled", False),
            "endpoints": [
                "/test-providers/anthropic/success",
                "/test-providers/anthropic/error/{error_type}",
                "/test-providers/anthropic/streaming", 
                "/test-providers/anthropic/random",
                "/test-providers/anthropic/delay/{delay_ms}",
                "/test-providers/openai/success"
            ],
            "configuration": test_settings
        }
    
    async def _simulate_delay(delay_ms: int):
        """Simulate processing delay."""
        if delay_ms > 0:
            await asyncio.sleep(delay_ms / 1000)
    
    return router