# 透传模式 (Passthrough Mode)

透传模式允许 Claude Code Provider Balancer 直接将客户端请求的模型名称转发给后端服务提供商，而不进行任何模型名称的转换或替换。

## 功能说明

在正常情况下，balancer 会根据客户端请求的模型名称（如 `claude-3-5-sonnet-20241022`、`claude-3-5-haiku-20241022` 等）来判断应该使用配置中的 `big_model` 还是 `small_model`，然后将配置的模型名称发送给后端服务商。

透传模式通过在配置中将 `big_model` 或 `small_model` 设置为特殊值 `"passthrough"` 来实现，当检测到这个值时，balancer 会直接使用客户端请求的原始模型名称。

## 使用场景

透传模式适用于以下场景：

1. **后端服务商支持多种模型**：当你的服务商支持多种不同的模型，你希望客户端能够直接指定使用哪个模型
2. **模型名称保持一致**：当后端服务商使用的模型名称与客户端请求的模型名称完全一致时
3. **灵活的模型选择**：当你希望给客户端更多的模型选择自由度时
4. **测试和开发**：在测试环境中，你可能需要测试不同的模型而不想频繁修改配置

## 配置方法

### 1. 完全透传模式

将 `big_model` 和 `small_model` 都设置为 `"passthrough"`：

```yaml
providers:
  - name: "passthrough_provider"
    type: "anthropic"
    base_url: "https://api.claude-provider.com"
    auth_type: "api_key"
    auth_value: "sk-your-key-here"
    big_model: "passthrough"
    small_model: "passthrough"
    enabled: true
```

在这种配置下，所有的模型请求都会被透传：
- 客户端请求 `claude-3-5-sonnet-20241022` → 转发 `claude-3-5-sonnet-20241022`
- 客户端请求 `claude-3-5-haiku-20241022` → 转发 `claude-3-5-haiku-20241022`
- 客户端请求 `custom-model-name` → 转发 `custom-model-name`

### 2. 部分透传模式

只将其中一个模型类型设置为透传：

```yaml
providers:
  - name: "mixed_provider"
    type: "anthropic"
    base_url: "https://api.claude-provider.com"
    auth_type: "api_key"
    auth_value: "sk-your-key-here"
    big_model: "passthrough"                    # 大模型透传
    small_model: "claude-3-5-haiku-20241022"    # 小模型使用固定配置
    enabled: true
```

在这种配置下：
- 大模型请求（包含 opus、sonnet 关键词或其他未知模型）会被透传
- 小模型请求（包含 haiku 关键词）会使用配置的 `claude-3-5-haiku-20241022`

### 3. OpenAI 兼容服务商的透传

透传模式同样适用于 OpenAI 兼容的服务商：

```yaml
providers:
  - name: "openai_passthrough"
    type: "openai"
    base_url: "https://api.openrouter.ai/v1"
    auth_type: "api_key"
    auth_value: "sk-or-your-key"
    big_model: "passthrough"
    small_model: "passthrough"
    enabled: true
```

## 模型判断逻辑

balancer 使用以下逻辑来判断请求应该使用 big_model 还是 small_model：

1. **大模型判断**：如果请求的模型名称包含 `opus` 或 `sonnet` 关键词
2. **小模型判断**：如果请求的模型名称包含 `haiku` 关键词
3. **默认选择**：其他情况默认使用大模型配置

在透传模式下，这个判断逻辑仍然有效，只是最终返回的模型名称会是原始请求的名称而不是配置中的固定名称。

## 负载均衡

透传模式不会影响负载均衡功能。balancer 仍然会：

1. 在多个健康的 provider 之间轮换
2. 检测 provider 的健康状态
3. 在 provider 故障时自动切换到下一个健康的 provider
4. 应用故障冷却时间

## 示例场景

### 场景1：多模型支持的服务商

假设你有一个支持多种 Claude 模型的服务商：

```yaml
providers:
  - name: "multi_model_provider"
    type: "anthropic"
    base_url: "https://api.multi-claude.com"
    auth_type: "api_key"
    auth_value: "your-key"
    big_model: "passthrough"
    small_model: "passthrough"
    enabled: true
```

客户端可以请求任何模型：
- `claude-3-5-sonnet-20241022`
- `claude-3-opus-20240229`
- `claude-3-5-haiku-20241022`
- `claude-instant-1.2`

所有这些请求都会原样转发给后端服务商。

### 场景2：混合模式

你希望小模型使用固定的高性价比模型，但大模型请求透传：

```yaml
providers:
  - name: "hybrid_provider"
    type: "anthropic"
    base_url: "https://api.claude-service.com"
    auth_type: "api_key"
    auth_value: "your-key"
    big_model: "passthrough"
    small_model: "claude-3-5-haiku-20241022"
    enabled: true
```

这样配置后：
- 客户端请求 `claude-3-5-sonnet-20241022` → 转发 `claude-3-5-sonnet-20241022`
- 客户端请求 `claude-3-opus-20240229` → 转发 `claude-3-opus-20240229`
- 客户端请求 `claude-3-5-haiku-20241022` → 转发 `claude-3-5-haiku-20241022`（固定）

## 注意事项

1. **后端兼容性**：确保你的后端服务商支持客户端请求的模型名称
2. **错误处理**：如果后端服务商不支持某个模型，会返回相应的错误信息
3. **配置验证**：`"passthrough"` 必须是精确的字符串匹配（区分大小写）
4. **日志记录**：透传的模型名称会在日志中正确记录，便于调试和监控

## 测试透传功能

你可以通过以下方式测试透传功能：

1. **查看提供商状态**：
   ```bash
   curl http://localhost:8080/providers
   ```

2. **发送测试请求**：
   ```bash
   curl -X POST http://localhost:8080/v1/messages \
     -H "Content-Type: application/json" \
     -H "x-api-key: your-key" \
     -d '{
       "model": "custom-model-name",
       "max_tokens": 100,
       "messages": [{"role": "user", "content": "Hello"}]
     }'
   ```

3. **检查日志**：查看日志中的模型选择记录，确认是否正确透传了模型名称。

透传模式为 Claude Code Provider Balancer 提供了更大的灵活性，让你能够在保持负载均衡和故障恢复功能的同时，给客户端更多的模型选择自由度。