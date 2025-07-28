# 测试架构简化重构计划

## 背景问题

当前测试架构存在过度复杂的问题：

### 现状分析
- **配置文件过大**: `config-test.yaml` 有 834 行，包含 50+ providers 和 60+ 模型路由
- **Mock Server 复杂**: 需要独立 mock server (localhost:8998) 和几十个专门的 mock endpoints
- **配置与测试分离**: 测试逻辑依赖外部配置，难以理解和维护
- **重复配置多**: 很多相似的测试只是配置不同，导致大量重复代码

### 问题影响
- 新增测试需要同时修改配置文件和测试代码
- 测试逻辑分散在多个文件中，可读性差
- 维护成本高，配置错误难以调试
- 测试场景受限于预定义配置

## 解决方案：动态配置 + 测试工厂模式

### 核心设计思路
```
测试需求 → TestScenario → TestConfigFactory → 动态配置 → 统一Mock Server → 测试执行
```

### 架构分层
1. **Scenario Layer**: 定义测试场景（成功/失败/超时等）
2. **Config Layer**: 动态生成 provider 和路由配置  
3. **Mock Layer**: 统一的 mock server，根据路由规则响应
4. **Test Layer**: 简化的测试代码，配置即代码

## 实现计划

### Phase 1: 核心数据结构 (高优先级)

#### 1.1 创建测试场景数据类
**文件**: `tests/framework/test_scenario.py`

```python
@dataclass
class ProviderConfig:
    """Provider 配置定义"""
    name: str
    behavior: str  # "success", "error", "timeout", "rate_limit", "duplicate_cache"
    response_data: Optional[dict] = None
    delay_ms: int = 0
    priority: int = 1
    error_count: int = 0  # 用于测试 unhealthy 计数

@dataclass
class TestScenario:
    """测试场景定义"""
    name: str
    providers: List[ProviderConfig]
    expected_behavior: str  # "success", "failover", "error", "all_fail"
    model_name: Optional[str] = None
    settings_override: Optional[dict] = None
```

#### 1.2 创建配置工厂类
**文件**: `tests/framework/config_factory.py`

```python
class TestConfigFactory:
    """测试配置动态生成器"""
    
    def __init__(self, mock_server_base: str = "http://localhost:8998"):
        self.mock_server_base = mock_server_base
        
    def create_config(self, scenario: TestScenario) -> dict:
        """根据测试场景动态生成完整配置"""
        
    def create_simple_success_config(self, model_name: str) -> dict:
        """创建简单成功场景配置"""
        
    def create_failover_config(self, model_name: str) -> dict:
        """创建故障转移场景配置"""
        
    def create_duplicate_test_config(self, model_name: str) -> dict:
        """创建重复请求测试配置"""
```

### Phase 2: Mock Server 重构 (高优先级)

#### 2.1 统一Mock路由处理器
**文件**: `tests/framework/unified_mock.py`

```python
@router.post("/mock-provider/{provider_name}/v1/messages")
async def unified_mock_provider(provider_name: str, request: Request):
    """统一的mock provider处理器 - 替代几十个专门的endpoints"""
    
    # 1. 获取当前测试上下文
    test_context = TestContextManager.get_current_context()
    provider_config = test_context.get_provider_config(provider_name)
    
    # 2. 根据配置的behavior生成响应
    return await MockResponseGenerator.generate(
        behavior=provider_config.behavior,
        request_data=await request.json(),
        response_data=provider_config.response_data,
        delay_ms=provider_config.delay_ms
    )
```

#### 2.2 行为驱动响应生成器
**文件**: `tests/framework/response_generator.py`

