# Claude Code Provider Balancer - 测试文档

## 测试概述

本项目包含 **65个测试用例**，全面覆盖了Claude Code Provider Balancer的所有功能特性，包括流式传输、负载均衡、故障转移、重复请求处理等核心功能。

## 测试架构设计

### 服务分离架构

- **主服务端口**: 9090 (生产环境)
- **测试Mock服务端口**: 8998 (测试环境)
- **完全独立**: 测试服务与生产服务完全分离，互不干扰

### Mock Provider系统

我们使用真实的Mock Provider (`src/routers/mock_provider.py`) 而不是respx模拟，因为：

1. **真实流式传输**: 能够测试真正的streaming延迟和时序
2. **问题检测能力**: 能够发现"假streaming"问题（批量缓冲vs实时流式）
3. **完整功能覆盖**: 支持SSE错误、连接错误、超时等各种场景

## 测试文件结构

```
tests/
├── README.md                           # 本文档
├── conftest.py                         # 测试配置和fixtures
├── config-test.yaml                    # 测试环境配置
├── test_config.py                      # 测试URL配置管理
├── run_mock_server.py                  # 独立Mock服务器
├── test_utils.py                       # 测试工具函数
├── test_streaming_requests.py          # 流式传输测试 (20个测试)
├── test_duplicate_request_handling.py  # 重复请求处理测试 (9个测试)
├── test_non_streaming_requests.py      # 非流式传输测试 (12个测试)
├── test_multi_provider_management.py   # 多Provider管理测试 (11个测试)
└── test_mixed_provider_responses.py    # 混合Provider响应测试 (13个测试)
```

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

## 测试运行方式

### 方式一：自动化测试（推荐）

```bash
cd /Users/alanguo/Projects/claude-code-provider-balancer

# 运行所有测试
python -m pytest tests/ -v

# 运行特定测试文件
python -m pytest tests/test_streaming_requests.py -v
python -m pytest tests/test_duplicate_request_handling.py -v
```

### 方式二：手动启动Mock服务

如果需要调试或查看详细的Mock Provider行为：

```bash
# 终端1: 启动Mock Provider服务器
python tests/run_mock_server.py

# 终端2: 运行测试
python -m pytest tests/ -v
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