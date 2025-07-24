# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **Claude Code Provider Balancer** - a sophisticated FastAPI-based proxy service that provides intelligent load balancing and failover for multiple Claude Code providers and OpenAI-compatible services. The system ensures high availability through automated provider switching, request deduplication, and comprehensive health monitoring.

## Architecture Overview

The system follows a modern, modular architecture with clear separation of concerns:

### Request Flow
1. **Request Reception** (`src/main.py`) - FastAPI endpoints receive and validate requests
2. **OAuth Authentication** (`src/oauth/`) - Handle Claude Code Official OAuth 2.0 authentication
3. **Request Deduplication** (`src/caching/`) - Check for duplicate requests and handle caching
4. **Provider Selection** (`src/core/provider_manager.py`) - Select healthy provider based on routing rules
5. **Format Conversion** (`src/conversion/`) - Convert between Anthropic and OpenAI formats as needed
6. **Provider Communication** - Send request to selected provider with proper authentication
7. **Response Processing** (`src/core/streaming/`) - Handle streaming/non-streaming responses with parallel broadcasting
8. **Response Caching** - Cache successful responses for deduplication

### Core Modules

#### Application Layer
- **`src/main.py`** - FastAPI application entry point with lifespan management
- **`src/routers/`** - API endpoint definitions organized by domain:
  - `messages.py` - Core message processing endpoints
  - `oauth.py` - OAuth authentication endpoints
  - `health.py` - Health check endpoints
  - `management.py` - Provider management endpoints

#### Business Logic Layer
- **`src/handlers/`** - Business logic handlers:
  - `message_handler.py` - Message processing business logic
- **`src/core/`** - Core system components:
  - `provider_manager.py` - Provider health monitoring and selection
  - `streaming/parallel_broadcaster.py` - Streaming response management

#### Data Layer
- **`src/models/`** - Pydantic models for data validation:
  - `requests.py` - Request models for different API formats
  - `responses.py` - Response models and streaming data structures
  - `messages.py` - Message and conversation models
  - `content_blocks.py` - Content block definitions (text, image, tool use)
  - `tools.py` - Tool calling and function definitions
  - `errors.py` - Error response models

#### Service Layer
- **`src/conversion/`** - API format conversion services:
  - `anthropic_to_openai.py` - Anthropic → OpenAI format conversion
  - `openai_to_anthropic.py` - OpenAI → Anthropic format conversion
  - `token_counting.py` - Token counting and billing calculations
  - `error_handling.py` - Error format standardization
  - `helpers.py` - Conversion utility functions

- **`src/caching/`** - Request deduplication and caching:
  - `deduplication.py` - Content-based request deduplication

- **`src/oauth/`** - OAuth 2.0 authentication:
  - `oauth_manager.py` - OAuth token management and refresh

#### Infrastructure Layer
- **`src/utils/`** - Utility components:
  - `logging/` - Structured logging with colored console and JSON formatters
  - `validation/provider_health.py` - Provider health validation

### Configuration System

The system uses `config.yaml` for configuration with hot-reload capability:

```yaml
# Provider Configuration
providers:
  - name: "Provider Name"
    type: "anthropic" | "openai"    # Determines format conversion strategy
    base_url: "https://api.example.com"
    auth_type: "api_key" | "auth_token" | "oauth"
    auth_value: "key" | "passthrough" | "${ENV_VAR}"
    proxy: "http://proxy:port"       # Optional proxy support
    enabled: true | false

# Model Routing with Glob Patterns
model_routes:
  "*sonnet*":                       # Matches any model containing "sonnet"
    - provider: "ProviderName"
      model: "passthrough"          # Forward original model name
      priority: 1                   # Lower = higher priority
  "*haiku*":
    - provider: "ProviderName"  
      model: "anthropic/claude-3.5-haiku"  # Map to specific model
      priority: 1

# System Settings
settings:
  cooldown_seconds: 90              # Provider failure cooldown period
  timeout_seconds: 300              # Request timeout
  log_level: "INFO"                 # Logging verbosity
  max_cache_size: 1000              # Maximum cached responses
  cache_ttl_seconds: 3600           # Cache time-to-live
  enable_streaming: true            # Enable streaming responses
  max_concurrent_requests: 100      # Maximum parallel requests
  
  # OAuth Configuration
  oauth:
    enable_persistence: true        # Persist tokens to disk
    enable_auto_refresh: true       # Auto-refresh expired tokens
    token_file: "oauth_tokens.json" # Token storage file
    auto_refresh_interval: 3600     # Auto-refresh check interval (seconds)
```

