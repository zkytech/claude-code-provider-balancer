# Claude Provider Balancer Tests

This directory contains comprehensive tests for the Claude Provider Balancer application using pytest.

## Test Structure

### Test Files

- **`conftest.py`** - Pytest configuration and shared fixtures
- **`test_streaming_requests.py`** - Tests for streaming request handling
- **`test_non_streaming_requests.py`** - Tests for non-streaming request handling  
- **`test_multi_provider_management.py`** - Tests for provider management and failover
- **`test_mixed_provider_responses.py`** - Tests for mixed OpenAI/Anthropic provider responses
- **`test_duplicate_request_handling.py`** - Tests for request deduplication and caching
- **`run_tests.py`** - Test runner script
- **`test_utils.py`** - Common test utilities

### Test Categories

#### 1. Streaming Request Tests (`test_streaming_requests.py`)
- ✅ Successful streaming responses
- ✅ Provider errors (500, 401, 429, etc.)  
- ✅ Connection errors and timeouts
- ✅ 200 responses with error content
- ✅ 200 responses with empty content
- ✅ Malformed JSON responses
- ✅ Partial response interruptions
- ✅ Content type mismatches

#### 2. Non-Streaming Request Tests (`test_non_streaming_requests.py`)
- ✅ Successful non-streaming responses
- ✅ System message handling
- ✅ Temperature and parameter handling
- ✅ Various error responses (500, 401, 429, etc.)
- ✅ Connection and timeout errors
- ✅ Invalid JSON and empty responses
- ✅ OpenAI format requests
- ✅ Tool usage requests
- ✅ Invalid models and missing fields

#### 3. Multi-Provider Management Tests (`test_multi_provider_management.py`)
- ✅ Primary provider success
- ✅ Failover to secondary providers
- ✅ All providers unavailable scenarios
- ✅ Provider cooldown mechanisms
- ✅ Provider recovery after cooldown
- ✅ Streaming failover
- ✅ Health check integration
- ✅ Priority ordering
- ✅ Type-specific error handling
- ✅ Concurrent request handling
- ✅ Model routing

#### 4. Mixed Provider Response Tests (`test_mixed_provider_responses.py`)
- ✅ Anthropic requests to OpenAI providers
- ✅ OpenAI requests to Anthropic providers
- ✅ Streaming format conversions
- ✅ Error format conversions
- ✅ Tool use format conversions
- ✅ Mixed provider failover
- ✅ Token counting across providers
- ✅ System message handling

#### 5. Duplicate Request Handling Tests (`test_duplicate_request_handling.py`)
- ✅ Duplicate non-streaming request caching
- ✅ Duplicate streaming request handling
- ✅ Mixed streaming/non-streaming duplicates
- ✅ Concurrent duplicate requests
- ✅ Different parameter differentiation
- ✅ System message duplicate detection
- ✅ Tool definition duplicate detection
- ✅ Cache expiration behavior
- ✅ Duplicate detection with provider failover

## Running Tests

### Prerequisites

```bash
# Install test dependencies
pip install pytest pytest-asyncio respx httpx
```

### Run All Tests

```bash
# Using the test runner script
python tests/run_tests.py

# Or directly with pytest
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/test_streaming_requests.py -v

# Run specific test function
python -m pytest tests/test_streaming_requests.py::TestStreamingRequests::test_successful_streaming_response -v
```

### Test Configuration

Tests use the following configuration:

- **Test Providers**: Mock providers are enabled via configuration
- **Async Testing**: Uses `pytest-asyncio` for async test support
- **HTTP Mocking**: Uses `respx` for HTTP request mocking
- **Headers**: Realistic Claude Code client headers for testing
- **Fixtures**: Shared test data and client fixtures

### Test Providers

Tests utilize the built-in test providers at:
- `/test-providers/anthropic/success` - Mock successful Anthropic responses
- `/test-providers/anthropic/error/{error_type}` - Mock various error responses
- `/test-providers/anthropic/streaming` - Mock streaming responses
- `/test-providers/openai/success` - Mock successful OpenAI responses

### Mock Configuration

The test configuration includes:
- Enabled test providers with configurable delays and error rates
- Multiple provider types (Anthropic and OpenAI)
- Model routing rules for different test scenarios
- Realistic authentication and headers

## Test Implementation Details

### Fixtures Used

- `async_client` - AsyncClient for making HTTP requests
- `claude_headers` - Realistic Claude Code client headers
- `test_messages_request` - Standard non-streaming request
- `test_streaming_request` - Standard streaming request
- `test_config` - Test configuration with mock providers
- `mock_provider_manager` - Mock provider manager instance

### Key Testing Patterns

1. **HTTP Mocking**: Uses `respx` to mock provider responses
2. **Async Testing**: All tests are async using `pytest.mark.asyncio`
3. **Error Simulation**: Tests various error conditions and edge cases
4. **Format Conversion**: Tests conversion between OpenAI and Anthropic formats
5. **Concurrent Testing**: Tests concurrent request scenarios
6. **Cache Testing**: Tests request deduplication and caching behavior

### Common Test Scenarios

- **Success Paths**: Normal operation with various configurations
- **Error Handling**: Provider failures, network errors, timeouts
- **Edge Cases**: Empty responses, malformed JSON, content mismatches
- **Failover**: Provider switching and recovery scenarios
- **Format Conversion**: API format compatibility between providers
- **Concurrency**: Multiple simultaneous requests and race conditions

## Extending the Tests

To add new tests:

1. **Create new test file** in the `tests/` directory
2. **Import required fixtures** from `conftest.py`
3. **Use `@pytest.mark.asyncio`** for async tests
4. **Mock HTTP responses** using `respx.mock`
5. **Add to test runner** if needed for specific execution order

Example new test:
```python
@pytest.mark.asyncio
async def test_new_feature(async_client: AsyncClient, claude_headers):
    with respx.mock:
        respx.post("http://localhost:9090/test-providers/anthropic/success").mock(
            return_value=Response(200, json={"test": "response"})
        )
        
        response = await async_client.post("/v1/messages", ...)
        assert response.status_code == 200
```