# Claude Code Provider Balancer

基于 FastAPI 的智能代理服务，为多个 Claude Code 提供商和 OpenAI 兼容服务提供负载均衡和故障转移功能。通过智能路由和健康监控，确保 Claude Code CLI 的高可用性和最佳性能。

![Claude Balancer](docs/cover.png)

## 核心特性

### 🚀 多提供商支持
- **Anthropic API** - 原生 Claude API 支持
- **OpenAI 兼容** - 支持 OpenRouter、Together AI 等服务  
- **灵活配置** - 支持自定义提供商和端点

### ⚡ 智能负载均衡
- **多种策略** - 优先级、轮询、随机选择
- **自动故障转移** - 提供商故障时无缝切换
- **健康监控** - 实时跟踪提供商状态，可配置冷却期

### 🔐 灵活认证
- **API Key** - 标准 X-API-Key 头认证
- **Bearer Token** - Authorization Bearer 认证
- **环境变量** - 支持从环境变量读取认证信息

### 🎯 智能路由
- **模式匹配** - 基于模型名称的 glob 模式路由
- **模型映射** - 将 Claude 模型映射到提供商特定模型
- **透传模式** - 支持原始模型名称透传

### 📊 监控与缓存
- **请求去重** - 基于内容哈希的智能去重
- **响应缓存** - 提高响应速度，减少重复请求
- **结构化日志** - JSON 格式日志，支持彩色控制台输出
- **性能指标** - 请求时间和成功率统计

### 🔧 开发友好
- **热配置重载** - 无需重启即可重新加载配置
- **流式响应** - 完整支持流式和非流式响应
- **错误处理** - 统一的错误格式和传播机制

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
cp config.example.yaml config.yaml
```

2. 编辑 `config.yaml` 添加你的提供商配置：

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

  - name: "Together"
    type: "openai"
    base_url: "https://api.together.xyz/v1"
    auth_type: "api_key"
    auth_value: "${TOGETHER_API_KEY}"  # 从环境变量读取
    enabled: true

model_routes:
  "*sonnet*":
    - provider: "GAC"
      model: "passthrough"  # 使用原始模型名
      priority: 1
    - provider: "OpenRouter"
      model: "anthropic/claude-3.5-sonnet"
      priority: 2

  "*haiku*":
    - provider: "Together"
      model: "meta-llama/Meta-Llama-3.1-405B-Instruct-Turbo"
      priority: 1
    - provider: "GAC"
      model: "passthrough"
      priority: 2

# 系统配置
settings:
  cooldown_seconds: 90        # 提供商故障冷却时间
  timeout_seconds: 300        # 请求超时时间
  log_level: "INFO"           # 日志级别
  max_cache_size: 1000        # 缓存最大条目数
```

### 启动服务

```bash
# 开发模式（推荐）
python src/main.py

# 或者使用 uv
uv run src/main.py

# 生产模式
uvicorn src.main:app --host 0.0.0.0 --port 9090
```

### 配置 Claude Code

```bash
# 设置环境变量
export ANTHROPIC_BASE_URL=http://localhost:9090
claude

# 或临时使用
ANTHROPIC_BASE_URL=http://localhost:9090 claude
```

## 使用示例

### 基本 API 调用

```bash
# 发送消息请求
curl -X POST http://localhost:9090/v1/messages \
  -H "Content-Type: application/json" \
  -H "anthropic-version: 2023-06-01" \
  -d '{
    "model": "claude-3-5-sonnet-20241022",
    "messages": [{"role": "user", "content": "你好，请介绍一下你自己"}],
    "max_tokens": 100
  }'

# 流式响应
curl -X POST http://localhost:9090/v1/messages \
  -H "Content-Type: application/json" \
  -H "anthropic-version: 2023-06-01" \
  -d '{
    "model": "claude-3-5-sonnet-20241022", 
    "messages": [{"role": "user", "content": "写一首关于春天的诗"}],
    "max_tokens": 200,
    "stream": true
  }'

# 计算 token 数量
curl -X POST http://localhost:9090/v1/messages/count_tokens \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-3-5-haiku-20241022",
    "messages": [{"role": "user", "content": "计算这段文本的 token 数量"}]
  }'
```

