"""
Unit tests for the model selection logic in api.py
"""


import pytest

from claude_proxy.api import select_target_model


@pytest.mark.parametrize(
    "client_model,expected_target",
    [
        ("claude-3-opus-20240229", "test_big_model"),
        ("claude-3-sonnet-20240229", "test_big_model"),
        ("claude-3-haiku-20240307", "test_small_model"),
        ("unknown-model", "test_small_model"),
    ],
)
def test_select_target_model(client_model, expected_target):
    """Tests that model selection maps client models to the correct target."""
    result = select_target_model(client_model, "test-request-id")

    assert result == expected_target
