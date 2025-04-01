"""
Tests for error handling in the API.
"""

from unittest.mock import patch

import httpx
import openai
import pytest
from fastapi.testclient import TestClient

from claude_proxy.api import app


@pytest.fixture
def client():
    """Test client fixture."""
    return TestClient(app)


@pytest.mark.parametrize(
    "status_code,openai_error,anthropic_error_type",
    [
        (401, "Invalid API key", "authentication_error"),
        (403, "Permission denied", "permission_error"),
        (429, "Rate limit exceeded", "rate_limit_error"),
        (400, "Bad request parameters", "invalid_request_error"),
        (404, "Resource not found", "not_found_error"),
        (413, "Request too large", "request_too_large"),
        (422, "Validation failed", "invalid_request_error"),
        (500, "Internal server error", "api_error"),
        (503, "Service unavailable", "overloaded_error"),
    ],
)
def test_openai_error_mapping(client, status_code, openai_error, anthropic_error_type):
    """Test mapping of OpenAI/OpenRouter errors to Anthropic error format."""

    mock_request = httpx.Request(
        "POST", "https://test.openrouter.ai/api/v1/chat/completions"
    )
    mock_response = httpx.Response(
        status_code=status_code,
        json={"error": {"message": openai_error}},
        request=mock_request,
    )

    error_classes = {
        401: openai.AuthenticationError,
        403: openai.PermissionDeniedError,
        429: openai.RateLimitError,
        400: openai.BadRequestError,
        404: openai.NotFoundError,
        422: openai.UnprocessableEntityError,
        500: openai.InternalServerError,
    }

    error_class = error_classes.get(status_code, openai.APIStatusError)
    api_error = error_class(
        message=openai_error,
        response=mock_response,
        body={"error": {"message": openai_error}},
    )

    with patch(
        "claude_proxy.api.client.chat.completions.create", side_effect=api_error
    ):
        request_data = {
            "model": "claude-3-opus-20240229",
            "messages": [{"role": "user", "content": "Hello"}],
            "max_tokens": 1024,
        }

        response = client.post("/v1/messages", json=request_data)

        assert response.status_code == status_code
        data = response.json()
        assert data["type"] == "error"
        assert data["error"]["type"] == anthropic_error_type
        assert openai_error in data["error"]["message"], (
            f"Expected error message to contain '{openai_error}'"
        )


@pytest.mark.parametrize(
    "exception,expected_status,anthropic_error_type",
    [
        (httpx.ConnectError("Failed to connect"), 502, "api_error"),
        (httpx.ConnectTimeout("Request timed out"), 502, "api_error"),
        (httpx.ReadError("Failed to read response"), 502, "api_error"),
    ],
)
def test_network_error_mapping(
    client, exception, expected_status, anthropic_error_type
):
    """Test mapping of network-level errors to Anthropic error format."""

    mock_request = httpx.Request(
        "POST", "https://test.openrouter.ai/api/v1/chat/completions"
    )

    if isinstance(
        exception, (httpx.ConnectError, httpx.ReadError, httpx.ConnectTimeout)
    ):
        api_error = openai.APIConnectionError(
            message=str(exception), request=mock_request
        )
    else:
        api_error = exception

    with patch(
        "claude_proxy.api.client.chat.completions.create", side_effect=api_error
    ):
        request_data = {
            "model": "claude-3-opus-20240229",
            "messages": [{"role": "user", "content": "Hello"}],
            "max_tokens": 1024,
        }

        response = client.post("/v1/messages", json=request_data)

        assert response.status_code == expected_status
        data = response.json()
        assert data["type"] == "error"
        assert data["error"]["type"] == anthropic_error_type
        assert "message" in data["error"]


def test_invalid_request_format(client):
    """Test error handling for invalid request format."""

    request_data = {
        "model": "claude-3-opus-20240229",
    }

    response = client.post("/v1/messages", json=request_data)

    assert response.status_code == 422
    data = response.json()
    assert data["type"] == "error"
    assert data["error"]["type"] == "invalid_request_error"
    assert "message" in data["error"]


def test_invalid_json_format(client):
    """Test error handling for invalid JSON in request."""

    response = client.post(
        "/v1/messages",
        headers={"Content-Type": "application/json"},
        content="this is not valid json",
    )

    assert response.status_code == 400
    data = response.json()
    assert data["type"] == "error"
    assert data["error"]["type"] == "invalid_request_error"
    assert "message" in data["error"]


def test_streaming_rate_limit_error(client):
    mock_request = httpx.Request(
        "POST", "https://test.openrouter.ai/api/v1/chat/completions"
    )
    mock_response = httpx.Response(
        status_code=429,
        json={"error": {"message": "Rate limit exceeded for streaming"}},
        request=mock_request,
    )

    streaming_error = openai.RateLimitError(
        message="Rate limit exceeded for streaming",
        response=mock_response,
        body={"error": {"message": "Rate limit exceeded for streaming"}},
    )

    with patch(
        "claude_proxy.api.client.chat.completions.create", side_effect=streaming_error
    ):
        request_data = {
            "model": "claude-3-opus-20240229",
            "messages": [{"role": "user", "content": "Hello"}],
            "max_tokens": 1024,
            "stream": True,
        }

        response = client.post("/v1/messages", json=request_data)

        assert response.status_code == 429
        assert response.headers["content-type"] == "application/json"

        data = response.json()
        assert data["type"] == "error"
        assert data["error"]["type"] == "rate_limit_error"
        assert "message" in data["error"]


def test_streaming_server_error(client):
    mock_request = httpx.Request(
        "POST", "https://test.openrouter.ai/api/v1/chat/completions"
    )
    mock_response = httpx.Response(
        status_code=500,
        json={"error": {"message": "Internal server error during streaming"}},
        request=mock_request,
    )

    streaming_error = openai.InternalServerError(
        message="Internal server error during streaming",
        response=mock_response,
        body={"error": {"message": "Internal server error during streaming"}},
    )

    with patch(
        "claude_proxy.api.client.chat.completions.create", side_effect=streaming_error
    ):
        request_data = {
            "model": "claude-3-opus-20240229",
            "messages": [{"role": "user", "content": "Hello"}],
            "max_tokens": 1024,
            "stream": True,
        }

        response = client.post("/v1/messages", json=request_data)

        assert response.status_code == 500
        assert response.headers["content-type"] == "application/json"

        data = response.json()
        assert data["type"] == "error"
        assert data["error"]["type"] == "api_error"
        assert "message" in data["error"]


def test_streaming_connection_error(client):
    mock_request = httpx.Request(
        "POST", "https://test.openrouter.ai/api/v1/chat/completions"
    )

    connection_error = openai.APIConnectionError(
        message="Connection error during streaming", request=mock_request
    )

    with patch(
        "claude_proxy.api.client.chat.completions.create", side_effect=connection_error
    ):
        request_data = {
            "model": "claude-3-opus-20240229",
            "messages": [{"role": "user", "content": "Hello"}],
            "max_tokens": 1024,
            "stream": True,
        }

        response = client.post("/v1/messages", json=request_data)

        assert response.status_code == 502
        assert response.headers["content-type"] == "application/json"

        data = response.json()
        assert data["type"] == "error"
        assert data["error"]["type"] == "api_error"
        assert "message" in data["error"]