### Key Design Patterns

#### Provider Abstraction
- **Unified Interface**: All providers (Anthropic, OpenAI-compatible) are handled through a common interface
- **Health Monitoring**: Continuous provider health checks with configurable cooldown periods
- **Authentication Abstraction**: Support for multiple auth types (API key, Bearer token, OAuth)

#### Request Deduplication
- **Content-based Hashing**: Generate unique signatures based on request content
- **Concurrent Request Pooling**: Multiple identical requests share the same response
- **Quality Validation**: Ensure cached responses meet minimum quality thresholds

#### Format Transparency
- **Bidirectional Conversion**: Seamless conversion between Anthropic and OpenAI API formats
- **Tool Calling Translation**: Convert function calling formats between specifications
- **Error Mapping**: Standardize error formats across different provider types

#### Streaming Architecture
- **Parallel Broadcasting**: Support for multiple concurrent streaming clients
- **Background Collection**: Optional background response collection for failover support
- **Direct Streaming**: Low-latency direct streaming mode for Anthropic providers

## Common Development Commands

### Running the Application

```bash
# Development mode (recommended - includes hot reload)
python src/main.py

# Alternative with uv
uv run src/main.py

# Production mode
uvicorn src.main:app --host 0.0.0.0 --port 9090 --workers 4
```

### Testing

```bash
# Run all tests using the custom test runner (recommended)
python tests/run_tests.py

# Run all tests using pytest
python -m pytest tests/ -v

# Run specific test files
python tests/test_streaming_requests.py
python tests/test_multi_provider_management.py
python tests/test_duplicate_request_handling.py
python tests/test_mixed_provider_responses.py
python tests/test_non_streaming_requests.py

# Run a single test function
python -m pytest tests/test_streaming_requests.py::TestStreamingRequests::test_streaming_response -v
```

### Code Quality

```bash
# Lint and format code with ruff
ruff check src/ tests/           # Check for issues
ruff format src/ tests/          # Format code

# Type checking (if configured)
mypy src/
```

### Configuration Management

```bash
# Create configuration from template
cp config.example.yaml config.yaml

# Validate configuration syntax
python -c "import yaml; yaml.safe_load(open('config.yaml'))"

# Hot reload configuration (no restart needed)
curl -X POST http://localhost:9090/providers/reload

# Check provider status
curl http://localhost:9090/providers | jq '.'

# OAuth management endpoints
curl http://localhost:9090/oauth/status
curl "http://localhost:9090/oauth/generate-url?client_id=YOUR_CLIENT_ID"
curl -X POST http://localhost:9090/oauth/exchange-code -d '{"code":"auth_code"}'
curl -X POST http://localhost:9090/oauth/refresh-token
```

### Development Testing

```bash
# Basic connectivity test
curl -X POST http://localhost:9090/v1/messages \
  -H "Content-Type: application/json" \
  -H "anthropic-version: 2023-06-01" \
  -d '{
    "model": "claude-3-5-sonnet-20241022",
    "messages": [{"role": "user", "content": "Hello"}],
    "max_tokens": 100
  }'

# Test with Claude Code client headers
curl -X POST http://localhost:9090/v1/messages \
  -H "anthropic-version: 2023-06-01" \
  -H "x-app: cli" \
  -H "user-agent: claude-cli/1.0.56 (external, cli)" \
  -H "content-type: application/json" \
  -d '{
    "model": "claude-3-5-sonnet-20241022",
    "messages": [{"role": "user", "content": "Hello"}],
    "max_tokens": 100
  }'

# Test streaming response
curl -X POST http://localhost:9090/v1/messages \
  -H "Content-Type: application/json" \
  -H "anthropic-version: 2023-06-01" \
  -d '{
    "model": "claude-3-5-sonnet-20241022",
    "messages": [{"role": "user", "content": "Count to 10"}],
    "max_tokens": 100,
    "stream": true
  }'

# Test token counting
curl -X POST http://localhost:9090/v1/messages/count_tokens \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-3-5-haiku-20241022",
    "messages": [{"role": "user", "content": "Count tokens"}]
  }'
```

## Important Implementation Details

