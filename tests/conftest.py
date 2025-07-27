"""Pytest configuration and fixtures for Claude Provider Balancer tests."""

import asyncio
import json
import os
import sys
import tempfile
import yaml
from pathlib import Path
from typing import Dict, Any, AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import AsyncClient

# Add src to Python path
current_dir = Path(__file__).parent
src_dir = current_dir.parent / "src"
sys.path.insert(0, str(src_dir))

from main import app
from core.provider_manager import ProviderManager
from test_utils import get_claude_code_headers


@pytest.fixture
def mock_provider_manager() -> ProviderManager:
    """Create a mock provider manager for testing."""
    # We'll just use respx to mock HTTP requests instead of modifying the actual provider manager
    manager = ProviderManager()
    return manager


@pytest.fixture(autouse=True) 
def setup_test_environment():
    """Set up test environment."""
    # Now that async_client creates its own test app, we don't need complex patching
    pass


@pytest.fixture
def test_client() -> TestClient:
    """Create a test client for the FastAPI app."""
    return TestClient(app)


@pytest_asyncio.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Create an async test client with test configuration."""
    from httpx import ASGITransport
    import os
    from pathlib import Path
    
    # Get the test directory (where config-test.yaml is now located)
    current_dir = Path(__file__).parent
    test_config_path = current_dir / "config-test.yaml"
    
    # Create test provider manager
    from core.provider_manager import ProviderManager
    test_provider_manager = ProviderManager(config_path=str(test_config_path))
    
    # Store provider manager globally for access by other fixtures
    global _test_provider_manager
    _test_provider_manager = test_provider_manager
    
    # Create test app with test provider manager
    from main import Settings
    import fastapi
    
    # Create test settings (we can reuse the existing settings for now)
    test_settings = Settings()
    test_settings.load_from_provider_config()
    
    # Create test FastAPI app
    test_app = fastapi.FastAPI(
        title="Test " + test_settings.app_name,
        version=test_settings.app_version,
        description="Test application with mock providers",
    )
    
    # Register routers with test provider manager
    from routers.messages import create_messages_router
    from routers.oauth import create_oauth_router
    from routers.health import create_health_router
    from routers.management import create_management_router
    from routers.mock_provider import create_mock_provider_router
    
    test_app.include_router(create_messages_router(test_provider_manager, test_settings))
    test_app.include_router(create_oauth_router(test_provider_manager))
    test_app.include_router(create_health_router(test_provider_manager, test_settings.app_name, test_settings.app_version))
    test_app.include_router(create_management_router())
    test_app.include_router(create_mock_provider_router())  # Add mock provider for testing
    
    # Set up test deduplication
    from caching.deduplication import set_provider_manager
    set_provider_manager(test_provider_manager)
    
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        yield client


# Global variable to store test provider manager
_test_provider_manager = None


@pytest.fixture
def provider_manager():
    """Get access to the test provider manager."""
    return _test_provider_manager


@pytest.fixture
def claude_headers() -> Dict[str, str]:
    """Get Claude Code client headers for realistic testing."""
    return get_claude_code_headers()


@pytest.fixture
def test_messages_request() -> Dict[str, Any]:
    """Standard test messages request."""
    return {
        "model": "claude-3-5-sonnet-20241022",
        "max_tokens": 100,
        "messages": [
            {
                "role": "user",
                "content": "Hello, this is a test message."
            }
        ]
    }


@pytest.fixture
def test_streaming_request() -> Dict[str, Any]:
    """Standard test streaming messages request."""
    return {
        "model": "claude-3-5-sonnet-20241022", 
        "max_tokens": 100,
        "stream": True,
        "messages": [
            {
                "role": "user",
                "content": "Hello, this is a streaming test message."
            }
        ]
    }


@pytest.fixture
def test_openai_request() -> Dict[str, Any]:
    """Standard test OpenAI request."""
    return {
        "model": "gpt-3.5-turbo",
        "max_tokens": 100,
        "messages": [
            {
                "role": "user", 
                "content": "Hello, this is an OpenAI test message."
            }
        ]
    }


@pytest.fixture(autouse=True)
def cleanup_after_test(provider_manager):
    """Cleanup after each test."""
    yield
    # Reset provider health states to prevent test interference
    try:
        from core.provider_manager.health import reset_all_health_states
        reset_all_health_states()
    except ImportError:
        pass  # Skip if module not available
    
    # Reset provider manager states
    if provider_manager:
        try:
            provider_manager.reset_all_provider_states()
        except AttributeError:
            pass  # Skip if method not available
    
    # Also clear any cached deduplication data
    try:
        from caching.deduplication import clear_all_cache
        clear_all_cache()
    except (ImportError, AttributeError):
        pass  # Skip if method not available