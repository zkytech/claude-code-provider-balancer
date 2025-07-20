# Claude Code Provider Balancer

基于 FastAPI 的智能代理服务，为多个 Claude Code 提供商和 OpenAI 兼容服务提供负载均衡和故障转移功能。

![Claude Balancer](docs/cover.png)

## 主要功能

- **多提供商支持** - 支持 Anthropic API、OpenAI 兼容和 Zed 提供商
- **智能负载均衡** - 基于优先级、轮询和随机选择策略
- **自动故障转移** - 发生故障时无缝切换到健康的提供商
- **健康监控** - 跟踪提供商状态，可配置冷却期
- **双重认证** - 支持 `api_key` 和 `auth_token` 认证方式
- **动态模型路由** - 将 Claude 模型映射到提供商特定模型
- **热配置重载** - 无需重启即可重新加载提供商配置
- **流式响应支持** - 完整支持流式响应和错误处理

## 快速开始

### 安装依赖

```bash
# 使用 uv（推荐）
uv sync

# 或使用 pip
pip install -r requirements.txt
```

### 配置提供商

1. 复制示例配置文件：
```bash
cp providers.example.yaml providers.yaml
```

2. 编辑 `providers.yaml` 添加你的提供商配置：

```yaml
providers:
  - name: "GAC"
    type: "anthropic"
    base_url: "https://gaccode.com/claudecode"
    auth_type: "api_key"
    auth_value: "your-api-key-here"
    enabled: true

  - name: "OpenRouter"
    type: "openai"
    base_url: "https://openrouter.ai/api/v1"
    auth_type: "api_key"
    auth_value: "sk-or-your-key"
    enabled: true

model_routes:
  "*sonnet*":
    - provider: "GAC"
      model: "passthrough"
      priority: 1
    - provider: "OpenRouter"
      model: "google/gemini-2.5-pro"
      priority: 2
```

### 启动服务

```bash
# 开发模式（推荐）
python src/main.py

# 或者使用 uv
uv run src/main.py

# 生产模式
uvicorn src.main:app --host 0.0.0.0 --port 8080
```

### 配置 Claude Code

```bash
# 设置环境变量
export ANTHROPIC_BASE_URL=http://localhost:8080
claude

# 或临时使用
ANTHROPIC_BASE_URL=http://localhost:8080 claude
```

## 基本测试

```bash
# 发送测试请求
curl -X POST http://localhost:8080/v1/messages \
  -H "Content-Type: application/json" \
  -d '{"model":"claude-3-5-sonnet-20241022","messages":[{"role":"user","content":"你好"}],"max_tokens":100}'

# 检查提供商状态
curl http://localhost:8080/providers

# 重新加载配置
curl -X POST http://localhost:8080/providers/reload
```

## 项目结构

```
src/
├── main.py                 # 主应用入口
├── provider_manager.py     # 提供商管理逻辑
├── models/                 # 数据模型
├── conversion/             # API 转换逻辑
├── caching/               # 缓存和去重功能
└── log_utils/             # 日志工具

tests/                     # 测试套件
providers.yaml             # 提供商配置文件
```

## 运行测试

```bash
# 运行所有测试
python -m pytest tests/

# 运行特定测试
python tests/test_api.py
```

## API 端点

- `POST /v1/messages` - 发送消息到 Claude
- `GET /providers` - 查看提供商状态
- `POST /providers/reload` - 重新加载配置

## 常见问题

### 服务商显示不健康

```bash
# 检查状态
curl http://localhost:8080/providers

# 查看日志
tail -f logs/logs.jsonl
```

### Claude Code 连接失败

```bash
# 检查服务
curl http://localhost:8080/

# 验证环境变量
echo $ANTHROPIC_BASE_URL
```

## 许可证

[LICENSE](./LICENSE)
