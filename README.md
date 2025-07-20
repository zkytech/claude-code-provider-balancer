# Claude Code Provider Balancer

一个支持多个 Claude Code 服务商和 OpenAI 兼容服务的负载均衡代理服务，具有自动故障转移和重试机制。

![Claude Proxy Logo](docs/cover.png)

## 概述

Claude Code Provider Balancer 为多个 Claude Code 服务商和 OpenAI 兼容服务提供智能负载均衡和故障转移。当某个服务商不可用时，它会无缝切换到其他服务商，确保您的 Claude Code 应用程序的高可用性。

主要特性：

- **多服务商支持**：支持 Anthropic API 兼容、OpenAI 兼容和计划中的 Zed 服务商
- **智能负载均衡**：优先级、轮询和随机选择策略
- **自动故障转移**：当故障发生时自动切换到健康的服务商
- **健康监控**：跟踪服务商状态，支持可配置的冷却时间
- **双重认证**：支持 `api_key` 和 `auth_token` 认证方式
- **动态模型路由**：Claude 模型与服务商特定模型的映射和透传支持
- **热配置重载**：无需重启即可重新加载服务商配置
- **全面日志记录**：详细的请求/响应跟踪，支持彩色输出
- **Token 计数**：内置 token 估算功能
- **流式支持**：完全支持流式响应，包含错误处理
- **请求去重**：智能缓存防止重复请求
- **模块化架构**：缓存、转换、模型验证等功能独立组织
- **透传模式**：直接将模型名称转发给后端服务商

## 示例

**模型**: `deepseek/deepseek-chat-v3-0324`

![Claude Proxy Example](docs/example.png)

## 🚀 快速开始

### 1. 安装

