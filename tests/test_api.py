"""
Tests for the FastAPI endpoints and helper functions within src/claude_proxy/api.py.
"""

import json
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from claude_proxy import models
from claude_proxy.api import (app, extract_provider_error_details,
                              get_error_response)


@pytest.fixture
def client():
    """Test client fixture."""
    return TestClient(app)

@pytest.fixture
def mock_completion():
    completion = models.MessagesResponse(
        id="msg_mock123",
        type="message",
        role="assistant",
        model="claude-3-opus-20240229",
        content=[models.ContentBlockText(type="text", text="Mock response")],
        stop_reason="end_turn",
        usage=models.Usage(input_tokens=10, output_tokens=5)
    )
    return completion

@pytest.fixture
def mock_openai_client_create(mocker):
    """Mocks the client.chat.completions.create method."""
    mock_create = AsyncMock()
    mocker.patch("claude_proxy.api.client.chat.completions.create", mock_create)
    return mock_create

def test_count_tokens_endpoint(client):
    """Tests the /v1/messages/count_tokens endpoint returns zero."""
    request_data = {
        "model": "claude-3-opus-20240229",
        "messages": [{"role": "user", "content": "Count these tokens"}],
    }

    response = client.post("/v1/messages/count_tokens", json=request_data)

    assert response.status_code == 200
    data = response.json()
    assert data == {"input_tokens": 4}

def test_extract_provider_error_details_variations():
    """Tests extract_provider_error_details with different inputs."""
    valid_details = {
        "message": "Provider error",
        "metadata": {
            "provider_name": "google",
            "raw": json.dumps({"error": {"code": 400, "message": "Bad tool schema"}}),
        },
    }
    result = extract_provider_error_details(valid_details)
    assert isinstance(result, models.ProviderErrorMetadata)
    assert result.provider_name == "google"
    assert result.raw_error == {"error": {"code": 400, "message": "Bad tool schema"}}

    missing_meta = {"message": "Some error"}
    assert extract_provider_error_details(missing_meta) is None

    missing_raw = {"message": "Provider error", "metadata": {"provider_name": "google"}}
    assert extract_provider_error_details(missing_raw) is None

    malformed_raw = {
        "message": "Provider error",
        "metadata": {"provider_name": "google", "raw": "{invalid json"},
    }
    assert extract_provider_error_details(malformed_raw) is None

    assert extract_provider_error_details("not a dict") is None
    assert extract_provider_error_details(None) is None

def test_get_error_response_formatting():
    """Tests the formatting of AnthropicErrorResponse."""
    error_resp1 = get_error_response(
        models.AnthropicErrorType.INVALID_REQUEST, "Missing parameter"
    )
    assert error_resp1.type == "error"
    assert error_resp1.error.type == models.AnthropicErrorType.INVALID_REQUEST
    assert error_resp1.error.message == "Missing parameter"
    assert error_resp1.error.provider is None
    assert error_resp1.error.provider_message is None
    assert error_resp1.error.provider_code is None

    provider_details = models.ProviderErrorMetadata(
        provider_name="google",
        raw_error={"error": {"code": 429, "message": "Quota exceeded"}},
    )
    error_resp2 = get_error_response(
        models.AnthropicErrorType.RATE_LIMIT, "Provider rate limit", provider_details
    )
    assert error_resp2.type == "error"
    assert error_resp2.error.type == models.AnthropicErrorType.RATE_LIMIT
    assert error_resp2.error.message == "Provider rate limit"
    assert error_resp2.error.provider == "google"
    assert error_resp2.error.provider_message == "Quota exceeded"
    assert error_resp2.error.provider_code == 429
