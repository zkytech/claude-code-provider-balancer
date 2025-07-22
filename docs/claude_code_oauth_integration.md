# Claude Code OAuth 自动认证集成

## 概述

本系统集成 Claude Code Official 的 OAuth 2.0 自动认证功能，支持：
- 🔐 自动OAuth授权流程
- 💾 内存token存储管理  
- 🔄 多账号轮换机制
- 🕐 自动token刷新 (5分钟提前)
- ⚡ 401错误自动处理
- 🔑 Keyring持久化存储

## 配置方式

### 1. 修改 providers.yaml

```yaml
providers:
  - name: "Claude Code Official"
    type: "anthropic"
    base_url: "https://api.anthropic.com"
    auth_type: "auth_token"
    auth_value: "oauth"  # 使用OAuth token认证
    enabled: true
```

**全局OAuth配置:**
```yaml
settings:
  oauth:
    enable_auto_refresh: true  # 启用自动刷新
    enable_persistence: true   # 启用keyring持久化存储
    service_name: "claude-code-balancer"  # keyring服务名称
```

**配置说明:**
- `auth_value: "oauth"` - 表示使用OAuth token认证
- `enable_persistence: true` - Token通过系统keyring持久化存储，重启后自动加载

## 使用流程

### 1. 启动服务

```bash
python src/main.py
```

### 2. 首次授权

当provider返回401错误时，控制台显示授权URL：
```
🔐 CLAUDE CODE OFFICIAL AUTHORIZATION REQUIRED
Please authorize: https://claude.ai/oauth/authorize?code=true&client_id=...
After login, copy the 'code' parameter and run:
curl -X POST http://localhost:9090/oauth/exchange-code \
     -H "Content-Type: application/json" \
     -d '{"code":"YOUR_CODE","account_email":"your@email.com"}'
```

### 3. 完成授权

1. 点击授权URL，登录Claude
2. 复制回调URL中的 `code` 参数
3. 调用交换端点完成授权

### 4. 自动管理

系统自动：
- ✅ 交换token并持久化存储
- ✅ 启动自动刷新任务（提前5分钟）
- ✅ 多账号轮换负载均衡

## 多账号支持

系统支持多个Claude账号token，使用轮换机制分配请求，并自动统计使用情况：

```bash
# 查看token状态
curl http://localhost:9090/oauth/status

# 返回示例（含使用统计）
{
  "total_tokens": 2,
  "tokens": [
    {
      "account_email": "user1@example.com",
      "expires_in_minutes": 55.2,
      "is_healthy": true,
      "usage_count": 127,
      "last_used": "5分钟前",
      "last_used_timestamp": 1753196757,
      "created_at": 1753192857,
      "scopes": ["org:create_api_key", "user:profile", "user:inference"]
    },
    {
      "account_email": "user2@example.com", 
      "expires_in_minutes": 62.1,
      "is_healthy": true,
      "usage_count": 89,
      "last_used": "2小时前",
      "last_used_timestamp": 1753189557,
      "created_at": 1753185957,
      "scopes": ["org:create_api_key", "user:profile", "user:inference"]
    }
  ]
}
```

## 管理API

### 主要接口

#### 1. 交换授权码
```bash
POST /oauth/exchange-code
{
  "code": "authorization_code",
  "account_email": "user@example.com"
}
```

#### 2. 查看token状态
```bash
GET /oauth/status
```

#### 3. 删除token
```bash
DELETE /oauth/tokens/{account_email}
```

#### 4. 清除所有token
```bash
DELETE /oauth/tokens
```

## 核心功能

### 自动刷新机制
- 过期前5分钟自动刷新
- 失败重试（1小时后）
- 多token独立管理

### 持久化存储
- 使用系统keyring安全存储
- 重启后自动加载token
- 支持多用户环境

### 使用统计
- 自动记录每个token使用次数
- 追踪最后使用时间（人性化显示）
- 统计数据持久化存储
- 支持使用模式分析

### 错误处理
- 401错误自动生成授权URL
- Token过期透明处理
- 自动重试机制

### 安全机制
- OAuth 2.0 PKCE流程
- 状态参数防CSRF
- 最小权限原则

## 故障排除

### 常见问题

1. **授权码交换失败** - 检查code是否过期（10分钟有效期）
2. **Token刷新失败** - 确认网络可访问anthropic.com
3. **重启后丢失token** - 确认`enable_persistence: true`
4. **Keyring访问失败** - 安装keyring库: `pip install keyring`

### 调试日志

```yaml
settings:
  log_level: "DEBUG"  # 查看详细OAuth流程
```

## 技术实现

### 核心组件
- **oauth_manager.py** - OAuth认证管理器
- **provider_manager.py** - Provider管理增强
- **main.py** - API端点集成

### 关键特性
- PKCE安全流程
- Keyring持久化存储  
- 多账号轮换策略
- 自动token刷新