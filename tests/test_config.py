"""Test configuration utilities for Claude Code Provider Balancer tests."""

import os
from typing import Dict, Any

# Test server configuration - mock provider runs on separate port
TEST_SERVER_HOST = "localhost"
TEST_SERVER_PORT = 8998  # Port for test mock provider server
TEST_BASE_URL = f"http://{TEST_SERVER_HOST}:{TEST_SERVER_PORT}"

# Test provider endpoints
TEST_PROVIDERS = {
    "anthropic": f"{TEST_BASE_URL}/test-providers/anthropic/v1/messages",
    "anthropic_sse_error": f"{TEST_BASE_URL}/test-providers/anthropic-sse-error/v1/messages", 
    "openai": f"{TEST_BASE_URL}/test-providers/openai/v1/chat/completions",
    # Unhealthy counting test providers
    "anthropic_unhealthy_single": f"{TEST_BASE_URL}/test-providers/anthropic-unhealthy-test-single/v1/messages",
    "anthropic_unhealthy_multiple": f"{TEST_BASE_URL}/test-providers/anthropic-unhealthy-test-multiple/v1/messages",
    "anthropic_unhealthy_reset": f"{TEST_BASE_URL}/test-providers/anthropic-unhealthy-test-reset/v1/messages",
    "anthropic_unhealthy_always_fail": f"{TEST_BASE_URL}/test-providers/anthropic-unhealthy-test-always-fail/v1/messages",
}

def get_test_provider_url(provider_type: str, endpoint: str = "v1/messages") -> str:
    """Get test provider URL for given provider type and endpoint."""
    if provider_type == "anthropic":
        if endpoint == "v1/messages":
            return TEST_PROVIDERS["anthropic"]
    elif provider_type == "anthropic-sse-error":
        if endpoint == "v1/messages":
            return TEST_PROVIDERS["anthropic_sse_error"]
    elif provider_type == "openai":
        if endpoint == "v1/chat/completions":
            return TEST_PROVIDERS["openai"]
    
    # Fallback to generic pattern
    return f"{TEST_BASE_URL}/test-providers/{provider_type}/{endpoint}"

def get_test_server_config() -> Dict[str, Any]:
    """Get test server configuration."""
    return {
        "host": TEST_SERVER_HOST,
        "port": TEST_SERVER_PORT, 
        "base_url": TEST_BASE_URL
    }