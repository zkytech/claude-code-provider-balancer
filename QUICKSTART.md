# 快速开始指南

欢迎使用 Claude Code Provider Balancer！这个指南将帮助你在几分钟内设置并运行负载均衡器。

## 🚀 快速安装

### 1. 克隆项目
```bash
git clone <repository-url>
cd claude-code-provider-balancer
```

### 2. 安装依赖
```bash
# 使用 pip 安装
pip install -r requirements.txt

# 或者使用 uv (推荐)
uv sync
```

### 3. 配置提供商
```bash
# 复制配置模板
cp providers.example.yaml providers.yaml

# 编辑配置文件
vim providers.yaml  # 或使用你喜欢的编辑器
```

## ⚙️ 基本配置

编辑 `providers.yaml` 文件，添加你的服务商：

```yaml
providers:
  # Anthropic 官方 API
  - name: "anthropic_official"
    type: "anthropic"
    base_url: "https://api.anthropic.com"
    auth_type: "api_key"
    auth_value: "sk-ant-your-actual-key-here"
    big_model: "claude-3-5-sonnet-20241022"
    small_model: "claude-3-5-haiku-20241022"
    enabled: true
    
  # 第三方 Claude 服务商（使用 auth_token）
  - name: "custom_claude_provider"
    type: "anthropic"
    base_url: "https://your-claude-provider.com"
    auth_type: "auth_token"
    auth_value: "your-auth-token-here"
    big_model: "claude-3-5-sonnet-20241022"
    small_model: "claude-3-5-haiku-20241022"
    enabled: true
    
  # OpenRouter 作为备用
  - name: "openrouter_backup"
    type: "openai"
    base_url: "https://openrouter.ai/api/v1"
    auth_type: "api_key"
    auth_value: "sk-or-your-openrouter-key"
    big_model: "anthropic/claude-3-5-sonnet"
    small_model: "anthropic/claude-3-5-haiku"
    enabled: true
    
  # 透传模式示例 - 直接转发客户端请求的模型名称
  - name: "passthrough_provider"
    type: "anthropic"
    base_url: "https://api.claude-provider.com"
    auth_type: "api_key"
    auth_value: "sk-your-key-here"
    big_model: "passthrough"     # 透传大模型请求
    small_model: "passthrough"   # 透传小模型请求
    enabled: true

settings:
  failure_cooldown: 60    # 故障服务商冷却时间（秒）
  request_timeout: 30     # 请求超时时间（秒）
  log_level: "INFO"       # 日志级别
  host: "127.0.0.1"       # 服务器地址
  port: 8080              # 服务器端口
```

## 🏃‍♂️ 启动服务

有两种启动方式：

### 方式1：从项目根目录启动（推荐）
```bash
python src/main.py
```

### 方式2：从src目录启动
```bash
cd src
python main.py
```

你应该看到类似这样的输出：

```
╭────────────── Claude Code Provider Balancer Configuration ──────────────╮
│    Version       : v0.3.0                                               │
│    Providers     : 3/3 healthy                                          │
│    [✓] anthropic_official (anthropic): https://api.anthropic.com        │
│    [✓] custom_claude_provider (anthropic): https://your-provider.com    │
│    [✓] openrouter_backup (openai): https://openrouter.ai/api/v1         │
│    Log Level     : INFO                                                  │
│    Listening on  : http://127.0.0.1:8080                                │
╰─────────────────────────────────────────────────────────────────────────╯
```

## 🔧 配置 Claude Code

设置环境变量让 Claude Code 使用你的负载均衡器：

```bash
export ANTHROPIC_BASE_URL=http://localhost:8080
claude
```

或者临时使用：

```bash
ANTHROPIC_BASE_URL=http://localhost:8080 claude
```

> 💡 **提示**: 配置文件会自动从项目根目录的 `providers.yaml` 加载，无论你从哪个目录启动服务。

## ✅ 验证安装

### 1. 检查服务状态
```bash
curl http://localhost:8080/
```

### 2. 查看提供商状态
```bash
curl http://localhost:8080/providers
```

### 3. 运行完整测试
```bash
python test_api.py
```

