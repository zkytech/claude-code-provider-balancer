"""Common utilities for test files."""

def get_claude_code_headers():
    """Get Claude Code client headers for realistic testing."""
    return {
        "x-stainless-retry-count": "0",
        "x-stainless-timeout": "60", 
        "x-stainless-lang": "js",
        "x-stainless-package-version": "0.55.1",
        "x-stainless-os": "MacOS",
        "x-stainless-arch": "arm64",
        "x-stainless-runtime": "node",
        "x-stainless-runtime-version": "v24.1.0",
        "anthropic-dangerous-direct-browser-access": "true",
        "anthropic-version": "2023-06-01",
        "x-app": "cli",
        "user-agent": "claude-cli/1.0.56 (external, cli)",
        "content-type": "application/json",
        "anthropic-beta": "oauth-2025-04-20,fine-grained-tool-streaming-2025-05-14",
        "x-stainless-helper-method": "stream",
        "accept-language": "*",
        "sec-fetch-mode": "cors",
        "accept-encoding": "gzip, deflate",
        # Add your actual API key here for testing
        "authorization": "Bearer TEST_AUTH_TOKEN"
    }