### Provider Management (`src/core/provider_manager.py`)
- **Health Monitoring**: Tracks provider availability with configurable cooldown periods (default 90s)
- **Selection Strategies**: Priority-based (default), round-robin, and random selection
- **Authentication Handling**: Supports `api_key` (X-API-Key header), `auth_token` (Authorization Bearer), and `oauth` methods
- **Model Routing**: Pattern-based routing with support for passthrough mode (`model: "passthrough"`)
- **Hot Configuration Reload**: Automatic configuration reloading without service restart
- **Proxy Support**: HTTP proxy support for providers behind corporate firewalls

### Request Deduplication (`src/caching/deduplication.py`)
- **Signature Generation**: Creates content-based hashes for request identification using SHA-256
- **Cache Management**: In-memory caching with TTL and quality validation
- **Concurrent Handling**: Thread-safe duplicate request handling with request pooling
- **Quality Validation**: Ensures cached responses meet minimum quality thresholds
- **Memory Management**: Automatic cache cleanup and size limiting

### Format Conversion (`src/conversion/`)
- **Bidirectional Conversion**: Anthropic ↔ OpenAI format translation with full feature support
- **Token Counting**: tiktoken-based token estimation for accurate billing (`token_counting.py`)
- **Tool Handling**: Converts function calling formats between API specifications (`helpers.py`)
- **Error Mapping**: Maps error codes and formats between different provider types (`error_handling.py`)
- **Content Block Processing**: Handles text, image, and tool use content blocks

### OAuth 2.0 Authentication (`src/oauth/oauth_manager.py`)
- **Token Management**: Automatic token refresh and persistence
- **Flow Support**: Complete OAuth 2.0 authorization code flow
- **Auto-refresh**: Background token refresh with configurable intervals
- **Persistence**: Secure token storage to disk with encryption
- **Error Handling**: Comprehensive OAuth error handling and recovery

### Streaming Architecture (`src/core/streaming/parallel_broadcaster.py`)
- **Parallel Broadcasting**: Support for multiple concurrent streaming clients
- **Background Collection**: Optional background response collection for failover
- **Direct Streaming**: Low-latency direct streaming mode for Anthropic providers
- **Error Recovery**: Automatic fallback for streaming failures
- **Memory Efficient**: Streaming with minimal memory footprint

### Message Handling (`src/handlers/message_handler.py`)
- **Request Processing**: Centralized message request processing logic
- **Provider Selection**: Integration with provider manager for optimal routing
- **Response Assembly**: Consistent response formatting across provider types
- **Error Propagation**: Proper error handling and client notification

### Logging System (`src/utils/logging/`)
- **Structured Logging**: JSON format logs with rich metadata (`formatters.py`)
- **Colored Console**: Developer-friendly colored console output (`handlers.py`)
- **Request Tracing**: Unique request IDs for tracking through the system
- **Performance Metrics**: Automatic timing and performance data collection
- **Log Rotation**: Automatic log file rotation and cleanup

### Configuration Patterns

When working with `config.yaml`:

```yaml
# Advanced Provider Configuration
providers:
  - name: "Claude Code Official"
    type: "anthropic"
    base_url: "https://api.anthropic.com"
    auth_type: "oauth"                # OAuth 2.0 authentication
    auth_value: "passthrough"         # Use OAuth tokens from oauth manager
    proxy: "http://127.0.0.1:10808"   # Corporate proxy support
    enabled: true
    
  - name: "Custom Provider"
    type: "openai"
    base_url: "https://api.custom.com/v1"
    auth_type: "api_key"
    auth_value: "${CUSTOM_API_KEY}"   # Environment variable
    enabled: true

# Advanced Model Routing
model_routes:
  # Exact model matching
  "claude-3-5-sonnet-20241022":
    - provider: "Claude Code Official"
      model: "passthrough"
      priority: 1
    - provider: "Custom Provider"
      model: "anthropic/claude-3.5-sonnet"
      priority: 2
      
  # Wildcard matching with fallbacks
  "*opus*":
    - provider: "Premium Provider"
      model: "passthrough"
      priority: 1
    - provider: "Fallback Provider"
      model: "gpt-4o"  # Cross-format fallback
      priority: 2

# Advanced System Settings
settings:
  # Provider Management
  cooldown_seconds: 90              # Provider failure cooldown
  timeout_seconds: 300              # Request timeout
  max_concurrent_requests: 100      # Concurrent request limit
  
  # Caching Configuration
  max_cache_size: 1000              # Maximum cached responses
  cache_ttl_seconds: 3600           # Cache time-to-live
  enable_deduplication: true        # Enable request deduplication
  
  # Streaming Configuration
  enable_streaming: true            # Enable streaming responses
  streaming_mode: "auto"            # auto, direct, or background
  stream_buffer_size: 8192          # Streaming buffer size
  
  # Logging Configuration
  log_level: "INFO"                 # DEBUG, INFO, WARNING, ERROR
  log_format: "json"                # json or console
  log_file: "logs/logs.jsonl"       # Log file path
  
  # OAuth Configuration
  oauth:
    enable_persistence: true        # Persist tokens to disk
    enable_auto_refresh: true       # Auto-refresh expired tokens
    token_file: "oauth_tokens.json" # Token storage file
    auto_refresh_interval: 3600     # Auto-refresh check interval
    encryption_key: "${OAUTH_KEY}"  # Token encryption key
```

