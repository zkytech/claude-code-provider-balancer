# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **Claude Code Provider Balancer** - a FastAPI-based proxy service that provides intelligent load balancing and failover for multiple Claude Code providers and OpenAI-compatible services. The system ensures high availability by automatically switching between providers when failures occur.

## Key Features

- **Multi-Provider Support**: Supports Anthropic API-compatible, OpenAI-compatible, and Zed providers
- **Intelligent Load Balancing**: Priority-based, round-robin, and random selection strategies
- **Automatic Failover**: Seamless switching to healthy providers when failures occur
- **Health Monitoring**: Tracks provider status with configurable cooldown periods
- **Dual Authentication**: Supports both `api_key` and `auth_token` authentication methods
- **Dynamic Model Routing**: Maps Claude models to provider-specific models with passthrough support
- **Hot Configuration Reload**: Reload provider configuration without restart
- **Comprehensive Logging**: Detailed request/response tracking with colored output
- **Token Counting**: Built-in token estimation functionality
- **Streaming Support**: Full support for streaming responses with proper error handling
- **Request Deduplication**: Prevents duplicate requests with intelligent caching
- **Zed Integration**: Advanced thread management with context-aware rotation and mode selection

## Architecture

### Core Components

1. **`src/main.py`** - Main FastAPI application with request handling logic
2. **`src/provider_manager.py`** - Provider management and routing logic
3. **`providers.yaml`** - Configuration file for providers and model routes
4. **`tests/`** - Test suite for API functionality

### Key Technologies

- **FastAPI** - Web framework for API endpoints
- **Pydantic** - Data validation and serialization
- **httpx** - HTTP client for provider requests
- **OpenAI SDK** - For OpenAI-compatible provider interactions
- **PyYAML** - Configuration file parsing
- **Rich** - Terminal output formatting
- **Uvicorn** - ASGI server
- **uv** - Modern Python package manager

## Common Development Commands

### Running the Application

```bash
# Development mode (recommended)
python src/main.py

# From src directory
cd src && python main.py

# Production mode
uvicorn src.main:app --host 0.0.0.0 --port 8080
```

### Running the Project

- **Using uv**: `uv run src/main.py`

### Testing and Validation

```bash
# Run all tests
python -m pytest tests/

# Run specific test files
python tests/test_api.py
python tests/test_passthrough.py
python tests/test_log_colors.py

# Test provider connectivity (basic)
curl -X POST http://localhost:8080/v1/messages \
  -H "Content-Type: application/json" \
  -d '{"model":"claude-3-5-sonnet-20241022","messages":[{"role":"user","content":"Hello"}],"max_tokens":100}'

# Test with Claude Code client headers (recommended for realistic testing)
# See tests/test_headers.txt for complete header set
curl -X POST http://localhost:8080/v1/messages \
  -H "x-stainless-retry-count: 0" \
  -H "x-stainless-timeout: 60" \
  -H "x-stainless-lang: js" \
  -H "x-stainless-package-version: 0.55.1" \
  -H "anthropic-version: 2023-06-01" \
  -H "x-app: cli" \
  -H "user-agent: claude-cli/1.0.56 (external, cli)" \
  -H "content-type: application/json" \
  -H "anthropic-beta: oauth-2025-04-20,fine-grained-tool-streaming-2025-05-14" \
  -d '{"model":"claude-3-5-sonnet-20241022","messages":[{"role":"user","content":"Hello"}],"max_tokens":100}'

# Check provider status
curl http://localhost:8080/providers

# Reload configuration
curl -X POST http://localhost:8080/providers/reload
```

[... rest of the file remains unchanged ...]