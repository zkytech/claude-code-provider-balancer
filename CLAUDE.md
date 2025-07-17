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

### Testing and Validation

```bash
# Run all tests
python -m pytest tests/

# Run specific test files
python tests/test_api.py
python tests/test_passthrough.py
python tests/test_log_colors.py

# Test provider connectivity
curl -X POST http://localhost:8080/v1/messages \
  -H "Content-Type: application/json" \
  -d '{"model":"claude-3-5-sonnet-20241022","messages":[{"role":"user","content":"Hello"}],"max_tokens":100}'

# Check provider status
curl http://localhost:8080/providers

# Reload configuration
curl -X POST http://localhost:8080/providers/reload
```

### Code Quality

```bash
# Type checking
mypy src/

# Code formatting
ruff format src/

# Linting
ruff check src/
```

### Dependencies

```bash
# Install dependencies
uv sync

# Install development dependencies
uv sync --group dev

# Add new dependency
uv add package_name

# Add development dependency
uv add --group dev package_name
```

## Configuration

### Provider Configuration (`providers.yaml`)

```yaml
providers:
  - name: "provider_name"
    type: "anthropic"  # or "openai" or "zed"
    base_url: "https://api.example.com"
    auth_type: "api_key"  # or "auth_token"
    auth_value: "your-api-key"
    enabled: true
    proxy: "http://proxy:8080"  # optional
    zed_config:  # Zed-specific configuration
      default_mode: "normal"  # normal | burn
      max_context_tokens: 120000
      thread_ttl: 3600

model_routes:
  "claude-3-5-sonnet-20241022":
    - provider: "provider_name"
      model: "claude-3-5-sonnet-20241022"
      priority: 1
  
  "*sonnet*":  # wildcard matching
    - provider: "provider_name"
      model: "passthrough"  # use original model name
      priority: 1

settings:
  selection_strategy: "priority"  # priority | round_robin | random
  failure_cooldown: 60  # seconds
  request_timeout: 30   # seconds
  log_level: "INFO"
  log_color: true
  host: "127.0.0.1"
  port: 8080
```

### Configuration Setup

```bash
# Copy example configuration
cp providers.example.yaml providers.yaml

# Edit configuration with your provider details
vim providers.yaml
```

## API Endpoints

### Core Endpoints

- `POST /v1/messages` - Main Claude API endpoint with load balancing
- `POST /v1/messages/count_tokens` - Token counting utility
- `GET /` - Health check
- `GET /providers` - Provider status information
- `POST /providers/reload` - Hot reload configuration

### Usage with Claude Code

```bash
# Set environment variable
export ANTHROPIC_BASE_URL=http://localhost:8080

# Use Claude Code normally
claude
```

## Key Implementation Details

### Provider Selection Logic

1. **Exact Model Matching**: Direct model name matches take precedence
2. **Wildcard Matching**: Supports patterns like `*sonnet*`, `*haiku*`
3. **Selection Strategies**:
   - **Priority**: Always use highest priority healthy provider
   - **Round Robin**: Cycle through providers in priority order
   - **Random**: Random selection from top-priority providers

### Failover and Recovery

- **Failure Detection**: HTTP errors, timeouts, and connection issues
- **Cooldown Period**: Failed providers are excluded for configurable time
- **Automatic Recovery**: Providers automatically rejoin after cooldown
- **Sticky Sessions**: Recent successful providers are preferred during active periods

### Streaming Response Handling

The system has comprehensive streaming support with proper error detection:

- **Error Event Detection**: Detects `event: error` in SSE streams (e.g., `overloaded_error`)
- **Success Callbacks**: Providers marked successful only after complete streaming
- **Timeout Handling**: Configurable timeouts for streaming requests
- **Request Lifecycle Tracking**: Complete monitoring from request start to completion

### Request Processing

1. **Request Validation**: Pydantic models ensure data integrity
2. **Provider Selection**: Choose optimal provider based on model and health
3. **Format Conversion**: Convert between Anthropic, OpenAI, and Zed formats as needed
4. **Response Handling**: Stream or return complete responses
5. **Error Handling**: Graceful fallback to alternative providers

### Logging and Monitoring

- **Structured Logging**: JSON-formatted logs with request IDs
- **Colored Console Output**: Enhanced development experience
- **Request Tracking**: Complete request lifecycle monitoring
- **Performance Metrics**: Response times, token counts, and provider statistics

## Common Development Patterns