### Testing Strategy

The test suite focuses on integration testing with comprehensive coverage:

#### Test Files and Coverage
- **`test_streaming_requests.py`**: Tests streaming response handling, parallel broadcasting, and stream error recovery
- **`test_non_streaming_requests.py`**: Tests standard request/response cycles, format conversion, and error handling
- **`test_multi_provider_management.py`**: Tests provider health monitoring, failover logic, and configuration reloading
- **`test_duplicate_request_handling.py`**: Tests request deduplication, caching logic, and concurrent request pooling
- **`test_mixed_provider_responses.py`**: Tests mixed provider scenarios, format conversions, and cross-provider failover

#### Testing Infrastructure
- **Mock Providers**: `respx`-based HTTP mocking for reliable test scenarios
- **Async Testing**: `pytest-asyncio` for comprehensive async/await testing
- **Configuration Testing**: Dynamic configuration generation for different test scenarios
- **Performance Testing**: Response time and throughput validation
- **Error Scenario Testing**: Comprehensive error condition simulation

### Debugging and Monitoring

#### Structured Logging
```bash
# View real-time logs with formatting
tail -f logs/logs.jsonl | jq '.'

# Filter by log level
tail -f logs/logs.jsonl | jq 'select(.level == "ERROR")'

# Filter by request ID
tail -f logs/logs.jsonl | jq 'select(.request_id == "req_123")'

# View performance metrics
tail -f logs/logs.jsonl | jq 'select(.response_time) | {request_id, response_time, provider}'
```

#### Provider Health Monitoring
```bash
# Detailed provider status
curl http://localhost:9090/providers | jq '.[] | {name, healthy, last_error, cooldown_until}'

# Provider-specific health check
curl http://localhost:9090/providers | jq '.[] | select(.name == "ProviderName")'
```

#### Performance Metrics
- **Request Timing**: End-to-end request processing time
- **Provider Response Time**: Individual provider response metrics
- **Cache Hit Rate**: Request deduplication effectiveness
- **Error Rate**: Provider and system error statistics
- **Concurrent Request Tracking**: Active request monitoring

#### OAuth Token Management
```bash
# Check OAuth status
curl http://localhost:9090/oauth/status | jq '.'

# View token expiration
curl http://localhost:9090/oauth/status | jq '.tokens[] | {provider, expires_at, valid}'

# Force token refresh
curl -X POST http://localhost:9090/oauth/refresh-token
```

## Important Notes for Development

### Code Quality Standards
- **Linting**: Always run `ruff check src/ tests/` before committing
- **Formatting**: Use `ruff format src/ tests/` for consistent code style
- **Testing**: Ensure all tests pass with `python tests/run_tests.py`
- **Type Hints**: Use proper type annotations throughout the codebase
- **Documentation**: Update docstrings and comments for new functionality

### Architecture Principles
- **Separation of Concerns**: Keep routers, handlers, and core logic separate
- **Dependency Injection**: Use FastAPI's dependency injection for shared resources
- **Error Handling**: Implement comprehensive error handling at all layers
- **Async/Await**: Use asyncio patterns consistently throughout
- **Configuration Driven**: Make behavior configurable rather than hard-coded

### Error Handling Patterns
- **Provider Failures**: Always implement graceful degradation with automatic failover
- **Network Errors**: Use exponential backoff for retries where appropriate
- **Configuration Errors**: Fail fast with clear, actionable error messages
- **Validation Errors**: Return structured error responses using Pydantic models
- **OAuth Errors**: Handle authentication failures with automatic token refresh