### 管理端点

```bash
# 检查提供商状态
curl http://localhost:9090/providers

# 重新加载配置（热重载）
curl -X POST http://localhost:9090/providers/reload

# 检查服务健康状态
curl http://localhost:9090/health
```

## 项目架构

### 目录结构

```
claude-code-provider-balancer/
├── src/                           # 主要源代码
│   ├── main.py                   # FastAPI 应用入口点
│   ├── provider_manager.py       # 提供商管理和路由逻辑
│   ├── models/                   # Pydantic 数据模型
│   │   ├── __init__.py
│   │   ├── base.py              # 基础模型定义
│   │   ├── anthropic_models.py  # Anthropic API 模型
│   │   ├── openai_models.py     # OpenAI API 模型
│   │   └── error_models.py      # 错误响应模型
│   ├── conversion/              # API 格式转换
│   │   ├── __init__.py
│   │   ├── anthropic_to_openai.py
│   │   ├── openai_to_anthropic.py
│   │   └── token_counting.py    # Token 计数逻辑
│   ├── caching/                 # 请求缓存和去重
│   │   ├── __init__.py
│   │   ├── request_signature.py  # 请求签名生成
│   │   ├── response_cache.py     # 响应缓存管理
│   │   └── deduplication.py     # 请求去重逻辑
│   └── log_utils/               # 日志工具
│       ├── __init__.py
│       ├── colored_logger.py    # 彩色控制台日志
│       └── json_logger.py       # JSON 格式日志
├── tests/                       # 测试套件
│   ├── test_provider_routing.py
│   ├── test_stream_nonstream.py
│   ├── test_caching_deduplication.py
│   ├── test_error_handling.py
│   ├── test_passthrough.py
│   ├── test_log_colors.py
│   └── run_all_tests.py
├── logs/                        # 日志文件目录
├── config.yaml                  # 主配置文件
├── config.example.yaml          # 配置文件模板
├── requirements.txt             # Python 依赖
├── pyproject.toml              # 项目配置
└── README.md                   # 项目文档
```

### 核心组件

#### 1. 请求处理流程 (`src/main.py`)
- 接收并验证 HTTP 请求
- 处理 Anthropic 和 OpenAI 格式的请求
- 管理流式和非流式响应
- 统一错误处理和日志记录

#### 2. 提供商管理 (`src/provider_manager.py`)
- 健康监控和故障检测
- 智能路由和负载均衡
- 配置热重载
- 认证和代理支持

#### 3. 格式转换 (`src/conversion/`)
- Anthropic ↔ OpenAI API 格式互转
- 工具调用格式转换
- Token 计数和计费
- 错误格式标准化

#### 4. 缓存系统 (`src/caching/`)
- 基于内容哈希的请求去重
- 智能响应缓存
- 并发请求处理
- 缓存质量验证

## 开发指南

### 运行测试

```bash
# 运行所有测试
python -m pytest tests/ -v

# 运行特定测试文件
python tests/test_provider_routing.py

# 运行单个测试函数
python -m pytest tests/test_provider_routing.py::TestProviderRouting::test_basic_routing -v

# 使用自定义测试运行器
python tests/run_all_tests.py
```

### 代码质量检查

```bash
# 代码格式化
ruff format src/ tests/

# 代码检查
ruff check src/ tests/

# 类型检查（如果配置了 mypy）
mypy src/
```

## API 参考

### 核心端点

| 端点 | 方法 | 描述 |
|------|------|------|
| `/v1/messages` | POST | 发送消息请求 |
| `/v1/messages/count_tokens` | POST | 计算消息 token 数量 |
| `/providers` | GET | 查看提供商状态 |
| `/providers/reload` | POST | 热重载配置 |
| `/health` | GET | 服务健康检查 |

### 请求格式

支持标准的 Anthropic Messages API 格式：

