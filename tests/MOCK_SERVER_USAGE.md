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

Mock Server现在专注于支持新的简化测试框架，提供以下核心端点：

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
from framework import (
    TestScenario, ProviderConfig, ProviderBehavior, 
    ExpectedBehavior, TestEnvironment
)

# 创建测试场景
scenario = TestScenario(
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

# 使用测试环境（自动设置Mock Server上下文）
async with TestEnvironment(scenario) as env:
    # 进行测试
    response = await client.post(
        f"http://localhost:8998/mock-provider/test_provider/v1/messages",
        json={
            "model": env.effective_model_name,
            "messages": [{"role": "user", "content": "test"}]
        }
    )
```

### 支持的Provider行为

- `SUCCESS` - 返回成功响应
- `STREAMING_SUCCESS` - 返回流式成功响应
- `ERROR` - 返回错误响应
- `TIMEOUT` - 模拟超时
- `RATE_LIMIT` - 返回429错误
- `CONNECTION_ERROR` - 连接错误
- `SERVICE_UNAVAILABLE` - 服务不可用（503）
- `INSUFFICIENT_CREDITS` - 余额不足错误（402）
- `DUPLICATE_CACHE` - 返回确定性的缓存响应

### 跨进程通信

测试框架通过HTTP API与Mock Server进行跨进程通信：

1. **TestEnvironment** 启动时自动调用 `POST /mock-set-context` 设置测试场景
2. **Mock Server** 根据设置的上下文动态生成相应的响应
3. **TestEnvironment** 退出时自动调用 `DELETE /mock-clear-context` 清理上下文

这样就解决了测试进程和Mock Server进程间的状态共享问题。

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
        "provider_type": "anthropic"
      }
    ]
  }'
```

### 测试统一Mock端点
```bash
curl -X POST http://localhost:8998/mock-provider/debug_provider/v1/messages \
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

### 与旧架构的区别
- **旧架构**: 70+ 硬编码端点，依赖config-test.yaml配置文件
- **新架构**: 7个核心端点，完全动态配置

这种设计让测试编写更简单，维护成本更低，同时提供了更强的灵活性。

## 测试文件组织

当前的测试文件使用统一的命名和结构：

- `test_duplicate_request_handling.py` - 重复请求处理测试
- `test_mixed_provider_responses.py` - 混合提供者响应测试
- `test_multi_provider_management.py` - 多提供者管理测试
- `test_non_streaming_requests.py` - 非流式请求测试
- `test_streaming_requests.py` - 流式请求测试
- `test_unhealthy_counting.py` - 不健康计数测试
- `test_framework_validation.py` - 框架验证测试

所有测试都使用相同的 `TestScenario` + `ProviderConfig` + `TestEnvironment` 模式，确保一致性和可维护性。