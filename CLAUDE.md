# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **Claude Code Provider Balancer** - a sophisticated FastAPI-based proxy service that provides intelligent load balancing and failover for multiple Claude Code providers and OpenAI-compatible services. The system ensures high availability through automated provider switching, request deduplication, and comprehensive health monitoring.

## Development Commands

### Environment Setup
```bash
# Install dependencies using uv (recommended for faster package management)
uv sync

# Or using pip with requirements file
pip install -r requirements.txt

# Install development dependencies (includes pytest, ruff, mypy, etc.)
uv sync --group dev
```

### Running the Application
```bash
# Development mode with auto-reload
python src/main.py

# Production mode
uvicorn src.main:app --host 0.0.0.0 --port 9090

# Background execution
nohup uvicorn src.main:app --host 0.0.0.0 --port 9090 > logs/server.log 2>&1 &
```

### Testing
```bash
# Run all tests (recommended - includes proper async handling)
python tests/run_tests.py

# Run specific test file
python -m pytest tests/test_multi_provider_management.py -v

# Run with coverage reporting
python -m pytest tests/ --cov=src --cov-report=html

# Run individual test categories
python -m pytest tests/test_streaming_requests.py -v
python -m pytest tests/test_non_streaming_requests.py -v
python -m pytest tests/test_duplicate_request_handling.py -v

# Run mock server for end-to-end testing
python tests/run_mock_server.py
```

### Code Quality
```bash
# Format code
ruff format src/ tests/

# Lint code
ruff check src/ tests/

# Type checking (optional)
mypy src/
```

### Configuration Management
```bash
# Copy example config
cp config.example.yaml config.yaml

# Hot reload configuration (no restart needed)
curl -X POST http://localhost:9090/providers/reload

# Check provider status
curl -s http://localhost:9090/providers | jq '.'
```

## Architecture Overview

The system follows a modular FastAPI architecture with clear separation of concerns:

### Core Components

1. **Provider Manager (`src/core/provider_manager.py`)**
   - Multi-provider load balancing with priority-based selection
   - Real-time health monitoring and automatic failover
   - Configurable cooling periods for failed providers
   - Support for both Anthropic and OpenAI-compatible APIs

2. **Message Handler (`src/handlers/message_handler.py`)**
   - Intelligent request routing based on model patterns
   - Format conversion between Anthropic and OpenAI APIs
   - Error classification and retry logic
   - Streaming and non-streaming response handling

3. **OAuth Integration (`src/oauth/oauth_manager.py`)**
   - Claude Code OAuth 2.0 flow implementation
   - Automatic token refresh and secure storage
   - Multi-user session management

4. **Request Deduplication (`src/caching/deduplication.py`)**
   - Content-based request hashing and deduplication
   - Concurrent request merging to reduce backend load
   - Configurable timeout and cache policies

5. **API Conversion (`src/conversion/`)**
   - Bidirectional format conversion (Anthropic ↔ OpenAI)
   - Error code mapping and normalization
   - Token counting and billing statistics

### Router Structure
- `src/routers/messages.py` - Core messaging endpoints
- `src/routers/oauth.py` - OAuth authentication flow
- `src/routers/health.py` - Health checks and monitoring
- `src/routers/management.py` - Configuration management
- `src/routers/mock_provider.py` - Testing utilities

### Data Models
All data structures use Pydantic models in `src/models/` for type safety and validation:
- `messages.py` - Message format definitions
- `requests.py` - Request/response schemas
- `errors.py` - Error classification
- `tools.py` - Tool calling support

## Configuration

The system uses YAML-based configuration with hot-reload support. Key configuration sections:

### Provider Configuration
```yaml
providers:
  - name: "anthropic_official"
    type: "anthropic"
    base_url: "https://api.anthropic.com"
    auth_type: "api_key"
    auth_value: "your-api-key"
    enabled: true
```

### Model Routing
```yaml
model_routes:
  "*sonnet*":
    - provider: "provider1"
      model: "passthrough"
      priority: 1
    - provider: "provider2" 
      model: "claude-3-5-sonnet-20241022"
      priority: 2
```

### Global Settings
```yaml
settings:
  selection_strategy: "priority"  # priority | round_robin | random
  failure_cooldown: 180  # seconds
  sticky_provider_duration: 300  # seconds - duration to prefer last successful provider
  unhealthy_threshold: 2  # number of errors before marking provider unhealthy
  unhealthy_error_types: ["connection_error", "Insufficient credits"]  # errors that trigger unhealthy marking
  unhealthy_http_codes: [402, 404, 429, 500, 502, 503, 504]  # HTTP codes that trigger unhealthy marking
  log_level: "INFO"
  host: "127.0.0.1"
  port: 9090
```

### API Authentication (Optional)
The balancer supports API key authentication consistent with upstream provider patterns:

```yaml
auth:
  enabled: true          # Enable/disable API authentication
  api_key: "your-key"    # Single API key (matches upstream provider tokens)
  exempt_paths:          # Paths that don't require authentication
    - "/health"
    - "/docs" 
    - "/redoc"
    - "/openapi.json"
```

**Authentication Usage (supports both upstream patterns):**
- **Anthropic style**: `x-api-key: your-api-key` header
- **OpenAI style**: `Authorization: Bearer your-api-key` header
- Exempt paths (health checks, docs) don't require authentication
- Invalid/missing API keys return 401 Unauthorized
- Follows the same authentication logic as upstream providers

## Key API Endpoints

### Core Messaging
- `POST /v1/messages` - Send messages with intelligent routing
- `POST /v1/messages/count_tokens` - Token counting and billing

