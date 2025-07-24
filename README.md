# Claude Code Provider Balancer

基于 FastAPI 的智能代理服务，为多个 Claude Code 提供商和 OpenAI 兼容服务提供负载均衡和故障转移功能。

![Claude Balancer](docs/cover.png)

## 核心特性

- **🚀 多提供商支持** - 支持 Anthropic API、OpenAI 兼容服务
- **⚡ 智能负载均衡** - 自动故障转移、健康监控
- **🔐 OAuth 认证** - 支持 Claude Code 官方 OAuth 2.0 认证
- **🎯 智能路由** - 基于模型名称的路由策略
- **📊 请求去重** - 智能缓存，减少重复请求
- **🔧 热配置重载** - 无需重启即可更新配置

## 快速开始

### 1. 安装依赖

```bash
# 推荐使用 uv
uv sync

# 或使用 pip
pip install -r requirements.txt
```

### 2. 配置服务

```bash
# 复制配置文件
cp config.example.yaml config.yaml

# 编辑配置文件，添加你的 API 密钥
vim config.yaml
```

### 3. 启动服务

```bash
# 开发模式
python src/main.py

# 生产模式
uvicorn src.main:app --host 0.0.0.0 --port 9090
```

### 4. 配置 Claude Code

```bash
export ANTHROPIC_BASE_URL=http://localhost:9090
claude
```


## 核心功能

### 多提供商负载均衡

- 支持多个 Claude Code 服务商
- 自动故障转移和健康检测
- 基于优先级的智能路由

### OAuth 2.0 认证

- 支持 Claude Code 官方 OAuth 认证
- 自动 token 刷新和持久化
- 无缝认证体验

### 请求缓存和去重

- 基于请求内容的智能去重
- 响应缓存提升性能
- 并发请求合并处理

### API 兼容性

- 完整的 Anthropic Messages API 支持
- OpenAI 格式自动转换
- 流式和非流式响应

## 主要端点

| 端点 | 方法 | 描述 |
|------|------|------|
| `/v1/messages` | POST | 发送消息请求 |
| `/v1/messages/count_tokens` | POST | 计算 token 数量 |
| `/providers` | GET | 查看提供商状态 |
| `/providers/reload` | POST | 重新加载配置 |
| `/oauth/status` | GET | OAuth 状态检查 |
| `/health` | GET | 服务健康检查 |

## 开发和测试

```bash
# 运行测试
python tests/run_tests.py

# 代码格式化
ruff format src/ tests/

# 代码检查
ruff check src/ tests/
```

## 故障排除

### 常见问题

1. **提供商连接失败** - 检查 API 密钥和网络连接
2. **配置不生效** - 使用 `/providers/reload` 手动重载
3. **OAuth 认证问题** - 检查 `/oauth/status` 和配置

### 监控

```bash
# 查看提供商状态
curl http://localhost:9090/providers

# 查看日志
tail -f logs/logs.jsonl | jq '.'
```

## 技术特性

- **模块化架构** - 清晰的代码组织和职责分离
- **异步处理** - 基于 asyncio 的高性能并发
- **类型安全** - 完整的 Pydantic 模型验证
- **可观测性** - 结构化日志和性能监控
- **高可用性** - 自动故障转移和健康检测

## 许可证

MIT License - 详见 [LICENSE](./LICENSE) 文件