```json
{
  "model": "claude-3-5-sonnet-20241022",
  "messages": [
    {"role": "user", "content": "Hello, Claude!"}
  ],
  "max_tokens": 100,
  "stream": false,
  "temperature": 0.7
}
```

## 故障排除

### 常见问题解决

#### 🔴 提供商显示不健康

**症状**: 提供商状态显示为 "unhealthy" 或持续故障

```bash
# 1. 检查提供商状态
curl http://localhost:9090/providers

# 2. 查看详细日志
tail -f logs/logs.jsonl | jq '.'

# 3. 测试提供商连接
curl -v https://your-provider-url/health

# 4. 检查认证配置
grep -A 5 "auth_value" config.yaml
```

**可能原因**:
- API 密钥过期或无效
- 提供商服务临时不可用
- 网络连接问题
- 配置文件语法错误

#### 🔴 Claude Code CLI 连接失败

**症状**: Claude Code CLI 无法连接到代理服务

```bash
# 1. 检查代理服务状态
curl http://localhost:9090/health

# 2. 验证环境变量
echo $ANTHROPIC_BASE_URL

# 3. 测试基本连接
curl -X POST http://localhost:9090/v1/messages \
  -H "Content-Type: application/json" \
  -d '{"model":"claude-3-5-haiku-20241022","messages":[{"role":"user","content":"test"}],"max_tokens":10}'
```

**解决步骤**:
- 确保服务在正确端口运行 (默认 9090)
- 检查防火墙设置
- 验证 ANTHROPIC_BASE_URL 格式: `http://localhost:9090`

#### 🔴 配置热重载失败

**症状**: 修改配置后未生效

```bash
# 1. 手动触发重载
curl -X POST http://localhost:9090/providers/reload

# 2. 检查配置文件语法
python -c "import yaml; print(yaml.safe_load(open('config.yaml')))"

# 3. 查看重载日志
grep "reload" logs/logs.jsonl
```

#### 🔴 流式响应中断

**症状**: 流式响应突然停止或出现错误

```bash
# 检查超时设置
grep "timeout" config.yaml

# 测试非流式请求
curl -X POST http://localhost:9090/v1/messages \
  -H "Content-Type: application/json" \
  -d '{"model":"claude-3-5-sonnet-20241022","messages":[{"role":"user","content":"简短回复"}],"max_tokens":50,"stream":false}'
```

### 性能优化建议

#### 1. 缓存配置优化

```yaml
settings:
  max_cache_size: 2000          # 增加缓存大小
  cache_ttl_seconds: 3600       # 设置缓存过期时间
```

#### 2. 并发请求处理

```bash
# 增加 uvicorn worker 数量
uvicorn src.main:app --workers 4 --host 0.0.0.0 --port 9090
```

#### 3. 日志级别调整

```yaml
settings:
  log_level: "WARNING"  # 生产环境建议使用 WARNING 或 ERROR
```

### 监控和维护

#### 查看系统状态

```bash
# 提供商健康状态
curl http://localhost:9090/providers | jq '.[] | {name: .name, healthy: .healthy, last_error: .last_error}'

# 系统健康检查
curl http://localhost:9090/health

# 实时日志监控
tail -f logs/logs.jsonl | jq 'select(.level == "ERROR")'
```

#### 性能指标

日志中包含详细的性能指标：
- 请求处理时间
- 提供商响应时间
- 缓存命中率
- 错误率统计

```bash
# 查看性能统计
grep "response_time" logs/logs.jsonl | tail -10 | jq '.response_time'
```

## 贡献指南

### 开发环境设置

```bash
# 1. 克隆仓库
git clone <repository-url>
cd claude-code-provider-balancer

# 2. 安装开发依赖
uv sync --dev

# 3. 设置预提交钩子
pre-commit install

# 4. 运行测试确保环境正常
python tests/run_all_tests.py
```

### 提交代码

```bash
# 格式化代码
ruff format src/ tests/

# 检查代码质量
ruff check src/ tests/

# 运行测试
python -m pytest tests/ -v

# 提交更改
git add .
git commit -m "feat: add new feature"
```

## 许可证

MIT License - 详见 [LICENSE](./LICENSE) 文件
