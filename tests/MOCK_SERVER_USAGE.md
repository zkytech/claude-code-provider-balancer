# Mock Server 使用指南

## 启动方式

### 普通模式
```bash
python tests/run_mock_server.py
```

### 自动重载模式（推荐开发时使用）
```bash
python tests/run_mock_server.py --reload
```

自动重载模式会监控以下目录的文件变化：
- `tests/framework/` - 测试框架代码
- `tests/` - 测试目录本身

## 可用端点

Mock Server 现在专注于支持新的简化测试框架，提供以下核心端点：

### 健康检查
- `GET http://localhost:8998/health` - 服务器健康状态

### API文档
- `GET http://localhost:8998/docs` - 自动生成的API文档
- `GET http://localhost:8998/endpoints` - 查看所有可用端点

### 测试上下文管理
- `GET http://localhost:8998/mock-test-context` - 查看当前测试上下文
- `POST http://localhost:8998/mock-set-context` - 设置测试上下文
- `DELETE http://localhost:8998/mock-clear-context` - 清除测试上下文

### 统一Mock Provider端点
- `POST http://localhost:8998/mock-provider/{provider_name}/v1/messages` - 统一Mock端点
- `GET http://localhost:8998/mock-provider/{provider_name}/health` - Provider健康检查

## 测试框架使用

### 基本用法
```python
from tests.framework import (
    Scenario, ProviderConfig, ProviderBehavior, 
    ExpectedBehavior, Environment
)

# 创建测试场景
scenario = Scenario(
    name="my_test",
    providers=[
        ProviderConfig(
            "test_provider", 
            ProviderBehavior.SUCCESS,
            response_data={"content": "Test response"}
        )
    ],
    expected_behavior=ExpectedBehavior.SUCCESS
)

# 使用测试环境（自动设置Mock Server上下文和Balancer）
async with Environment(scenario) as env:
    # 进行测试
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{env.balancer_url}/v1/messages",
            json={
                "model": env.model_name,
                "messages": [{"role": "user", "content": "test"}]
            }
        )
```

### 完整的Provider行为支持

- `SUCCESS` - 返回成功响应
- `STREAMING_SUCCESS` - 返回流式成功响应
- `ERROR` - 返回通用错误响应
- `TIMEOUT` - 模拟超时
- `RATE_LIMIT` - 返回429错误
- `CONNECTION_ERROR` - 连接错误
- `SSL_ERROR` - SSL/TLS错误
- `INTERNAL_SERVER_ERROR` - 内部服务器错误（500）
- `BAD_GATEWAY` - 网关错误（502）
- `SERVICE_UNAVAILABLE` - 服务不可用（503）
- `INSUFFICIENT_CREDITS` - 余额不足错误（402）
- `DUPLICATE_CACHE` - 返回确定性的缓存响应

### 高级配置选项

```python
# 带延迟和错误配置的Provider
provider_config = ProviderConfig(
    name="test_provider",
    behavior=ProviderBehavior.INSUFFICIENT_CREDITS,
    delay_ms=100,  # 100ms延迟
    error_http_code=402,
    error_message="Insufficient credits",
    provider_type="anthropic",  # 或 "openai"
    priority=1
)

# 带自定义设置的场景
scenario = Scenario(
    name="health_check_test",
    providers=[provider_config],
    expected_behavior=ExpectedBehavior.ERROR,
    settings_override={
        "unhealthy_threshold": 1,
        "failure_cooldown": 60,
        "unhealthy_response_body_patterns": [
            r'"error"\s*:\s*".*insufficient.*credits"'
        ]
    }
)
```

### 测试环境自动化

`Environment` 上下文管理器现在提供完整的测试自动化：

1. **自动配置生成** - 基于 Scenario 生成完整的 YAML 配置
2. **Mock Server 上下文设置** - 自动设置跨进程测试上下文
3. **Balancer 启动** - 自动启动独立的 Balancer 实例
4. **端口管理** - 自动分配和管理端口
5. **清理** - 测试完成后自动清理所有资源

### 跨进程通信

测试框架通过HTTP API与Mock Server进行跨进程通信：

1. **Environment** 启动时自动调用 `POST /mock-set-context` 设置测试场景
2. **Mock Server** 根据设置的上下文动态生成相应的响应
3. **Environment** 同时启动独立的 Balancer 实例进行完整的端到端测试
4. **Environment** 退出时自动调用 `DELETE /mock-clear-context` 清理上下文