### Management  
- `GET /providers` - View real-time provider status
- `POST /providers/reload` - Hot-reload configuration
- `GET /health` - Service health check

### OAuth (Optional)
- `GET /oauth/authorize` - Start OAuth flow
- `GET /oauth/callback` - Handle OAuth callback
- `GET /oauth/status` - Check authentication status

## Error Handling

The system implements comprehensive error classification:

### Unhealthy Provider Detection
Only specific error types trigger marking providers as unhealthy:
- Network errors: `connection_error`, `timeout_error`, `ssl_error`
- Server errors: `internal_server_error`, `bad_gateway`, `service_unavailable`
- Rate limiting: `too_many_requests`, `rate_limit_exceeded`
- Provider-specific: `没有可用token`, `无可用模型`, `Insufficient credits`

### HTTP Status Codes for Unhealthy Detection
- 402, 404, 408, 429, 500, 502, 503, 504
- Cloudflare errors: 520-524

### Failover Logic
When a provider is marked as unhealthy:
1. **For streaming requests**: If response headers already sent, cannot failover (return error)
2. **For non-streaming requests**: Always attempt failover to next available provider
3. **When no providers available**: Return "All providers failed" error

### Error Response Format
```json
{
  "error": {
    "type": "provider_error",
    "message": "Provider temporarily unavailable", 
    "code": "PROVIDER_UNAVAILABLE",
    "details": {
      "provider": "provider_name",
      "retry_after": 30
    }
  }
}
```

## Testing Strategy

### Test Files
- `tests/test_multi_provider_management.py` - Provider switching and failover
- `tests/test_streaming_requests.py` - Streaming response handling
- `tests/test_non_streaming_requests.py` - Non-streaming requests
- `tests/test_duplicate_request_handling.py` - Request deduplication
- `tests/test_mixed_provider_responses.py` - Mixed provider scenarios

### Mock Testing
```bash
# Start mock server for end-to-end testing
python tests/run_mock_server.py

# Run tests against mock server
python -m pytest tests/ -v
```

## Monitoring and Debugging

### Real-time Monitoring
```bash
# Monitor provider status
watch -n 5 'curl -s http://localhost:9090/providers | jq .'

# View live logs
tail -f logs/logs.jsonl | jq '.'

# Filter error logs
tail -f logs/logs.jsonl | jq 'select(.level == "ERROR")'

# Monitor OAuth events
tail -f logs/logs.jsonl | jq 'select(.message | contains("oauth"))'
```

### Performance Analysis
```bash
# Check system resources
htop

# Network connections
netstat -tlnp | grep :9090

# Request statistics
cat logs/logs.jsonl | jq 'select(.message | contains("request"))' | wc -l
```

## Common Troubleshooting

### Provider Issues
- **Connection failures**: Check API keys, network, and provider status at `/providers`
- **Rate limiting**: Monitor error logs for rate limit responses
- **OAuth problems**: Verify OAuth config and check `/oauth/status`

### Configuration Issues  
- **Config not applied**: Use `POST /providers/reload` for hot reload
- **Invalid YAML**: Validate syntax with `python -c "import yaml; print(yaml.safe_load(open('config.yaml')))"`
- **Model routing**: Check model patterns in `model_routes` section

### Performance Issues
- **Slow responses**: Check provider health and timeout configurations
- **Memory usage**: Review caching settings and restart if needed
- **High CPU**: Monitor concurrent requests and provider distribution

## Client Configuration

To use Claude Code with the balancer:

### Basic Usage
```bash
# Set proxy URL
export ANTHROPIC_BASE_URL=http://localhost:9090

# Start Claude Code
claude
```

### With Authentication
If authentication is enabled, use either authentication style:

```bash
# Set proxy URL
export ANTHROPIC_BASE_URL=http://localhost:9090

# Option 1: Anthropic style (x-api-key header)
curl -H "x-api-key: your-api-key" \
     -H "Content-Type: application/json" \
     -d '{"model": "claude-3-5-sonnet-20241022", "messages": [...]}' \
     http://localhost:9090/v1/messages

# Option 2: OpenAI style (Authorization Bearer header)  
curl -H "Authorization: Bearer your-api-key" \
     -H "Content-Type: application/json" \
     -d '{"model": "claude-3-5-sonnet-20241022", "messages": [...]}' \
     http://localhost:9090/v1/messages
```

All Claude Code requests will be intelligently routed through the balancer with automatic failover and load distribution.

## Development Notes

### Code Standards
- **Add LogEvent enums first** - Ensure type safety and consistency for logging events
- **Prefer Pydantic models** - Use Pydantic for all data structure validation
- **Async-first** - All I/O operations should use async/await patterns
- **Unified error handling** - Use consistent error handling mechanisms

### Architecture Decisions
- **Provider management** - Use ProviderManager for unified provider lifecycle management
- **Caching strategy** - Content hash-based intelligent request deduplication
- **OAuth integration** - Independent OAuth manager supporting multi-user concurrent authentication
- **Streaming processing** - Use ParallelBroadcaster for efficient streaming response handling

### Testing Approach
- **Unit tests** - Each core module has corresponding test files
- **Integration tests** - Test provider switching and failover scenarios  
- **Mock testing** - Use mock servers for end-to-end testing
- **Framework validation** - Use `tests/test_framework_validation.py` to validate test infrastructure

### Project Dependencies
- **Python 3.10+** required (specified in pyproject.toml)
- **FastAPI with standard extras** for web framework and automatic docs
- **HTTPX** for async HTTP client operations
- **Pydantic v2** for data validation and settings management
- **PyYAML** for configuration file parsing
- **Tiktoken** for accurate token counting
- **Watchdog** for configuration file monitoring and hot reload