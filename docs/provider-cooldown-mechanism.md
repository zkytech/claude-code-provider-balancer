# Provider冷却机制详解

## 概述

Claude Code Provider Balancer实现了一个智能的provider冷却机制，用于处理provider故障、自动恢复和负载均衡。该机制确保了系统的高可用性和容错能力。

## 核心特性

### 1. 独立冷却状态管理

每个provider都维护独立的失败状态，互不影响：

```python
@dataclass
class Provider:
    failure_count: int = 0          # 独立的失败计数
    last_failure_time: float = 0    # 独立的最后失败时间戳
```

### 2. 自动故障检测

系统会自动检测以下类型的故障：
- HTTP错误（4xx、5xx状态码）
- 连接超时和网络错误
- 流式响应中的错误事件（`event: error`）
- JSON解析错误
- 其他异常情况

### 3. 智能恢复机制

- **即时冷却**：失败后立即进入冷却期
- **自动恢复**：冷却期结束后自动可用
- **成功重置**：成功请求后重置失败状态

## 实现细节

### 健康检查逻辑

```python
def is_healthy(self, cooldown_seconds: int = 60) -> bool:
    """检查provider是否健康（不在冷却期）"""
    if self.failure_count == 0:
        return True  # 没有失败记录，直接可用
    return time.time() - self.last_failure_time > cooldown_seconds
```

**判断条件**：
1. `failure_count == 0`：没有失败记录，直接可用
2. `当前时间 - last_failure_time > cooldown_seconds`：冷却期结束

### 失败标记机制

```python
def mark_failure(self):
    """标记provider失败"""
    self.failure_count += 1
    self.last_failure_time = time.time()
```

**触发时机**：
- 每次请求失败时立即调用
- 在重试循环中，每个provider失败都会独立标记

### 成功恢复机制

```python
def mark_success(self):
    """标记provider成功（重置失败计数）"""
    self.failure_count = 0
    self.last_failure_time = 0
```

**触发时机**：
- 非流式请求成功响应后
- 流式请求**完全**成功完成后（注意：不是开始时）

## 配置参数

### 冷却时间配置

在`providers.yaml`中配置：

```yaml
settings:
  failure_cooldown: 60  # 故障服务商的冷却时间（秒）
```

**默认值**：60秒

### 获取冷却时间

```python
def get_failure_cooldown(self) -> int:
    """从设置中获取失败冷却时间"""
    return self.settings.get('failure_cooldown', 60)
```

## 选择策略集成

### Provider过滤逻辑

在构建可用选项时，只选择健康的provider：

```python
def _build_options_from_routes(self, routes: List[ModelRoute], requested_model: str):
    cooldown = self.get_failure_cooldown()
    
    for route in routes:
        provider = self._get_provider_by_name(route.provider)
        if not provider or not provider.enabled or not provider.is_healthy(cooldown):
            continue  # 跳过不健康的provider
        
        options.append((target_model, provider, route.priority))
```

### 粘滞逻辑

系统还实现了智能的粘滞逻辑：

```python
# 活跃期间优先使用最后成功的provider
if not is_idle_period and self._last_successful_provider:
    # 将最后成功的provider放在第一位
    if provider.name == self._last_successful_provider:
        sticky_option = (model, provider, priority)
```

**空闲恢复间隔**：
- 默认300秒（5分钟）
- 空闲期间才会考虑恢复失败的provider

## 流式请求的特殊处理

### 错误检测

```python
# 预读前几行检查错误
if line.strip() == "event: error":
    raise Exception(f"Provider {provider.name} returned error event in streaming response")
```

### 成功标记时机

```python
# 只有在流式传输完全成功后才标记成功
def on_stream_success():
    current_provider.mark_success()
    if provider_manager:
        provider_manager.mark_provider_success(current_provider.name)
```

**重要**：流式请求只有在完全成功完成后才会标记success，避免过早标记成功。

## 实际运行示例

### 日志分析示例

```
06:55:02 - GAC失败 (streaming error) → 进入冷却期
06:55:02 - Claude Code Official失败 (401) → 进入冷却期
06:56:03 - WenWen失败 (timeout) → 进入冷却期
06:57:01 - "No providers available" (所有provider都在冷却期)
06:57:03 - "available_options: 2" (GAC和Claude Code Official冷却期结束)
06:57:05 - GAC失败 (529) → 重新进入冷却期
06:57:06 - Claude Code Official失败 (401) → 重新进入冷却期
06:59:26 - "available_options: 3" (所有provider冷却期结束)
```

### 冷却时间计算

假设冷却时间为60秒：
- GAC: 06:55:02失败 → 06:56:02恢复 → 06:57:03可用 ✓
- Claude Code Official: 06:55:02失败 → 06:56:02恢复 → 06:57:03可用 ✓
- WenWen: 06:56:03失败 → 06:57:03恢复，但06:57:01又失败 → 06:58:01恢复

## 监控和调试

### 健康状态查看

```bash
# 查看所有provider状态
curl http://localhost:9090/providers
```

返回示例：
```json
{
  "providers": [
    {
      "name": "GAC",
      "enabled": true,
      "healthy": true,
      "failure_count": 0,
      "last_failure_time": 0
    },
    {
      "name": "Claude Code Official", 
      "enabled": true,
      "healthy": false,
      "failure_count": 1,
      "last_failure_time": 1642521302.456
    }
  ]
}
```

### 日志监控

关键日志事件：
- `provider_request_failed`：provider失败时记录
- `provider_fallback`：切换到备用provider时记录
- `request_completed`：请求成功完成时记录

## 最佳实践

### 1. 冷却时间配置

```yaml
settings:
  failure_cooldown: 60  # 推荐60-120秒
```

**建议**：
- 短冷却时间（30-60秒）：适合网络抖动较多的环境
- 长冷却时间（120-300秒）：适合provider故障恢复较慢的情况

### 2. 监控建议

- 定期检查provider健康状态
- 监控失败率和恢复时间
- 关注日志中的故障模式

### 3. 故障处理

- 配置多个不同类型的provider
- 设置合理的优先级
- 监控provider的可用性指标

## 技术原理

### 时间戳精度

使用`time.time()`获取高精度时间戳：
- 精度：秒级浮点数
- 跨平台兼容性好
- 性能开销小

### 并发安全

虽然没有使用锁，但由于以下原因是安全的：
- 单线程异步模型（FastAPI）
- 原子操作（简单的数值更新）
- 无复杂的竞态条件

### 内存使用

每个provider只额外使用：
- `failure_count`: 4字节整数
- `last_failure_time`: 8字节浮点数

总开销极小，适合长时间运行。

## 总结

Provider冷却机制通过独立的失败状态管理、自动故障检测和智能恢复机制，确保了系统的高可用性和容错能力。该机制具有以下优势：

1. **高可用性**：自动识别和隔离故障provider
2. **快速恢复**：故障provider在冷却期后自动恢复
3. **独立管理**：每个provider独立管理，互不影响
4. **智能选择**：结合粘滞逻辑优化性能
5. **易于监控**：提供完整的状态查询和日志记录

这个机制为生产环境提供了可靠的provider管理解决方案。