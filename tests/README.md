# 测试套件文档

这个目录包含了 Claude Code Provider Balancer 的完整测试套件，涵盖了系统的所有核心功能和边缘情况。

## 🧪 测试文件概览

### 核心功能测试
1. **`test_stream_nonstream.py`** - 流式和非流式请求测试
   - 基础响应格式验证
   - 流式数据块处理
   - 早期终止处理
   - 内容一致性验证

2. **`test_provider_routing.py`** - 服务商路由和选择测试
   - 服务商状态检查
   - 模型路由规则
   - 负载均衡行为
   - 优先级处理

3. **`test_provider_failover.py`** - 故障转移和恢复测试
   - 健康监控机制
   - 自动故障转移
   - 冷却时间处理
   - 并发故障恢复

4. **`test_timeout_retry.py`** - 超时和重试机制测试
   - 各种超时场景
   - 重试逻辑验证
   - 并发超时处理
   - 部分响应处理

5. **`test_client_disconnect.py`** - 客户端断开连接测试
   - 早期断开处理
   - 中途断开恢复
   - 并发断开处理
   - 服务器稳定性

6. **`test_caching_deduplication.py`** - 缓存和去重功能测试
   - 请求去重逻辑
   - 缓存命中率
   - 缓存过期处理
   - 并发缓存行为

### OAuth认证测试
7. **`test_oauth.py`** - OAuth 2.0 认证功能测试
   - OAuth状态端点验证
   - 真实OAuth授权流程触发
   - 授权码交换测试
   - Token管理端点测试
   - Memory模式认证验证
   - 使用OAuth token的真实请求测试

### 扩展功能测试  
8. **`test_error_handling.py`** - 错误处理和边缘情况测试
   - 无效请求处理
   - 特殊字符支持
   - 极端参数值
   - 系统健壮性

### 工具文件
- **`run_all_tests.py`** - 测试运行器，支持批量执行和报告生成

## 🚀 快速开始

### 前提条件
1. 确保服务器正在运行：
   ```bash
   # 在项目根目录
   python src/main.py
   ```

2. 安装依赖（如果还没有）：
   ```bash
   pip install requests
   ```

### 运行所有测试
```bash
# 在项目根目录或tests目录
python tests/run_all_tests.py
```

### 运行单个测试文件
```bash
# 运行特定测试
python tests/test_stream_nonstream.py
python tests/test_provider_routing.py
python tests/test_oauth.py
python tests/test_caching_deduplication.py
```

### 运行部分测试
```bash
# 只运行核心功能测试
python tests/run_all_tests.py --tests test_stream_nonstream.py test_provider_routing.py

# 只运行OAuth相关测试
python tests/run_all_tests.py --tests test_oauth.py

# 列出所有可用测试
python tests/run_all_tests.py --list

# 检查服务器状态
python tests/run_all_tests.py --check-server
```

### OAuth测试特殊说明

OAuth测试包含交互式和自动化测试：

1. **自动化测试** - 验证端点和基础功能
2. **交互式测试** - 需要真实OAuth授权

#### 完整OAuth测试流程
```bash
# 1. 运行OAuth测试（会触发401错误）
python tests/test_oauth.py

# 2. 复制console中显示的OAuth授权URL，在浏览器中完成授权

# 3. 从callback URL中复制授权码，设置环境变量
export OAUTH_TEST_CODE="your_authorization_code_here"

# 4. 重新运行测试以测试token交换
python tests/test_oauth.py

# 5. 测试使用真实token发送请求
python tests/test_oauth.py
```

## 📊 测试报告

测试运行器会生成详细的测试报告，包括：

- ✅ **通过/失败统计**
- ⏱️ **执行时间分析** 
- 🔍 **失败测试详情**
- 📈 **成功率计算**
- ⚡ **性能统计**

示例输出：
```
📊 测试报告
============================================================
总测试数: 7
✅ 通过: 6
❌ 失败: 1
⏭️ 跳过: 0
⏰ 超时: 0
💥 错误: 0
⏱️ 总耗时: 45.32秒
📈 成功率: 85.7%
```

## 🎯 测试覆盖范围

