# 错误分类机制文档

## 概述

Claude Code Provider Balancer 实现了智能的错误分类机制，用于决定当 provider 返回错误时，是否应该尝试其他 provider（failover）还是直接将错误返回给客户端。

## 设计原理

并不是所有 provider 返回的错误都需要重试其他 provider。某些错误（如认证失败、权限不足、请求格式错误等）应该直接返回给客户端，而不是浪费时间尝试其他 provider。

## 配置方式

在 `providers.yaml` 中配置两个错误分类列表：

### failover_error_types（错误类型）

基于错误的语义类型判断，适合处理异常类型和业务逻辑错误：

```yaml
settings:
  failover_error_types:
    - "connection_error"      # 连接错误
    - "timeout_error"         # 超时错误
    - "read_timeout"          # 读取超时
    - "internal_server_error" # 服务器内部错误
    - "service_unavailable"   # 服务不可用
    - "gateway_timeout"       # 网关超时
    - "rate_limit_exceeded"   # 速率限制
    - "overloaded_error"      # 服务过载
```

### failover_http_codes（HTTP状态码）

基于HTTP响应状态码判断，适合处理HTTP协议层面的错误：

```yaml
settings:
  failover_http_codes:
    - 500  # Internal Server Error
    - 502  # Bad Gateway
    - 503  # Service Unavailable
    - 504  # Gateway Timeout
    - 429  # Too Many Requests
    - 520  # Unknown Error
    - 521  # Web Server Is Down
    - 522  # Connection Timed Out
    - 523  # Origin Is Unreachable
    - 524  # A Timeout Occurred
```

## 判断逻辑

错误分类机制的判断优先级：

1. **HTTP状态码优先**：如果响应包含HTTP状态码且在 `failover_http_codes` 列表中，则进行failover
2. **错误类型判断**：如果错误类型在 `failover_error_types` 列表中，则进行failover
3. **异常类型判断**：检查具体的异常类型（如 `httpx.ReadTimeout`）

```python
def should_failover_on_error(self, error, http_status_code, error_type):
    # 1. 先检查HTTP状态码
    if http_status_code and http_status_code in failover_http_codes:
        return True
    
    # 2. 再检查错误类型
    if error_type and error_type in failover_error_types:
        return True
    
    # 3. 最后检查异常类型
    if isinstance(error, httpx.ReadTimeout):
        return "timeout_error" in failover_error_types
    
    return False
```

## 不会 Failover 的错误

以下错误类型会直接返回给客户端，不会尝试其他 provider：

- **认证错误**：401 Unauthorized
- **权限错误**：403 Forbidden  
- **请求格式错误**：400 Bad Request
- **资源不存在**：404 Not Found
- **方法不允许**：405 Method Not Allowed
- **请求过大**：413 Payload Too Large
- **不支持的媒体类型**：415 Unsupported Media Type
- **业务逻辑错误**：自定义的业务错误类型

## 流式响应错误处理

对于流式响应（Server-Sent Events），系统会解析流中的错误事件：

```python
# 检测流式响应中的错误事件
if line.startswith("event: error"):
    error_event = line[len("event: "):].strip()
    # 根据错误事件类型决定是否failover
    if error_event in failover_error_types:
        # 进行failover处理
    else:
        # 直接返回错误给客户端
```

## 实现细节

### 核心方法

1. **`should_failover_on_error()`**：判断是否应该failover
2. **`get_error_classification()`**：获取错误分类和failover决策
3. **`_extract_anthropic_error_type()`**：从Anthropic API响应中提取错误类型

### 日志记录

错误分类过程会记录详细的日志信息：

```python
logger.info(f"Error classification: type={error_type}, should_failover={should_failover}")
```

### 错误映射

系统会将HTTP状态码映射到具体的错误类型：

- 500 → "internal_server_error"
- 502 → "bad_gateway"
- 503 → "service_unavailable"
- 504 → "gateway_timeout"
- 429 → "rate_limit_exceeded"

## 使用示例

### 配置示例

```yaml
settings:
  failover_error_types:
    - "connection_error"
    - "timeout_error"
    - "internal_server_error"
    - "service_unavailable"
    - "rate_limit_exceeded"
    
  failover_http_codes:
    - 500
    - 502
    - 503
    - 504
    - 429
```

### 错误处理流程

1. 客户端发送请求到 Provider A
2. Provider A 返回 401 Unauthorized
3. 系统检查：401 不在 `failover_http_codes` 列表中
4. 错误类型为 "unauthorized"，不在 `failover_error_types` 列表中
5. 系统直接将 401 错误返回给客户端，不尝试其他 provider

## 优势

1. **减少无效重试**：避免对不可恢复的错误进行重试
2. **提高响应速度**：快速失败，减少客户端等待时间
3. **资源节约**：避免浪费其他 provider 的配额
4. **更好的错误体验**：客户端能够收到准确的错误信息

## 注意事项

1. **配置准确性**：需要根据实际使用的 provider 特性调整错误分类列表
2. **定期更新**：随着 provider API 的更新，可能需要调整错误分类配置
3. **测试验证**：在生产环境使用前，建议充分测试各种错误场景
4. **监控告警**：建议对错误分类的效果进行监控和分析

## 相关文件

- `src/provider_manager.py`：错误分类核心逻辑
- `src/main.py`：请求处理和错误分类调用
- `providers.yaml`：错误分类配置
- `docs/provider-cooldown-mechanism.md`：相关的冷却机制文档