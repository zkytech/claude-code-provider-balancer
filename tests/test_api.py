"""
Tests for the FastAPI endpoints and helper functions within src/claude_proxy/api.py.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from claude_proxy.api import app, get_error_response, extract_provider_error_details, extract_error_message
from claude_proxy import models, logger

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

def test_count_tokens_endpoint(client, mocker):
    """Tests the /v1/messages/count_tokens endpoint returns zero."""
    mock_log_info = mocker.patch("claude_proxy.logger.info")
    request_data = {
        "model": "claude-3-opus-20240229",
        "messages": [{"role": "user", "content": "Count these tokens"}],
    }

    response = client.post("/v1/messages/count_tokens", json=request_data)

    assert response.status_code == 200
    data = response.json()
    assert data == {"input_tokens": 0}

    log_found = False
    for call in mock_log_info.call_args_list:
        args, _ = call
        if args and isinstance(args[0], logger.LogRecord):
             if "Token counting disabled" in args[0].message:
                log_found = True
                break
    assert log_found, "Expected log message not found"

def test_create_message_with_metadata_user_id(client, mock_openai_client_create, mock_completion):
    """Tests that metadata.user_id is mapped to the OpenAI 'user' parameter."""
    mock_openai_response = AsyncMock()
    mock_openai_response.model_dump.return_value = {
         "id": "chatcmpl-mock123",
         "choices": [{
             "message": {"role": "assistant", "content": "Mock response"},
             "finish_reason": "stop"
         }],
         "usage": {"prompt_tokens": 10, "completion_tokens": 5},
         "model": "test_big_model",
         "error": None
    }
    mock_openai_client_create.return_value = mock_openai_response

    request_data = {
        "model": "claude-3-opus-20240229",
        "messages": [{"role": "user", "content": "Hello"}],
        "max_tokens": 10,
        "metadata": {"user_id": "test-user-123"},
    }

    response = client.post("/v1/messages", json=request_data)

    assert response.status_code == 200
    mock_openai_client_create.assert_called_once()
    call_args, call_kwargs = mock_openai_client_create.call_args
    assert call_kwargs.get("user") == "test-user-123"

def test_create_message_with_top_k_warning(client, mock_openai_client_create, mock_completion, mocker):
    """Tests that providing top_k logs an unsupported parameter warning."""
    mock_log_warning = mocker.patch("claude_proxy.logger.warning")

    mock_openai_response = AsyncMock()
    mock_openai_response.model_dump.return_value = {
         "id": "chatcmpl-mock123",
         "choices": [{
             "message": {"role": "assistant", "content": "Mock response"},
             "finish_reason": "stop"
         }],
         "usage": {"prompt_tokens": 10, "completion_tokens": 5},
         "model": "test_big_model",
         "error": None
    }
    mock_openai_client_create.return_value = mock_openai_response

    request_data = {
        "model": "claude-3-opus-20240229",
        "messages": [{"role": "user", "content": "Hello"}],
        "max_tokens": 10,
        "top_k": 50,
    }

    response = client.post("/v1/messages", json=request_data)

    assert response.status_code == 200

    warning_found = False
    for call in mock_log_warning.call_args_list:
        args, _ = call
        if args and isinstance(args[0], logger.LogRecord):
            if args[0].event == logger.LogEvent.PARAMETER_UNSUPPORTED.value and "top_k" in args[0].message:
                warning_found = True
                break
    assert warning_found, "Expected top_k warning log not found"

    mock_openai_client_create.assert_called_once()
    call_args, call_kwargs = mock_openai_client_create.call_args
    assert "top_k" not in call_kwargs

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

def test_extract_error_message_types(mocker):
    """Tests extract_error_message with various exception types."""
    from pydantic import ValidationError
    from fastapi import HTTPException
    import openai

    exc1 = Exception("Generic error")
    assert extract_error_message(exc1) == "Generic error"

    exc2 = HTTPException(status_code=404, detail="Not found here")
    assert extract_error_message(exc2) == "Not found here"

    mock_errors = [{"loc": ("field",), "msg": "Value error", "type": "value_error"}]
    exc3 = ValidationError.from_exception_data(title="Model", line_errors=mock_errors)
    assert "Value error" in extract_error_message(exc3)
    assert "field" in extract_error_message(exc3)

    mock_request = mocker.MagicMock()
    exc4 = openai.APIError("API Error Message", request=mock_request, body=None)
    assert extract_error_message(exc4) == "API Error Message"

    exc5_body = {"message": "Simple body message"}
    exc5 = openai.APIError("API Error", request=mock_request, body=exc5_body)
    assert extract_error_message(exc5) == "Simple body message"

    exc6_body = {"error": {"message": "Detailed error message"}}
    exc6 = openai.APIError("API Error", request=mock_request, body=exc6_body)
    assert extract_error_message(exc6) == "Detailed error message"

    exc7_body = {
        "error": {
            "message": "Provider error wrapper",
            "metadata": {
                "provider_name": "google",
                "raw": json.dumps({"error": {"message": "Actual provider message"}}),
            },
        }
    }
    exc7 = openai.BadRequestError("API Error", request=mock_request, body=exc7_body)
    assert "Provider error wrapper: Actual provider message" in extract_error_message(exc7)
