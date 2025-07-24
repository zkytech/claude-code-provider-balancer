"""Mock templates for test providers.

This module provides standardized mock configurations for testing.
All tests should use these templates to ensure consistency.
"""

from httpx import Response
from typing import Dict, Any, AsyncGenerator


class MockProviders:
    """Standardized mock provider URLs."""
    
    # Anthropic test providers
    ANTHROPIC_SUCCESS = "http://localhost:9090/test-providers/anthropic/success"
    ANTHROPIC_ERROR = "http://localhost:9090/test-providers/anthropic/error/server_error"
    ANTHROPIC_RATE_LIMIT = "http://localhost:9090/test-providers/anthropic/error/rate_limit"
    ANTHROPIC_INVALID_REQUEST = "http://localhost:9090/test-providers/anthropic/error/invalid_request"
    
    # OpenAI test providers  
    OPENAI_SUCCESS = "http://localhost:9090/test-providers/openai/success"
    OPENAI_ERROR = "http://localhost:9090/test-providers/openai/error/server_error"
    OPENAI_RATE_LIMIT = "http://localhost:9090/test-providers/openai/error/rate_limit"


class MockResponses:
    """Standardized mock response templates."""
    
    @staticmethod
    def anthropic_success_response(content: str = "Hello from Claude") -> Dict[str, Any]:
        """Standard Anthropic success response."""
        return {
            "id": "msg_test_success",
            "type": "message",
            "role": "assistant",
            "content": [
                {
                    "type": "text",
                    "text": content
                }
            ],
            "model": "claude-3-5-sonnet-20241022",
            "stop_reason": "end_turn",
            "stop_sequence": None,
            "usage": {
                "input_tokens": 10,
                "output_tokens": 5
            }
        }
    
    @staticmethod
    def openai_success_response(content: str = "Hello from OpenAI") -> Dict[str, Any]:
        """Standard OpenAI success response."""
        return {
            "id": "chatcmpl-test-success",
            "object": "chat.completion",
            "created": 1234567890,
            "model": "gpt-4",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": content
                    },
                    "finish_reason": "stop"
                }
            ],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15
            }
        }
    
    @staticmethod
    def error_response(error_type: str = "server_error", message: str = "Internal server error") -> Dict[str, Any]:
        """Standard error response template."""
        return {
            "type": "error",
            "error": {
                "type": error_type,
                "message": message
            }
        }
    
    @staticmethod
    def rate_limit_error() -> Dict[str, Any]:
        """Standard rate limit error response."""
        return MockResponses.error_response("rate_limit_error", "Rate limit exceeded")
    
    @staticmethod
    def invalid_request_error() -> Dict[str, Any]:
        """Standard invalid request error response."""
        return MockResponses.error_response("invalid_request_error", "Invalid request parameters")


class MockStreamingResponses:
    """Standardized streaming response templates."""
    
    @staticmethod
    async def anthropic_streaming_success(content: str = "Hello from streaming") -> AsyncGenerator[bytes, None]:
        """Standard Anthropic streaming success response."""
        yield b'event: message_start\ndata: {"type": "message_start", "message": {"id": "msg_test_success", "type": "message", "role": "assistant", "content": [], "model": "claude-3-5-sonnet-20241022", "stop_reason": null, "stop_sequence": null, "usage": {"input_tokens": 10, "output_tokens": 0}}}\n\n'
        yield b'event: content_block_start\ndata: {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}\n\n'
        
        # Split content into chunks for realistic streaming
        words = content.split()
        for word in words:
            yield f'event: content_block_delta\ndata: {{"type": "content_block_delta", "index": 0, "delta": {{"type": "text_delta", "text": "{word} "}}}}\n\n'.encode()
        
        yield b'event: content_block_stop\ndata: {"type": "content_block_stop", "index": 0}\n\n'
        yield b'event: message_delta\ndata: {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": null}, "usage": {"output_tokens": 3}}\n\n'
        yield b'event: message_stop\ndata: {"type": "message_stop"}\n\n'
    
    @staticmethod
    async def interrupted_streaming() -> AsyncGenerator[bytes, None]:
        """Streaming response that gets interrupted."""
        yield b'event: message_start\ndata: {"type": "message_start"}\n\n'
        yield b'event: content_block_delta\ndata: {"type": "content_block_delta"}\n\n'
        # Simulate interruption - no more data


class MockHelper:
    """Helper functions for setting up mocks."""
    
    @staticmethod
    def setup_anthropic_success_mock(respx_mock, content: str = "Hello from Claude"):
        """Set up a standard Anthropic success mock."""
        respx_mock.post(MockProviders.ANTHROPIC_SUCCESS).mock(
            return_value=Response(200, json=MockResponses.anthropic_success_response(content))
        )
    
    @staticmethod
    def setup_openai_success_mock(respx_mock, content: str = "Hello from OpenAI"):
        """Set up a standard OpenAI success mock."""
        respx_mock.post(MockProviders.OPENAI_SUCCESS).mock(
            return_value=Response(200, json=MockResponses.openai_success_response(content))
        )
    
    @staticmethod
    def setup_anthropic_streaming_mock(respx_mock, content: str = "Hello from streaming"):
        """Set up a standard Anthropic streaming mock."""
        respx_mock.post(MockProviders.ANTHROPIC_SUCCESS).mock(
            return_value=Response(
                200,
                headers={"content-type": "text/event-stream"},
                stream=MockStreamingResponses.anthropic_streaming_success(content)
            )
        )
    
    @staticmethod
    def setup_error_mock(respx_mock, provider_url: str, status_code: int = 500, error_type: str = "server_error"):
        """Set up a standard error mock."""
        respx_mock.post(provider_url).mock(
            return_value=Response(status_code, json=MockResponses.error_response(error_type))
        )
    
    @staticmethod
    def setup_rate_limit_mock(respx_mock, provider_url: str):
        """Set up a rate limit error mock."""
        respx_mock.post(provider_url).mock(
            return_value=Response(429, json=MockResponses.rate_limit_error())
        )


# Usage examples in docstring
"""
Usage Examples:

# Basic success mock
with respx.mock:
    MockHelper.setup_anthropic_success_mock(respx, "Hello World")
    # Your test code here

# Streaming mock
with respx.mock:
    MockHelper.setup_anthropic_streaming_mock(respx, "Streaming response")
    # Your test code here

# Error mock
with respx.mock:
    MockHelper.setup_error_mock(respx, MockProviders.ANTHROPIC_SUCCESS, 500)
    # Your test code here

# Manual mock setup
with respx.mock:
    respx.post(MockProviders.ANTHROPIC_SUCCESS).mock(
        return_value=Response(200, json=MockResponses.anthropic_success_response("Custom content"))
    )
    # Your test code here
"""