### Adding New Providers

1. Add provider configuration to `providers.yaml`
2. Configure model routes for the new provider
3. Test connectivity with `/providers` endpoint
4. Verify with actual requests

### Debugging Issues

1. **Check Provider Health**: `GET /providers`
2. **Review Logs**: Monitor console output or log files
3. **Test Individual Providers**: Use provider-specific endpoints
4. **Validate Configuration**: Ensure YAML syntax is correct

### Performance Optimization

1. **Connection Pooling**: httpx handles connection reuse
2. **Request Deduplication**: Prevents duplicate concurrent requests
3. **Streaming Support**: Reduces memory usage for large responses
4. **Configurable Timeouts**: Tune based on provider characteristics

## Troubleshooting

### Common Issues

1. **Provider Not Available**: Check network connectivity and API keys
2. **Model Not Found**: Verify model routes configuration
3. **Authentication Errors**: Confirm auth_type and auth_value are correct
4. **Timeout Issues**: Adjust request_timeout in settings
5. **Streaming Issues**: Check for `event: error` in SSE streams

### Debug Commands

```bash
# Check configuration syntax
python -c "import yaml; yaml.safe_load(open('providers.yaml'))"

# Test provider connectivity
curl -v http://localhost:8080/providers

# Monitor real-time logs
tail -f logs/logs.jsonl | jq .

# Test specific model requests
curl -X POST http://localhost:8080/v1/messages/count_tokens \
  -H "Content-Type: application/json" \
  -d '{"model":"claude-3-5-haiku-20241022","messages":[{"role":"user","content":"test"}]}'
```

### Streaming Response Debugging

The system includes comprehensive debugging for streaming issues:

- **Request Lifecycle Tracking**: All streaming requests have start/complete logging
- **Error Event Detection**: Automatic detection of streaming errors
- **Provider Health Management**: Failed streams trigger provider cooldown
- **Timeout Monitoring**: Configurable timeouts for streaming operations

## Security Considerations

- **API Key Protection**: Never log or expose API keys
- **Request Validation**: All inputs are validated using Pydantic
- **Error Handling**: Sanitized error responses prevent information leakage
- **HTTPS Support**: Configure reverse proxy for TLS termination

## Deployment Considerations

### Environment Variables

```bash
# Override configuration
export ANTHROPIC_BASE_URL=http://localhost:8080
export LOG_LEVEL=INFO
export LOG_COLOR=true
```

### Production Setup

```bash
# Install production dependencies
uv sync --no-dev

# Run with production server
uvicorn src.main:app --host 0.0.0.0 --port 8080 --workers 4
```

### Monitoring and Maintenance

- **Health Checks**: Use `/` endpoint for load balancer health checks
- **Provider Status**: Monitor `/providers` for provider health
- **Log Analysis**: Parse JSON logs for performance insights
- **Configuration Updates**: Use `/providers/reload` for zero-downtime updates

This load balancer provides a robust, production-ready solution for managing multiple Claude Code providers with intelligent failover and comprehensive monitoring capabilities.

## Zed Provider Integration

The system includes advanced support for Zed providers, offering:

### Zed-Specific Features

- **Thread Management**: Automatic thread creation and rotation based on context limits
- **Mode Selection**: Smart selection between normal and burn modes
- **Context Optimization**: Intelligent context window management
- **Cost Control**: Automatic cost optimization through mode selection

### Zed Configuration Example

```yaml
providers:
  - name: "zed_provider"
    type: "zed"
    base_url: "https://zed-api.example.com"
    auth_type: "api_key"
    auth_value: "your-zed-api-key"
    enabled: true
    zed_config:
      default_mode: "normal"
      auto_burn_mode_triggers:
        - "complex_coding_task"
        - "multi_step_analysis"
      context_management:
        max_context_tokens: 120000
        rotation_threshold: 0.8
        summarization_method: "ai"
      thread_management:
        ttl: 3600
        auto_rotate: true
        task_based_isolation: true
```

### Zed Request Format

Zed uses a unique nested request structure:

```json
{
    "thread_id": "uuid",
    "prompt_id": "uuid", 
    "intent": "user_prompt",
    "mode": "normal",
    "provider": "anthropic",
    "provider_request": {
        "model": "claude-sonnet-4",
        "messages": [...],
        "max_tokens": 8192
    }
}
```

For detailed Zed integration documentation, see [docs/zed-provider-support.md](docs/zed-provider-support.md).