### 功能覆盖
- [x] **基础API功能** - 请求/响应处理
- [x] **流式处理** - SSE流式响应
- [x] **服务商管理** - 路由、负载均衡、故障转移
- [x] **OAuth认证** - 自动授权流程、token管理、多账号轮换
- [x] **缓存系统** - 去重、缓存命中、过期处理
- [x] **错误处理** - 异常情况、边缘情况
- [x] **网络处理** - 超时、重试、断开连接
- [x] **并发处理** - 多线程、竞争条件

### 场景覆盖
- [x] **正常使用场景** - 标准API调用
- [x] **异常场景** - 服务商故障、网络问题
- [x] **边缘情况** - 极端参数、特殊字符
- [x] **压力情况** - 并发请求、长时间运行
- [x] **恢复场景** - 故障后恢复、缓存清理

### 数据覆盖
- [x] **有效数据** - 标准模型、正常消息
- [x] **无效数据** - 错误格式、缺失字段
- [x] **边界数据** - 极大/极小值、空值
- [x] **特殊数据** - Unicode、表情符号、转义字符

## 🔧 自定义测试

### 添加新测试
1. 创建新的测试文件：`test_your_feature.py`
2. 继承或模仿现有测试的结构
3. 实现 `run_all_tests()` 方法
4. 添加到 `run_all_tests.py` 的 `TEST_FILES` 列表

### 测试文件模板
```python
#!/usr/bin/env python3
"""
测试 [功能名称]
"""

import requests
import sys
import os

BASE_URL = "http://localhost:9090"

class TestYourFeature:
    def __init__(self):
        self.base_url = BASE_URL
        self.headers = {"Content-Type": "application/json"}
    
    def test_your_specific_case(self):
        """测试具体场景"""
        print("测试: 具体场景描述")
        
        try:
            # 测试逻辑
            assert True, "测试条件"
            print("✅ 测试通过")
            return True
        except Exception as e:
            print(f"❌ 测试失败: {e}")
            return False
    
    def run_all_tests(self):
        """运行所有测试"""
        tests = [self.test_your_specific_case]
        passed = sum(1 for test in tests if test())
        return passed == len(tests)

def main():
    tester = TestYourFeature()
    return tester.run_all_tests()

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
```

## 🐛 故障排除

### 常见问题

1. **服务器未运行**
   ```
   ❌ 无法连接到服务器
   ```
   **解决方案**: 先启动服务器 `python src/main.py`

2. **测试超时**
   ```
   ⏰ 测试超时
   ```
   **解决方案**: 检查网络连接或增加超时时间

3. **缓存相关测试失败**
   ```
   ℹ️ 缓存功能可能未启用
   ```
   **解决方案**: 检查 `providers.yaml` 中的缓存配置

4. **服务商相关测试失败**
   ```
   ⚠️ 只有一个可用服务商
   ```
   **解决方案**: 在 `providers.yaml` 中配置多个服务商

### 调试模式
```bash
# 启用详细输出
python tests/test_stream_nonstream.py -v

# 运行单个测试函数（需要修改代码）
# 在测试文件中添加调试代码
```

## 📝 测试编写最佳实践

1. **测试独立性** - 每个测试应该能独立运行
2. **清晰命名** - 测试名称应该描述测试的具体场景
3. **完整验证** - 验证响应状态码、内容格式和业务逻辑
4. **错误处理** - 测试应该能优雅处理异常情况
5. **性能考虑** - 避免不必要的等待时间
6. **文档化** - 为复杂测试添加注释说明

## 📚 相关文档

- [项目README](../README.md) - 项目整体介绍
- [配置指南](../providers.example.yaml) - 服务商配置示例
- [API文档](../docs/) - API接口说明

## 🤝 贡献指南

1. 添加新功能时，请同时添加对应的测试
2. 修改现有功能时，请更新相关测试
3. 确保所有测试在提交前都能通过
4. 为复杂测试添加适当的文档说明

---

**注意**: 这些测试依赖于实际的服务器运行状态，请确保在运行测试前已正确配置并启动了 Claude Code Provider Balancer 服务。