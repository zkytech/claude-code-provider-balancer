"""
Pytest configuration file containing shared fixtures.
Only contains fixtures that are truly shared between multiple test modules.
"""

import logging
from unittest.mock import patch

import pytest

from claude_proxy import logger as app_logger
from claude_proxy.config import Settings


@pytest.fixture(autouse=True)
def disable_app_logging():
    """
    Auto-use fixture to disable application logs during test runs
    by setting the log level extremely high.
    """
    log_instance = app_logger._logger
    original_level = log_instance.level

    log_instance.setLevel(logging.CRITICAL + 1)

    yield  

    log_instance.setLevel(original_level)


@pytest.fixture(autouse=True)
def mock_settings():
    """Override settings for all tests."""
    test_config = Settings(
        openrouter_api_key="test_api_key",
        big_model_name="test_big_model",
        small_model_name="test_small_model",
        openrouter_base_url="https://test.openrouter.ai/api/v1",
        app_name="TestClaudeProxy",
        log_level="DEBUG",
    )

    with patch("claude_proxy.api.settings", test_config):
        with patch("claude_proxy.openrouter_client.settings", test_config):
            yield test_config