这样就解决了测试进程、Mock Server 进程和 Balancer 进程间的状态共享问题。

## 开发工作流

1. 启动自动重载Mock Server:
   ```bash
   python tests/run_mock_server.py --reload
   ```

2. 编写或修改测试文件
3. Server会自动重启，无需手动重启
4. 运行测试验证更改:
   ```bash
   python -m pytest tests/test_*.py -v
   # 或使用专用的测试运行器
   python tests/run_tests.py
   ```

## 调试技巧

### 查看当前测试上下文
```bash
curl http://localhost:8998/mock-test-context | jq
```

### 手动设置测试上下文
```bash
curl -X POST http://localhost:8998/mock-set-context \
  -H "Content-Type: application/json" \
  -d '{
    "name": "debug_test",
    "expected_behavior": "success",
    "model_name": "test-model",
    "providers": [
      {
        "name": "debug_provider",
        "behavior": "success",
        "response_data": {"content": "Debug response"},
        "provider_type": "anthropic",
        "error_http_code": 200,
        "error_message": "",
        "delay_ms": 0,
        "priority": 1
      }
    ]
  }'
```

### 测试特定错误场景
```bash
# 测试余额不足错误
curl -X POST http://localhost:8998/mock-set-context \
  -H "Content-Type: application/json" \
  -d '{
    "name": "insufficient_credits_test",
    "expected_behavior": "error",
    "model_name": "test-model",
    "providers": [
      {
        "name": "credits_provider",
        "behavior": "insufficient_credits",
        "error_http_code": 402,
        "error_message": "Insufficient credits to complete request",
        "provider_type": "anthropic"
      }
    ]
  }'

# 测试统一Mock端点
curl -X POST http://localhost:8998/mock-provider/credits_provider/v1/messages \
  -H "Content-Type: application/json" \
  -d '{
    "model": "test-model",
    "messages": [{"role": "user", "content": "test"}]
  }' | jq
```

### 查看API文档
访问 http://localhost:8998/docs 可以看到完整的交互式API文档。

## 架构特点

### 简化的设计
- **零配置依赖** - 不需要任何配置文件
- **动态响应生成** - 基于测试上下文动态生成响应
- **统一端点** - 一个端点处理所有provider请求
- **自动重载** - 开发时代码变更自动重启
- **完整测试隔离** - 每个测试使用独立的 Balancer 实例

### 增强的测试能力
- **健康检查模式测试** - 支持各种错误响应模式和 HTTP 状态码
- **延迟模拟** - 可配置的响应延迟
- **流式和非流式响应** - 完整支持两种响应模式
- **Provider类型支持** - 支持 Anthropic 和 OpenAI 兼容的 Provider
- **错误分类测试** - 精确的错误类型和 HTTP 状态码控制

### 与旧架构的区别
- **旧架构**: 70+ 硬编码端点，依赖 config-test.yaml 配置文件
- **新架构**: 7个核心端点，完全动态配置，自动化测试环境管理

这种设计让测试编写更简单，维护成本更低，同时提供了更强的灵活性和测试隔离性。

## 测试文件组织

当前的测试文件使用统一的命名和结构：

- `test_duplicate_request_handling.py` - 重复请求处理测试
- `test_mixed_provider_responses.py` - 混合提供者响应测试  
- `test_multi_provider_management.py` - 多提供者管理测试
- `test_non_streaming_requests.py` - 非流式请求测试
- `test_streaming_requests.py` - 流式请求测试
- `test_provider_error_handling.py` - 提供者错误处理测试
- `test_framework_validation.py` - 框架验证测试

所有测试都使用相同的 `Scenario` + `ProviderConfig` + `Environment` 模式，确保一致性和可维护性。

## 配置工厂增强

`TestConfigFactory` 现在支持完整的健康检查配置：

```python
from tests.framework import TestConfigFactory

factory = TestConfigFactory()

# 基本配置生成
config = factory.create_config(scenario)

# 配置包含了完整的健康检查设置：
# - unhealthy_threshold: 错误阈值
# - unhealthy_reset_on_success: 成功时重置
# - unhealthy_reset_timeout: 超时重置
# - unhealthy_exception_patterns: 异常模式匹配
# - unhealthy_response_body_patterns: 响应体模式匹配  
# - unhealthy_http_codes: HTTP状态码列表
```

这些设置可以通过 `settings_override` 参数在 Scenario 中进行定制，为健康检查相关的测试提供了完整的配置支持。