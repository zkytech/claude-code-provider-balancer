"""
Tests for Pydantic models and their validation logic.
"""

from unittest.mock import patch
import pytest

from claude_proxy import models, logger

def test_messages_request_top_k_warning(mocker):
    """Tests that MessagesRequest logs a warning when top_k is provided."""
    mock_log_warning = mocker.patch("claude_proxy.logger.warning")

    data = {
        "model": "claude-3-opus-20240229",
        "max_tokens": 100,
        "messages": [{"role": "user", "content": "Hello"}],
        "top_k": 10,
    }
    request = models.MessagesRequest(**data)

    assert request.top_k == 10

    warning_found = False
    for call in mock_log_warning.call_args_list:
        args, _ = call
        if args and isinstance(args[0], logger.LogRecord):
             if args[0].event == logger.LogEvent.PARAMETER_UNSUPPORTED.value and "top_k" in args[0].message:
                warning_found = True
                break
    assert warning_found, "Expected top_k warning log not found"