### 4. 测试 Claude Code
```bash
# 在另一个终端中
ANTHROPIC_BASE_URL=http://localhost:8080 claude

# 在 Claude Code 中输入
/? Hello, test message
```

## 🔄 负载均衡行为

系统的工作方式：

1. **正常情况**：始终使用第一个健康的提供商
2. **故障发生**：自动切换到下一个健康的提供商
3. **冷却期**：故障的提供商在60秒内不会被重新使用
4. **自动恢复**：冷却期过后，故障的提供商会重新加入轮询
5. **全部故障**：如果所有提供商都不可用，返回503错误

## 🚀 透传模式 (Passthrough Mode)

透传模式允许直接转发客户端请求的模型名称到后端服务商，而不进行模型名称的转换。

### 配置透传模式
```yaml
providers:
  - name: "passthrough_provider"
    big_model: "passthrough"     # 透传大模型请求
    small_model: "passthrough"   # 透传小模型请求
    # 或者只透传其中一种：
    # big_model: "passthrough"
    # small_model: "claude-3-5-haiku-20241022"
```

### 透传模式的行为
- **完全透传**：`big_model` 和 `small_model` 都设为 `"passthrough"`
  - 客户端请求 `claude-3-5-sonnet-20241022` → 转发 `claude-3-5-sonnet-20241022`
  - 客户端请求 `custom-model-name` → 转发 `custom-model-name`

- **部分透传**：只设置其中一个为 `"passthrough"`
  - 大模型请求透传，小模型使用固定配置
  - 或相反

### 使用场景
- 后端服务商支持多种模型，希望客户端直接指定模型
- 测试环境中需要灵活的模型选择
- 与后端服务商的模型名称保持完全一致

> 💡 **注意**：透传模式不影响负载均衡逻辑，系统仍会在多个provider之间轮换。

## 🛠 常用操作

### 重新加载配置（无需重启）
```bash
curl -X POST http://localhost:8080/providers/reload
```

### 查看详细日志
```bash
tail -f logs/balancer.jsonl | jq .
```

### 修改日志级别
在 `providers.yaml` 中设置：
```yaml
settings:
  log_level: "DEBUG"  # INFO, WARNING, ERROR, DEBUG
```

## 🐛 故障排除

### 问题1：提供商显示不健康
```bash
# 检查提供商状态
curl http://localhost:8080/providers

# 查看详细错误日志
tail -f logs/balancer.jsonl | grep ERROR
```

### 问题2：Claude Code 连接失败
```bash
# 确认服务正在运行
curl http://localhost:8080/

# 检查环境变量
echo $ANTHROPIC_BASE_URL

# 验证网络连接
curl -X POST http://localhost:8080/v1/messages/count_tokens \
  -H "Content-Type: application/json" \
  -d '{"model":"claude-3-5-haiku-20241022","messages":[{"role":"user","content":"test"}]}'
```

### 问题3：所有提供商都故障
1. 检查 API 密钥是否正确
2. 验证网络连接
3. 查看提供商的服务状态
4. 检查冷却时间设置

## 📊 监控和管理

### API 端点
- `GET /` - 健康检查
- `GET /providers` - 提供商状态
- `POST /providers/reload` - 重新加载配置
- `POST /v1/messages` - 主要的消息端点
- `POST /v1/messages/count_tokens` - 令牌计数

### 配置热重载
修改 `providers.yaml` 后：
```bash
curl -X POST http://localhost:8080/providers/reload
```

## 🎯 下一步

1. **生产部署**：考虑使用 Docker 或 systemd
2. **监控集成**：添加 Prometheus 指标
3. **安全加固**：配置 HTTPS 和认证
4. **扩展配置**：添加更多提供商和自定义规则

## 💡 提示

- 建议至少配置2个不同的提供商以确保高可用性
- 定期检查提供商的健康状态和账户余额
- 使用不同类型的提供商（Anthropic + OpenAI兼容）作为备份
- 根据使用情况调整冷却时间和超时设置
- 使用透传模式时，确保后端服务商支持客户端请求的模型名称
- 可以查看 `docs/passthrough-mode.md` 了解透传模式的详细说明

---

需要帮助？查看 [README.md](README.md) 获取更详细的文档，或运行 `python test_api.py` 进行完整的功能测试。