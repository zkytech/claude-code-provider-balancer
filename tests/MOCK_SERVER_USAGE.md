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
- `tests/framework/` - 新测试框架代码
- `src/routers/mock_providers/` - 传统Mock Provider代码
- `tests/` - 测试目录本身

## 可用端点

### 健康检查
- `GET http://localhost:8998/health`

### 端点列表
- `GET http://localhost:8998/endpoints` - 查看所有可用端点

### 测试上下文管理（新功能）
- `GET http://localhost:8998/mock-test-context` - 查看当前测试上下文
- `POST http://localhost:8998/mock-set-context` - 设置测试上下文
- `DELETE http://localhost:8998/mock-clear-context` - 清除测试上下文

### 统一Mock Provider（新功能）
- `POST http://localhost:8998/mock-provider/{provider_name}/v1/messages` - 统一Mock端点
- `GET http://localhost:8998/mock-provider/{provider_name}/health` - Provider健康检查

## 使用新测试框架

### 基本用法
```python
from framework import TestScenario, ProviderConfig, ProviderBehavior, TestEnvironment

# 创建测试场景
scenario = TestScenario(
    name="my_test",
    providers=[
        ProviderConfig("test_provider", ProviderBehavior.SUCCESS)
    ]
)

# 使用测试环境（自动设置Mock Server上下文）
async with TestEnvironment(scenario) as env:
    # 进行测试
    response = await client.post(
        "/v1/messages",
        json={"model": env.effective_model_name, ...}
    )
```

### 跨进程通信

新的测试框架通过HTTP API与Mock Server进行跨进程通信：

1. **TestEnvironment** 启动时自动调用 `POST /mock-set-context` 设置测试场景
2. **Mock Server** 根据设置的上下文生成相应的响应
3. **TestEnvironment** 退出时自动调用 `DELETE /mock-clear-context` 清理上下文

这样就解决了测试进程和Mock Server进程间的状态共享问题。

## 支持的Provider行为

- `SUCCESS` - 返回成功响应
- `ERROR` - 返回错误响应
- `TIMEOUT` - 模拟超时
- `RATE_LIMIT` - 返回429错误
- `DUPLICATE_CACHE` - 返回确定性的缓存响应
- `CONNECTION_ERROR` - 连接错误
- `SSL_ERROR` - SSL错误
- `INSUFFICIENT_CREDITS` - 余额不足错误

## 开发工作流

1. 启动自动重载Mock Server:
   ```bash
   python tests/run_mock_server.py --reload
   ```

2. 修改测试框架代码（`tests/framework/`）

3. Server会自动重启，无需手动重启

4. 运行测试验证更改

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
    "providers": [
      {
        "name": "debug_provider",
        "behavior": "success",
        "response_data": {"content": "Debug response"}
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

## 与传统测试的兼容性

新的统一Mock路由与传统的专门Mock端点并存，确保向后兼容：

- 旧测试继续使用专门的Mock端点（如 `/test-providers/duplicate-success/v1/messages`）
- 新测试使用统一Mock端点（如 `/mock-provider/{provider_name}/v1/messages`）

这样可以渐进式地迁移测试，无需一次性全部更改。