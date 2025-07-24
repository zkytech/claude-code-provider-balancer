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
def test_config() -> Dict[str, Any]:
    """Test configuration with test providers enabled."""
    return {
        "settings": {
            "log_level": "DEBUG",
            "timeout_seconds": 30,
            "cooldown_seconds": 10,
            "test_providers": {
                "enabled": True,
                "default_delay_ms": 50,
                "error_delay_ms": 25,
                "streaming_chunks": 3,
                "chunk_delay_ms": 100,
                "random_error_rate": 0.3,
                "success_response_text": "Test response from mock provider",
                "streaming_response_text": "Streaming test response from mock provider"
            }
        },
        "providers": [
            {
                "name": "test_anthropic_success",
                "type": "anthropic",
                "base_url": "http://localhost:9090/test-providers/anthropic/success",
                "auth_type": "api_key",  
                "auth_value": "test-key",
                "enabled": True
            },
            {
                "name": "test_anthropic_error", 
                "type": "anthropic",
                "base_url": "http://localhost:9090/test-providers/anthropic/error/server_error",
                "auth_type": "api_key",
                "auth_value": "test-key",
                "enabled": True
            },
            {
                "name": "test_openai_success",
                "type": "openai",
                "base_url": "http://localhost:9090/test-providers/openai/success", 
                "auth_type": "api_key",
                "auth_value": "test-key",
                "enabled": True
            }
        ],
        "model_routes": {
            "*test*": [
                {
                    "provider": "test_anthropic_success",
                    "model": "passthrough",
                    "priority": 1
                }
            ],
            "*claude*": [
                {
                    "provider": "test_anthropic_success", 
                    "model": "passthrough",
                    "priority": 1
                },
                {
                    "provider": "test_anthropic_error",
                    "model": "passthrough", 
                    "priority": 2
                }
            ],
            "*gpt*": [
                {
                    "provider": "test_openai_success",
                    "model": "passthrough",
                    "priority": 1
                }
            ]
        }
    }


@pytest.fixture
def test_config_file(test_config: Dict[str, Any]) -> str:
    """Create a temporary config file for testing."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(test_config, f)
        return f.name


@pytest.fixture
def mock_provider_manager(test_config: Dict[str, Any]) -> ProviderManager:
    """Create a mock provider manager for testing."""
    # We'll just use respx to mock HTTP requests instead of modifying the actual provider manager
    manager = ProviderManager()
    return manager


@pytest.fixture(autouse=True) 
def setup_test_environment(monkeypatch):
    """Set up test environment for testing."""
    # We'll use respx to mock all HTTP requests, so we don't need to modify the actual provider manager
    pass


@pytest.fixture
def test_client() -> TestClient:
    """Create a test client for the FastAPI app."""
    return TestClient(app)


@pytest_asyncio.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Create an async test client for the FastAPI app."""
    from httpx import ASGITransport
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


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
def cleanup_after_test():
    """Cleanup after each test."""
    yield
    # Add any cleanup logic here if needed