### Performance Considerations
- **Async Operations**: Use `asyncio` and `aiohttp` for all I/O operations
- **Connection Pooling**: Reuse HTTP connections through session management
- **Memory Management**: Monitor cache growth and implement proper TTL
- **Request Deduplication**: Prevent duplicate expensive operations through content hashing
- **Streaming Optimization**: Use appropriate streaming mode for different scenarios

### Security Best Practices
- **Credential Management**: Never log or expose authentication credentials
- **Input Validation**: Validate all user inputs using Pydantic models
- **Rate Limiting**: Implement appropriate rate limiting for provider protection
- **CORS Configuration**: Configure CORS settings appropriately for deployment
- **OAuth Security**: Implement secure token storage and transmission

### Development Workflow

#### Setting up Development Environment
```bash
# Clone and setup
git clone <repository-url>
cd claude-code-provider-balancer

# Install dependencies
uv sync

# Copy configuration
cp config.example.yaml config.yaml

# Edit configuration with your provider credentials
vim config.yaml

# Run tests to verify setup
python tests/run_tests.py

# Start development server
python src/main.py
```

#### Making Changes
1. **Create Feature Branch**: `git checkout -b feature/new-feature`
2. **Write Tests First**: Add tests for new functionality
3. **Implement Feature**: Write the actual implementation
4. **Run Quality Checks**:
   ```bash
   ruff format src/ tests/
   ruff check src/ tests/
   python tests/run_tests.py
   ```
5. **Test Integration**: Test with actual providers if possible
6. **Update Documentation**: Update CLAUDE.md and docstrings
7. **Commit and Push**: Follow conventional commit format

#### Debugging Techniques
```bash
# Enable debug logging
export LOG_LEVEL=DEBUG
python src/main.py

# Monitor requests in real-time
tail -f logs/logs.jsonl | jq 'select(.level == "DEBUG")'

# Test specific provider
curl -X POST http://localhost:9090/v1/messages \
  -H "Content-Type: application/json" \
  -H "x-debug-provider: ProviderName" \
  -d '{"model":"claude-3-5-sonnet-20241022","messages":[{"role":"user","content":"test"}],"max_tokens":10}'

# Check provider health
curl http://localhost:9090/providers | jq '.[] | select(.name == "ProviderName")'
```

### Deployment Considerations

#### Production Configuration
```yaml
settings:
  log_level: "WARNING"              # Reduce log verbosity
  max_concurrent_requests: 200      # Increase for production load
  timeout_seconds: 120              # Reduce timeout for faster failover
  cache_ttl_seconds: 7200           # Longer cache TTL for efficiency
  
  oauth:
    enable_persistence: true        # Essential for production
    auto_refresh_interval: 1800     # More frequent refresh checks
    encryption_key: "${OAUTH_ENCRYPTION_KEY}"  # Use environment variable
```

#### Container Deployment
```dockerfile
# Example Dockerfile structure
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY src/ ./src/
COPY config.yaml .
EXPOSE 9090
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "9090"]
```

#### Health Checks
```bash
# Docker health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:9090/health || exit 1

# Kubernetes readiness probe
readinessProbe:
  httpGet:
    path: /health
    port: 9090
  initialDelaySeconds: 10
  periodSeconds: 5
```

### Troubleshooting Common Issues

#### Configuration Issues
```bash
# Validate YAML syntax
python -c "import yaml; yaml.safe_load(open('config.yaml'))"

# Check environment variables
env | grep -E '(API_KEY|TOKEN|OAUTH)'

# Test provider connectivity
curl -v https://provider-url/health
```

#### Performance Issues
```bash
# Monitor response times
tail -f logs/logs.jsonl | jq 'select(.response_time > 5000)'

# Check cache hit rates
grep "cache_hit" logs/logs.jsonl | tail -100 | jq '.cache_hit' | sort | uniq -c

# Monitor concurrent requests
curl http://localhost:9090/health | jq '.active_requests'
```

#### Memory and Resource Issues
```bash
# Monitor memory usage
ps aux | grep python

# Check cache size
curl http://localhost:9090/health | jq '.cache_stats'

# Monitor file descriptors
lsof -p $(pgrep -f "python src/main.py") | wc -l
```

This comprehensive documentation should help developers understand and work with the Claude Code Provider Balancer effectively. The modular architecture, extensive testing, and monitoring capabilities make it a robust solution for managing multiple Claude Code providers with high availability and performance.