```python
class MockResponseGenerator:
    """根据行为类型生成对应的 mock 响应"""
    
    @staticmethod
    async def generate(behavior: str, request_data: dict, **kwargs):
        """根据行为类型生成对应响应"""
        match behavior:
            case "success":
                return create_success_response(request_data, kwargs.get('response_data'))
            case "error":
                return create_error_response(500, "Internal Server Error")
            case "timeout":
                await asyncio.sleep(kwargs.get('delay_ms', 5000) / 1000)
            case "rate_limit":
                return create_error_response(429, "Rate Limited")
            case "duplicate_cache":
                return create_deterministic_response(request_data)
```

### Phase 3: 测试环境管理 (高优先级)

#### 3.1 测试上下文管理器
**文件**: `tests/framework/test_context.py`

```python
class TestContextManager:
    """管理测试执行上下文"""
    _current_scenario: Optional[TestScenario] = None
    
    @classmethod
    def set_scenario(cls, scenario: TestScenario):
        cls._current_scenario = scenario
        
    @classmethod  
    def get_current_context(cls) -> TestScenario:
        return cls._current_scenario
        
    @classmethod
    def clear(cls):
        cls._current_scenario = None
```

#### 3.2 测试环境上下文管理器
**文件**: `tests/framework/test_environment.py`

```python
class TestEnvironment:
    """测试环境上下文管理器 - 自动配置生成与清理"""
    
    def __init__(self, scenario: TestScenario, model_name: str = None):
        self.scenario = scenario
        self.model_name = model_name or scenario.model_name or f"test-{uuid4().hex[:8]}"
        self.original_config = None
        
    async def __aenter__(self):
        # 动态生成并应用配置
        config = TestConfigFactory().create_config(self.scenario, self.model_name)
        self.original_config = await self._apply_config(config)
        TestContextManager.set_scenario(self.scenario)
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # 恢复原始配置
        await self._restore_config(self.original_config)
        TestContextManager.clear()
```

### Phase 4: 测试重构示例 (中优先级)

#### 4.1 重构 duplicate request 测试
**文件**: `tests/test_duplicate_request_handling_simplified.py`

重构前（复杂版本）:
```python
# 依赖外部配置 config-test.yaml:491-494
async def test_duplicate_non_streaming_requests(self, async_client, claude_headers):
    test_request = {"model": "duplicate-non-streaming-test", ...}  # 硬编码
```

重构后（简化版本）:
```python
async def test_duplicate_non_streaming_requests(self, async_client, claude_headers):
    # 1. 动态创建测试场景
    scenario = TestScenario(
        name="duplicate_test",
        providers=[ProviderConfig("cache_provider", "duplicate_cache")]
    )
    
    # 2. 使用测试环境自动配置
    async with TestEnvironment(scenario) as env:
        # 3. 执行测试 - 配置自动生效
        response1 = await async_client.post("/v1/messages", 
                                          json={"model": env.model_name, ...})
        response2 = await async_client.post("/v1/messages", 
                                          json={"model": env.model_name, ...})
        
        # 4. 验证缓存效果
        assert response1.json() == response2.json()
```

#### 4.2 重构 failover 测试
```python
async def test_provider_failover(self, async_client, claude_headers):
    scenario = TestScenario(
        name="failover_test",
        providers=[
            ProviderConfig("primary_fail", "error", priority=1),
            ProviderConfig("secondary_success", "success", priority=2)
        ],
        expected_behavior="failover"
    )
    
    async with TestEnvironment(scenario) as env:
        response = await async_client.post("/v1/messages", 
                                         json={"model": env.model_name, ...})
        assert response.status_code == 200
        # 验证使用了 secondary provider
```

### Phase 5: 测试工具和辅助函数 (中优先级)

#### 5.1 常用场景预设
**文件**: `tests/framework/common_scenarios.py`

