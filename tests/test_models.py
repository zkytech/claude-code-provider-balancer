"""
Tests for Pydantic models and their validation logic.
"""


from claude_proxy import models


def test_messages_request_top_k_warning():
    """Tests that MessagesRequest logs a warning when top_k is provided."""
    data = {
        "model": "claude-3-opus-20240229",
        "max_tokens": 100,
        "messages": [{"role": "user", "content": "Hello"}],
        "top_k": 10,
    }
    request = models.MessagesRequest(**data)

    assert request.top_k == 10
