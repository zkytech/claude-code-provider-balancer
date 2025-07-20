# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **Claude Code Provider Balancer** - a FastAPI-based proxy service that provides intelligent load balancing and failover for multiple Claude Code providers and OpenAI-compatible services. The system ensures high availability by automatically switching between providers when failures occur.

## Architecture Overview

The system follows a modular, layered architecture with clear separation of concerns:

### Request Flow
1. **Request Reception** (`src/main.py`) - FastAPI endpoints receive and validate requests
2. **Request Deduplication** (`src/caching/`) - Check for duplicate requests and handle caching
3. **Provider Selection** (`src/provider_manager.py`) - Select healthy provider based on routing rules
4. **Format Conversion** (`src/conversion/`) - Convert between Anthropic and OpenAI formats as needed
5. **Provider Communication** - Send request to selected provider with proper authentication
6. **Response Processing** - Handle streaming/non-streaming responses and error cases
7. **Response Caching** - Cache successful responses for deduplication

### Core Modules

- **`src/main.py`** - FastAPI application entry point with endpoint handlers
- **`src/provider_manager.py`** - Provider health monitoring, selection logic, and configuration management
- **`src/models/`** - Pydantic models for request/response validation (content blocks, messages, tools, errors)
- **`src/conversion/`** - Bidirectional format conversion between Anthropic and OpenAI APIs
- **`src/caching/`** - Request deduplication and response caching system
- **`src/log_utils/`** - Structured logging with colored console output and JSON formatting

### Configuration System

The system uses `providers.yaml` for provider configuration with hot-reload capability:
- **Provider definitions** with auth types (`api_key`, `auth_token`) and endpoints
- **Model routing rules** with priority-based selection and passthrough support
- **System settings** for timeouts, cooldowns, and logging levels

### Key Design Patterns

- **Provider abstraction** - Unified interface for different provider types (Anthropic, OpenAI)
- **Request deduplication** - Content-based hashing to prevent duplicate processing
- **Graceful degradation** - Automatic failover with configurable cooldown periods
- **Format transparency** - Seamless conversion between API formats
- **Streaming support** - Both direct streaming and background collection modes

## Common Development Commands

### Running the Application

```bash
# Development mode (recommended)
python src/main.py

# Using uv (modern Python package manager)
uv run src/main.py

# Production mode
uvicorn src.main:app --host 0.0.0.0 --port 8080
```

### Testing

```bash
# Run all tests using pytest
python -m pytest tests/

# Run all tests using the custom test runner
python tests/run_all_tests.py

# Run specific test categories
python tests/test_provider_routing.py      # Provider selection logic
python tests/test_stream_nonstream.py      # Streaming functionality  
python tests/test_caching_deduplication.py # Request deduplication
python tests/test_error_handling.py        # Error handling
python tests/test_passthrough.py           # Passthrough model routing
python tests/test_log_colors.py           # Logging and colors

# Run a single test function
python -m pytest tests/test_provider_routing.py::TestProviderRouting::test_basic_routing -v
```

### Code Quality

```bash
# Lint code with ruff
ruff check src/ tests/

# Format code with ruff
ruff format src/ tests/

# Type checking with mypy (if configured)
mypy src/
```

### Configuration Management

```bash
# Create config from template
cp providers.example.yaml providers.yaml

# Test configuration validity
python -c "import yaml; yaml.safe_load(open('providers.yaml'))"

# Hot reload configuration (server must be running)
curl -X POST http://localhost:8080/providers/reload

# Check provider status
curl http://localhost:8080/providers
```

### Development Testing

```bash
# Basic connectivity test
curl -X POST http://localhost:8080/v1/messages \
  -H "Content-Type: application/json" \
  -d '{"model":"claude-3-5-sonnet-20241022","messages":[{"role":"user","content":"Hello"}],"max_tokens":100}'

# Test with Claude Code client headers for realistic simulation
curl -X POST http://localhost:8080/v1/messages \
  -H "anthropic-version: 2023-06-01" \
  -H "x-app: cli" \
  -H "user-agent: claude-cli/1.0.56 (external, cli)" \
  -H "content-type: application/json" \
  -d '{"model":"claude-3-5-sonnet-20241022","messages":[{"role":"user","content":"Hello"}],"max_tokens":100}'

# Test token counting endpoint
curl -X POST http://localhost:8080/v1/messages/count_tokens \
  -H "Content-Type: application/json" \
  -d '{"model":"claude-3-5-haiku-20241022","messages":[{"role":"user","content":"Count tokens"}]}'
```

## Important Implementation Details

### Provider Management (`src/provider_manager.py`)
- **Health Monitoring**: Tracks provider availability with configurable cooldown periods (default 90s)
- **Selection Strategies**: Priority-based (default), round-robin, and random selection
- **Authentication Handling**: Supports both `api_key` (X-API-Key header) and `auth_token` (Authorization Bearer) methods
- **Model Routing**: Pattern-based routing with support for passthrough mode (`model: "passthrough"`)

### Request Deduplication (`src/caching/`)
- **Signature Generation**: Creates content-based hashes for request identification
- **Cache Management**: In-memory caching with TTL and quality validation
- **Concurrent Handling**: Thread-safe duplicate request handling with request pooling
- **Quality Validation**: Ensures cached responses meet minimum quality thresholds

### Format Conversion (`src/conversion/`)
- **Bidirectional Conversion**: Anthropic ↔ OpenAI format translation
- **Token Counting**: tiktoken-based token estimation for billing
- **Tool Handling**: Converts function calling formats between API specifications
- **Error Mapping**: Maps error codes and formats between different provider types

### Configuration Patterns

When working with `providers.yaml`:
```yaml
# Provider configuration supports inheritance and environment variables
providers:
  - name: "Provider Name"
    type: "anthropic" | "openai"    # Determines format conversion
    base_url: "https://api.example.com"
    auth_type: "api_key" | "auth_token"
    auth_value: "key" | "passthrough" | "${ENV_VAR}"
    proxy: "http://proxy:port"       # Optional proxy support
    enabled: true | false

# Model routing uses glob patterns
model_routes:
  "*sonnet*":                       # Matches any model containing "sonnet"
    - provider: "ProviderName"
      model: "passthrough"          # Forward original model name
      priority: 1                   # Lower = higher priority
  "*haiku*":
    - provider: "ProviderName"  
      model: "anthropic/claude-3.5-haiku"  # Map to specific model
      priority: 1
```

### Testing Strategy

The test suite focuses on integration testing with mock providers:
- **`test_provider_routing.py`**: Tests provider selection logic and failover
- **`test_stream_nonstream.py`**: Validates streaming/non-streaming response handling
- **`test_caching_deduplication.py`**: Tests request deduplication and caching
- **`test_error_handling.py`**: Validates error propagation and formatting
- **`test_passthrough.py`**: Tests model name passthrough functionality

Tests use `respx` for HTTP mocking and `pytest-asyncio` for async test support.

### Debugging and Monitoring

- **Structured Logging**: JSON logs in `logs/logs.jsonl` with colored console output
- **Request Tracing**: Each request gets a unique ID for tracking through the system
- **Provider Health**: Real-time provider status available via `/providers` endpoint
- **Performance Metrics**: Request timing and success rates logged per provider