#### 前置要求
- Python 3.10+
- 您选择的服务商的 API 密钥
- [uv](https://github.com/astral-sh/uv) (推荐) 或 pip

#### 克隆并安装
```bash
# 克隆项目
git clone <repository-url>
cd claude-code-provider-balancer

# 安装依赖
uv sync
# 或使用 pip:
pip install -r requirements.txt
```

### 2. 配置

复制示例配置并编辑：

```bash
# 复制配置模板
cp providers.example.yaml providers.yaml

# 编辑配置文件
vim providers.yaml  # 或使用您喜欢的编辑器
```

系统使用 YAML 配置文件 (`providers.yaml`) 来管理多个服务商：

```yaml
providers:
  # Claude Code 官方 API
  - name: "Claude Code Official"
    type: "anthropic"
    base_url: "https://api.anthropic.com"
    auth_type: "api_key"
    auth_value: "sk-ant-your-actual-key-here"
    enabled: true

  # 使用 auth_token 的 Claude Code 服务商
  - name: "GAC"
    type: "anthropic"
    base_url: "https://gaccode.com/claudecode"
    auth_type: "api_key"
    auth_value: "your-api-key-here"
    enabled: true

  # 另一个 Claude Code 服务商
  - name: "AnyRouter"
    type: "anthropic"
    base_url: "https://anyrouter.top"
    auth_type: "auth_token"
    auth_value: "your-auth-token-here"
    enabled: true

  # OpenRouter 作为备用
  - name: "OpenRouter"
    type: "openai"
    base_url: "https://openrouter.ai/api/v1"
    auth_type: "api_key"
    auth_value: "sk-or-your-openrouter-key"
    enabled: true

# 模型路由配置
model_routes:
  # 大模型路由
  "*sonnet*":
    - provider: "GAC"
      model: "passthrough"
      priority: 1
    - provider: "Claude Code Official"
      model: "passthrough"
      priority: 2
    - provider: "OpenRouter"
      model: "google/gemini-2.5-pro"
      priority: 3

  # 小模型路由
  "*haiku*":
    - provider: "GAC"
      model: "passthrough"
      priority: 1
    - provider: "OpenRouter"
      model: "anthropic/claude-3.5-haiku"
      priority: 2

settings:
  failure_cooldown: 90    # 失败服务商的冷却时间（秒）
  request_timeout: 40     # 请求超时时间（秒）
  log_level: "INFO"       # 日志级别
  log_color: true         # 启用彩色控制台输出
  host: "127.0.0.1"       # 服务器地址
  port: 8080              # 服务器端口
```

#### 认证类型

- **`api_key`**: 标准 API 密钥认证（适用于 Anthropic 官方 API 和 OpenAI 兼容服务）
- **`auth_token`**: Bearer token 认证（适用于某些 Claude Code 服务商）

#### 服务商类型

- **`anthropic`**: 直接的 Anthropic API 兼容服务商
- **`openai`**: OpenAI 兼容服务商（请求会从 Anthropic 格式转换为 OpenAI 格式）
- **`zed`**: 计划支持的 Zed 服务商（基于会话的计费模式）

## 🏗️ 系统架构

### 核心组件

```
src/
├── main.py                 # FastAPI 主应用和请求处理
├── provider_manager.py     # 服务商管理和路由逻辑
├── caching/               # 请求去重和缓存模块
│   ├── deduplication.py   # 请求去重逻辑
│   └── cache_serving.py   # 缓存服务功能
├── conversion/            # 协议转换模块
│   ├── token_counting.py  # Token 计数功能
│   └── format_conversion.py # 请求/响应格式转换
├── models/                # Pydantic 数据模型
│   ├── requests.py        # 请求模型定义
│   ├── responses.py       # 响应模型定义
│   └── errors.py          # 错误处理模型
└── log_utils/             # 日志处理模块
    ├── formatters.py      # 日志格式化器
    └── handlers.py        # 日志处理器
```

### 关键技术栈

- **FastAPI** - Web 框架和 API 端点
- **Pydantic** - 数据验证和序列化
- **httpx** - HTTP 客户端
- **OpenAI SDK** - OpenAI 兼容服务商交互
- **PyYAML** - 配置文件解析
- **Rich** - 终端输出格式化
- **Uvicorn** - ASGI 服务器

### 3. 启动服务器

有两种启动服务器的方式：

#### 选项 1：从项目根目录启动（推荐）
```bash
python src/main.py
```

#### 选项 2：从 src 目录启动
```bash
cd src
python main.py
```

您应该看到类似的输出：

```
╭────────────── Claude Code Provider Balancer Configuration ──────────────╮
│    Version       : v0.5.0                                               │
│    Providers     : 3/3 healthy                                          │
│    [✓] GAC (anthropic): https://gaccode.com/claudecode                  │
│    [✓] AnyRouter (anthropic): https://anyrouter.top                     │
│    [✓] OpenRouter (openai): https://openrouter.ai/api/v1                │
│    Log Level     : INFO                                                  │
│    Listening on  : http://127.0.0.1:8080                                │
╰─────────────────────────────────────────────────────────────────────────╯
```

### 4. 配置 Claude Code

将 Claude Code 指向您的负载均衡器：

```bash
# 设置环境变量
export ANTHROPIC_BASE_URL=http://localhost:8080
claude

# 或临时使用
ANTHROPIC_BASE_URL=http://localhost:8080 claude
```

> 💡 **提示**：配置文件会自动从项目根目录的 `providers.yaml` 加载，无论您从哪个目录启动服务。

### 5. 验证安装

#### 检查服务状态
```bash
curl http://localhost:8080/
```

#### 查看服务商状态
```bash
curl http://localhost:8080/providers
```

#### 运行完整测试
```bash
python test_api.py
```

#### 测试 Claude Code
```bash
# 在另一个终端中
ANTHROPIC_BASE_URL=http://localhost:8080 claude

# 在 Claude Code 中输入：
/? Hello, test message
```

## 🔄 负载均衡行为

系统工作原理如下：

1. **正常运行**：始终使用第一个健康的服务商
2. **服务商故障**：自动切换到下一个健康的服务商
3. **冷却时间**：失败的服务商会被排除 90 秒（可配置）
4. **自动恢复**：失败的服务商在冷却时间过后重新加入轮询
5. **所有服务商都故障**：当所有服务商都不可用时返回 503 错误

## 🔄 请求去重与缓存

系统提供智能请求去重和缓存功能，显著提升性能和降低成本：

### 主要特性
- **智能去重**：基于请求签名检测重复请求
- **自动缓存**：缓存响应内容，避免重复计算
- **质量验证**：确保缓存响应的完整性和质量
- **流式支持**：支持流式和非流式响应的去重处理

### 工作原理
1. **请求指纹**：为每个请求生成唯一签名
2. **缓存命中**：检查是否存在相同请求的缓存响应
3. **质量检查**：验证缓存响应的完整性
4. **智能服务**：直接返回缓存结果或转发新请求

### 配置缓存
缓存功能默认启用，可通过配置调整：

```yaml
settings:
  enable_deduplication: true    # 启用请求去重（默认：true）
  cache_ttl: 3600              # 缓存存活时间（秒，默认：1小时）
  cache_size_limit: 1000       # 最大缓存条目数（默认：1000）
```

## 🔮 Zed 服务商支持（计划中）

系统架构已为 Zed 服务商集成做好准备，提供基于会话的智能计费模式：

### 计划特性
- **会话计费**：固定费用模式（普通模式 $0.04，加速模式 $0.05）
- **线程管理**：智能线程状态管理和上下文保持
- **模式选择**：普通模式和加速模式的自动选择
- **工具调用限制**：普通模式最多 25 次工具调用
- **上下文窗口**：120k token 上下文支持

### 智能路由策略
- **强制会话模式**：≥3 个工具、≥2000 字符、多文件操作
- **强制 Token 模式**：简单问题、无工具调用
- **关键词评分**：边缘情况的智能判断

### 线程生命周期
- **全局线程状态**：维护单一 `thread_id` 直到错误触发轮换
- **轮换触发器**：上下文窗口 80% 满、TTL 过期、工具调用限制
- **上下文总结**：智能保持对话连续性

> 📋 **状态**：架构已完成设计，实现计划中。详见 `docs/zed-provider-support.md`

## 🚀 透传模式

透传模式允许直接将客户端请求的模型名称转发给后端服务商，无需模型名称转换。

### 配置透传模式
```yaml
model_routes:
  "*sonnet*":
    - provider: "GAC"
      model: "passthrough"  # 透传模式
      priority: 1
    - provider: "OpenRouter"
      model: "google/gemini-2.5-pro"  # 固定模型
      priority: 2
```

### 透传行为
- **完全透传**：`model` 设置为 `"passthrough"`
  - 客户端请求 `claude-3-5-sonnet-20241022` → 转发 `claude-3-5-sonnet-20241022`
  - 客户端请求 `custom-model-name` → 转发 `custom-model-name`

- **部分透传**：某些服务商透传，其他使用固定配置
  - 优先级高的服务商透传，备用服务商使用固定模型

### 使用场景
- 后端服务商支持多种模型，希望客户端直接指定模型
- 测试环境需要灵活的模型选择
- 与后端服务商的模型名称保持完全一致

> 💡 **注意**：透传模式不影响负载均衡逻辑；系统仍会在多个服务商之间轮询。

## 📊 API 端点

- `POST /v1/messages`: 创建消息（主端点，自动选择服务商）
- `POST /v1/messages/count_tokens`: 计算请求的 token 数量
- `GET /`: 健康检查端点
- `GET /providers`: 获取服务商状态和健康信息
- `POST /providers/reload`: 无需重启即可重新加载服务商配置

## 🎛️ 管理操作

### 热重载配置（无需重启）
```bash
curl -X POST http://localhost:8080/providers/reload
```

### 查看详细日志
```bash
tail -f logs/logs.jsonl | jq .
```

### 修改日志级别
在 `providers.yaml` 中：
```yaml
settings:
  log_level: "DEBUG"  # INFO, WARNING, ERROR, DEBUG
```

## 🔧 模型选择

系统使用模型路由配置来映射 Claude 模型请求：

- **大模型**（Opus、Sonnet）：使用 `*sonnet*` 或 `*opus*` 路由
- **小模型**（Haiku）：使用 `*haiku*` 路由
- **未知模型**：默认使用大模型路由，并发出警告
- **优先级**：按照 `priority` 数值从低到高选择服务商

## 🐛 故障排除

### 问题 1：服务商显示为不健康
```bash
# 检查服务商状态
curl http://localhost:8080/providers

# 查看详细错误日志
tail -f logs/logs.jsonl | grep ERROR
```

### 问题 2：Claude Code 连接失败
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

### 问题 3：所有服务商都失败
1. 检查 API 密钥是否正确
2. 验证网络连接
3. 检查服务商服务状态
4. 查看冷却时间设置

## 🎨 彩色日志

负载均衡器支持彩色控制台输出，提供更好的开发体验：

- **DEBUG**：青色
- **INFO**：绿色  
- **WARNING**：黄色
- **ERROR**：红色
- **CRITICAL**：洋红色

颜色会自动为 TTY 终端启用，并可通过配置控制：

```yaml
settings:
  log_color: true  # 启用彩色输出（默认：true）
```

测试颜色功能：

```bash
# 测试日志颜色
python test_log_colors.py

# 测试服务器启动颜色
python test_server_colors.py
```

颜色会在以下情况下自动禁用：
- 非 TTY 环境（管道、重定向）
- 文件日志（保持日志文件整洁）
- 在配置中明确禁用时

## 🧪 测试

系统提供全面的测试套件，涵盖核心功能：

### 运行所有测试
```bash
# 使用 pytest 运行所有测试
python -m pytest tests/

# 或运行特定测试文件
python tests/test_api.py
python tests/test_passthrough.py
python tests/test_log_colors.py
```

### 测试套件结构
```
tests/
├── test_api.py           # API 端点测试
├── test_passthrough.py   # 透传模式测试
├── test_log_colors.py    # 日志颜色测试
├── test_caching.py       # 缓存功能测试（如果存在）
└── test_providers.py     # 服务商管理测试（如果存在）
```

### 手动功能测试
```bash
# 首先启动服务器
python src/main.py

# 在另一个终端中进行功能测试
# 测试基本 API
curl -X POST http://localhost:8080/v1/messages \
  -H "Content-Type: application/json" \
  -d '{"model":"claude-3-5-sonnet-20241022","messages":[{"role":"user","content":"Hello"}],"max_tokens":100}'

# 测试透传模式
curl -X POST http://localhost:8080/v1/messages \
  -H "Content-Type: application/json" \
  -d '{"model":"custom-model-name","messages":[{"role":"user","content":"Test passthrough"}],"max_tokens":50}'

# 测试 Token 计数
curl -X POST http://localhost:8080/v1/messages/count_tokens \
  -H "Content-Type: application/json" \
  -d '{"model":"claude-3-5-haiku-20241022","messages":[{"role":"user","content":"Count my tokens"}]}'
```

## 💡 最佳实践

### 高可用性配置
- 建议配置至少 2-3 个不同的服务商以实现高可用性
- 使用不同类型的服务商（Anthropic + OpenAI 兼容）作为备用
- 定期检查服务商健康状态和账户余额

### 性能优化
- 启用请求去重功能以降低重复请求成本
- 合理配置缓存 TTL 和大小限制
- 根据使用模式调整冷却时间和超时设置

### 模型路由策略
- 使用透传模式时，确保后端服务商支持客户端请求的模型名称
- 为不同模型类型配置合适的优先级和备用服务商
- 考虑服务商的定价和性能特点进行路由配置

### 监控和维护
- 定期查看日志文件了解系统运行状况
- 使用彩色日志输出提升开发体验
- 利用热重载功能动态调整配置无需重启

## 🎯 下一步

1. **生产部署**：考虑使用 Docker 或 systemd
2. **监控集成**：添加 Prometheus 指标
3. **安全加固**：配置 HTTPS 和身份验证
4. **扩展配置**：添加更多服务商和自定义规则

## 许可证

[LICENSE](./LICENSE)
