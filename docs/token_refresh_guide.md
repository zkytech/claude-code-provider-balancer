# 自动 Token 刷新指南

## 概述

本系统支持自动刷新 OAuth 2.0 token，适用于需要定期更新访问令牌的服务提供商（如 Claude Code Official）。

## 使用前提

⚠️ **重要**: 你必须首先通过手动 OAuth 流程获取以下信息：
- `client_id`: OAuth 客户端 ID
- `client_secret`: OAuth 客户端密钥  
- `refresh_token`: 长期有效的刷新令牌

## 配置步骤

### 1. 设置环境变量

```bash
export CLAUDE_CLIENT_ID="your_oauth_client_id"
export CLAUDE_CLIENT_SECRET="your_oauth_client_secret"  
export CLAUDE_REFRESH_TOKEN="your_long_lived_refresh_token"
```

### 2. 修改 providers.yaml

在需要自动刷新的 provider 配置中添加 `auto_refresh_config`：

```yaml
providers:
  - name: "Claude Code Official"
    type: "anthropic"
    base_url: "https://api.anthropic.com"
    auth_type: "auth_token"
    auth_value: ""  # 初始可留空，会被自动刷新的token填充
    enabled: true
    # 自动token刷新配置
    auto_refresh_config:
      enabled: true  # 启用自动刷新
      token_url: "https://api.anthropic.com/oauth/token"  # 实际的token端点
      client_id_env: "CLAUDE_CLIENT_ID"
      client_secret_env: "CLAUDE_CLIENT_SECRET" 
      refresh_token_env: "CLAUDE_REFRESH_TOKEN"
```

### 3. 启动服务

```bash
python src/main.py
```

服务启动时会自动为启用了 `auto_refresh_config` 的 provider 启动后台刷新任务。

## 工作原理

1. **后台任务**: 每个启用自动刷新的 provider 都会启动一个独立的后台任务
2. **定期刷新**: 根据 token 的 `expires_in` 字段，提前 5 分钟自动刷新
3. **内存更新**: 新的 access_token 直接更新到内存中的 provider 配置
4. **错误处理**: 刷新失败时会记录错误并重试（默认 1 小时后）

## 日志监控

启用后，你可以在日志中看到类似信息：

```
[INFO] Starting token refresh for provider: Claude Code Official
[INFO] Successfully refreshed token for provider using client_id: abc12...
```

## 故障排除

### 常见错误

1. **环境变量缺失**
   ```
   [ERROR] Missing environment variable: 'CLAUDE_CLIENT_ID'
   ```
   解决：检查环境变量是否正确设置

2. **刷新失败**  
   ```
   [ERROR] Failed to refresh token: 401 Unauthorized
   ```
   解决：检查 `client_secret` 和 `refresh_token` 是否有效

3. **token_url 错误**
   ```
   [ERROR] Failed to refresh token: 404 Not Found
   ```
   解决：确认 `token_url` 是否为正确的 OAuth token 端点

### 调试建议

1. 先手动测试 OAuth 刷新流程，确认所有凭证有效
2. 检查 provider 的官方文档获取正确的 `token_url`
3. 监控日志文件了解刷新状态和错误

## 安全注意事项

- ⚠️ **绝不要** 将 `client_secret` 和 `refresh_token` 硬编码到配置文件中
- ✅ **始终** 使用环境变量存储敏感信息
- 🔄 定期轮换 `refresh_token`（如果 provider 支持）
- 📝 监控刷新失败，及时更新过期的凭证

## 禁用自动刷新

要禁用自动刷新，只需将 `auto_refresh_config.enabled` 设置为 `false` 并重启服务。