```python
class CommonScenarios:
    """常用测试场景预设"""
    
    @staticmethod
    def simple_success() -> TestScenario:
        return TestScenario(
            name="simple_success",
            providers=[ProviderConfig("success_provider", "success")]
        )
    
    @staticmethod
    def basic_failover() -> TestScenario:
        return TestScenario(
            name="basic_failover", 
            providers=[
                ProviderConfig("primary_fail", "error", priority=1),
                ProviderConfig("secondary_success", "success", priority=2)
            ]
        )
    
    @staticmethod
    def all_providers_fail() -> TestScenario:
        return TestScenario(
            name="all_fail",
            providers=[
                ProviderConfig("fail1", "error", priority=1),
                ProviderConfig("fail2", "error", priority=2)
            ],
            expected_behavior="all_fail"
        )
```

#### 5.2 测试装饰器
**文件**: `tests/framework/decorators.py`

```python
def with_test_scenario(scenario: TestScenario):
    """测试装饰器 - 自动设置测试环境"""
    def decorator(test_func):
        @wraps(test_func)
        async def wrapper(*args, **kwargs):
            async with TestEnvironment(scenario) as env:
                return await test_func(*args, env=env, **kwargs)
        return wrapper
    return decorator

# 使用示例
@with_test_scenario(CommonScenarios.simple_success())
async def test_simple_success(self, async_client, claude_headers, env):
    response = await async_client.post("/v1/messages", 
                                     json={"model": env.model_name, ...})
    assert response.status_code == 200
```

### Phase 6: 文档和迁移 (低优先级)

#### 6.1 使用文档
**文件**: `tests/SIMPLIFIED_TESTING_GUIDE.md`

包含：
- 新测试架构使用指南
- 常用场景示例
- 从旧测试迁移指南
- 最佳实践

#### 6.2 迁移脚本
**文件**: `tests/migrate_tests.py`

帮助自动将现有测试迁移到新架构

## 实施步骤

### Step 1: 基础框架搭建
1. 创建 `tests/framework/` 目录
2. 实现核心数据结构（TestScenario, ProviderConfig）
3. 实现 TestConfigFactory
4. 创建统一 Mock Server 路由

### Step 2: 环境管理
1. 实现 TestContextManager
2. 实现 TestEnvironment 上下文管理器
3. 集成到现有测试基础设施

### Step 3: 示例重构
1. 选择 1-2 个代表性测试文件进行重构
2. 验证新架构的可行性
3. 性能和稳定性测试

### Step 4: 批量迁移
1. 逐步迁移所有测试文件
2. 保持向后兼容
3. 清理旧配置文件

### Step 5: 优化和文档
1. 性能优化
2. 编写使用文档
3. 培训和推广

## 预期收益

### 开发体验改善
- **配置即代码**: 测试逻辑和配置在同一文件中，易于理解
- **动态配置**: 无需预定义配置，支持任意组合测试场景
- **自包含测试**: 每个测试都是独立的，无外部依赖

### 维护成本降低
- **配置文件简化**: 从 834 行配置减少到按需生成
- **Mock Server 简化**: 从几十个 endpoints 简化到 1 个统一处理器
- **代码重用**: 通用场景可以复用，减少重复代码

### 可扩展性提升
- **灵活配置**: 支持复杂的测试场景组合
- **易于扩展**: 新增行为类型和场景类型很容易
- **向后兼容**: 可以与现有架构并存

## 风险评估

### 潜在风险
1. **迁移复杂度**: 现有测试较多，迁移工作量大
2. **学习成本**: 团队需要学习新的测试编写方式
3. **兼容性问题**: 可能与现有工具链存在冲突

### 风险缓解
1. **渐进式迁移**: 新旧架构并存，逐步迁移
2. **充分文档**: 提供详细的使用指南和示例
3. **向后兼容**: 保持现有测试继续可用

## 成功标准

### 量化指标
- 测试配置代码行数减少 80%
- 新增测试的编写时间减少 50%
- Mock Server endpoints 数量减少 90%

### 质量指标
- 测试代码可读性显著提升
- 测试维护成本显著降低
- 新人上手测试编写更容易

---

**最后更新**: 2025-07-28
**负责人**: Claude Code
**状态**: 规划中