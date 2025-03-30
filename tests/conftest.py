"""
Pytest configuration file containing shared fixtures.
Only contains fixtures that are truly shared between multiple test modules.
"""

import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

from claude_proxy.config import Settings


@pytest.fixture(autouse=True)
def mock_settings():
    """Override settings for all tests."""
    test_config = Settings(
        openrouter_api_key="test_api_key",
        big_model_name="test_big_model",
        small_model_name="test_small_model",
        openrouter_base_url="https://test.openrouter.ai/api/v1",
        app_name="TestClaudeProxy",
        log_level="DEBUG"
    )
    
    with patch("claude_proxy.api.settings", test_config):
        with patch("claude_proxy.openrouter_client.settings", test_config):
            yield test_config
