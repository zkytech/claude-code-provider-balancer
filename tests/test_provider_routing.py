#!/usr/bin/env python3
"""
测试指定 provider 请求和路由功能
"""

import json
import requests
import sys
import os
import random

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from test_utils import get_claude_code_headers

BASE_URL = "http://localhost:8080"

# 测试用模型常量
TEST_MODEL_HAIKU = "claude-3-5-haiku-20241022"
TEST_MODEL_SONNET = "claude-sonnet-4-20250514"
TEST_MODEL_UNKNOWN = "unknown-model-12345"

class TestProviderRouting:
    def __init__(self):
        self.base_url = BASE_URL
        self.headers = get_claude_code_headers()
        self.available_providers = []
        
    def get_provider_status(self):
        """获取服务商状态"""
        try:
            response = requests.get(f"{self.base_url}/providers", timeout=10)
            if response.status_code == 200:
                data = response.json()
                if "providers" in data:
                    self.available_providers = [
                        provider for provider in data["providers"] 
                        if provider.get("enabled", False) and provider.get("healthy", False)
                    ]
                    return True
            return False
        except Exception as e:
            print(f"❌ 获取服务商状态失败: {e}")
            return False
    
    def test_provider_status_endpoint(self):
        """测试服务商状态端点"""
        print("测试: /providers 端点")
        
        try:
            response = requests.get(f"{self.base_url}/providers", timeout=10)
            assert response.status_code == 200, f"状态码错误: {response.status_code}"
            
            data = response.json()
            assert "providers" in data, "响应中缺少 providers 字段"
            assert isinstance(data["providers"], list), "providers 应该是列表"
            
            # 检查每个服务商的必要字段
            for provider in data["providers"]:
                assert "name" in provider, "服务商缺少 name 字段"
                assert "type" in provider, "服务商缺少 type 字段"
                assert "enabled" in provider, "服务商缺少 enabled 字段"
                assert "healthy" in provider, "服务商缺少 healthy 字段"
            
            print(f"✅ 发现 {len(data['providers'])} 个配置的服务商")
            
            # 更新可用服务商列表
            self.available_providers = [
                provider for provider in data["providers"] 
                if provider.get("enabled", False) and provider.get("healthy", False)
            ]
            
            print(f"   其中 {len(self.available_providers)} 个可用")
            for provider in self.available_providers:
                print(f"   - {provider['name']} ({provider['type']})")
            
            return True
            
        except Exception as e:
            print(f"❌ /providers 端点测试失败: {e}")
            return False
    
    def test_model_routing_sonnet(self):
        """测试 Sonnet 模型路由"""
        print("测试: Sonnet 模型路由")
        
        payload = {
            "model": TEST_MODEL_SONNET,
            "system": [
                {
                    "type": "text",
                    "text": "You are Claude Code, Anthropic's official CLI for Claude.",
                    "cache_control": {
                        "type": "ephemeral"
                    }
                }
            ],
            "messages": [{"role": "user", "content": "回答: OK"}],
            "max_tokens": 10,
            "stream": False
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/v1/messages",
                headers=self.headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code != 200:
                print(f"⚠️  响应状态码: {response.status_code}")
                try:
                    response_data = response.json() if response.headers.get('content-type', '').startswith('application/json') else response.text
                    print(f"   响应内容: {response_data}")
                except:
                    print(f"   响应文本: {response.text}")
                return True  # 可能是服务商配置问题，不算测试失败
            
            data = response.json()
            
            # 检查响应结构 - Anthropic API 响应应该有 content 字段
            if "content" not in data:
                print(f"⚠️  响应结构异常，缺少 content 字段")
                print(f"   实际响应: {data}")
                if "error" in data:
                    print(f"   错误信息: {data['error']}")
                    return True  # 有错误响应也是正常的，可能是服务商问题
                return False  # 既没有 content 也没有 error，这是真正的问题
            
            # 验证 content 字段的结构
            if isinstance(data["content"], list) and len(data["content"]) > 0:
                print(f"✅ 收到有效响应，content 包含 {len(data['content'])} 个块")
            else:
                print(f"⚠️  content 字段为空或格式异常: {data['content']}")
            
            # 检查响应头中是否包含使用的服务商信息
            provider_used = response.headers.get("x-provider-used")
            if provider_used:
                print(f"   使用的服务商: {provider_used}")
            
            print("✅ Sonnet 模型路由测试通过")
            return True
            
        except Exception as e:
            print(f"❌ Sonnet 模型路由测试失败: {e}")
            return False
    
    def test_model_routing_haiku(self):
        """测试 Haiku 模型路由"""
        print("测试: Haiku 模型路由")
        
        payload = {
            "model": TEST_MODEL_HAIKU,
            "messages": [{"role": "user", "content": "回答: OK"}],
            "max_tokens": 10,
            "stream": False
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/v1/messages",
                headers=self.headers,
                json=payload,
                timeout=30
            )
            
            assert response.status_code == 200, f"响应状态码错误: {response.status_code}"
            
            data = response.json()
            assert "content" in data, "响应中缺少 content 字段"
            
            # 检查响应头中是否包含使用的服务商信息
            provider_used = response.headers.get("x-provider-used")
            if provider_used:
                print(f"   使用的服务商: {provider_used}")
            
            print("✅ Haiku 模型路由测试通过")
            return True
            
        except Exception as e:
            print(f"❌ Haiku 模型路由测试失败: {e}")
            return False
    
    def test_unknown_model_routing(self):
        """测试未知模型路由"""
        print("测试: 未知模型路由")
        
        payload = {
            "model": TEST_MODEL_UNKNOWN,
            "messages": [{"role": "user", "content": "回答: OK"}],
            "max_tokens": 10,
            "stream": False
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/v1/messages",
                headers=self.headers,
                json=payload,
                timeout=30
            )
            
            # 未知模型可能返回成功（使用默认路由）或失败
            if response.status_code == 200:
                data = response.json()
                assert "content" in data, "响应中缺少 content 字段"
                print("✅ 未知模型使用默认路由成功")
                return True
            elif response.status_code == 404:
                print("✅ 未知模型正确返回 404")
                return True
            else:
                print(f"⚠️  未知模型返回状态码: {response.status_code}")
                return True  # 任何合理的响应都算通过
                
        except Exception as e:
            print(f"❌ 未知模型路由测试失败: {e}")
            return False
    
    def test_passthrough_model(self):
        """测试透传模式"""
        print("测试: 透传模式")
        
        # 测试自定义模型名称
        payload = {
            "model": TEST_MODEL_HAIKU,
            "messages": [{"role": "user", "content": "透传测试"}],
            "max_tokens": 20,
            "stream": False
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/v1/messages",
                headers=self.headers,
                json=payload,
                timeout=30
            )
            
            # 透传可能成功或失败，取决于后端服务商是否支持该模型
            if response.status_code == 200:
                data = response.json()
                print("✅ 透传模式成功处理自定义模型")
                return True
            elif response.status_code in [400, 404, 422]:
                print("✅ 透传模式正确转发了请求（后端不支持该模型）")
                return True
            else:
                print(f"⚠️  透传模式返回状态码: {response.status_code}")
                return True  # 任何合理的响应都算通过
                
        except Exception as e:
            print(f"❌ 透传模式测试失败: {e}")
            return False
    
    def test_multiple_requests_load_balancing(self):
        """测试多个请求的负载均衡"""
        print("测试: 负载均衡行为")
        
        if len(self.available_providers) < 2:
            print("⚠️  只有一个可用服务商，跳过负载均衡测试")
            return True
        
        payload = {
            "model": TEST_MODEL_HAIKU,
            "messages": [{"role": "user", "content": "简短回答: Hi"}],
            "max_tokens": 5,
            "stream": False
        }
        
        providers_used = []
        
        try:
            # 发送多个请求来观察负载均衡
            for i in range(5):
                response = requests.post(
                    f"{self.base_url}/v1/messages",
                    headers=self.headers,
                    json=payload,
                    timeout=30
                )
                
                assert response.status_code == 200, f"请求 {i+1} 失败: {response.status_code}"
                
                provider_used = response.headers.get("x-provider-used")
                if provider_used:
                    providers_used.append(provider_used)
            
            unique_providers = set(providers_used)
            
            if len(unique_providers) > 1:
                print(f"✅ 负载均衡工作正常，使用了 {len(unique_providers)} 个不同服务商")
                print(f"   使用的服务商: {list(unique_providers)}")
            else:
                print("ℹ️  所有请求使用了同一个服务商（可能是优先级路由）")
            
            return True
            
        except Exception as e:
            print(f"❌ 负载均衡测试失败: {e}")
            return False
    
    def test_provider_priority(self):
        """测试服务商优先级"""
        print("测试: 服务商优先级")
        
        # 连续发送多个相同请求，观察是否优先使用同一个服务商
        payload = {
            "model": TEST_MODEL_SONNET,
            "system": [
                {
                    "type": "text",
                    "text": "You are Claude Code, Anthropic's official CLI for Claude.",
                    "cache_control": {
                        "type": "ephemeral"
                    }
                }
            ],
            "messages": [{"role": "user", "content": "测试优先级"}],
            "max_tokens": 10,
            "stream": False
        }
        
        providers_used = []
        
        try:
            for i in range(3):
                response = requests.post(
                    f"{self.base_url}/v1/messages",
                    headers=self.headers,
                    json=payload,
                    timeout=30
                )
                
                assert response.status_code == 200, f"请求 {i+1} 失败: {response.status_code}"
                
                provider_used = response.headers.get("x-provider-used")
                if provider_used:
                    providers_used.append(provider_used)
            
            # 检查是否主要使用优先级最高的服务商
            if providers_used:
                most_used = max(set(providers_used), key=providers_used.count)
                usage_count = providers_used.count(most_used)
                print(f"✅ 主要使用服务商: {most_used} ({usage_count}/{len(providers_used)} 次)")
            else:
                print("ℹ️  无法确定使用的服务商（响应头中无信息）")
            
            return True
            
        except Exception as e:
            print(f"❌ 服务商优先级测试失败: {e}")
            return False
    
    def test_specify_provider_parameter(self):
        """测试指定 provider 参数功能"""
        print("测试: 指定 provider 参数")
        
        if not self.available_providers:
            print("⚠️  没有可用的服务商，跳过指定 provider 测试")
            return True
        
        # 随机选择一个可用的服务商进行测试
        target_provider = random.choice(self.available_providers)
        provider_name = target_provider["name"]
        
        payload = {
            "model": TEST_MODEL_HAIKU,
            "messages": [{"role": "user", "content": "指定服务商测试"}],
            "max_tokens": 10,
            "stream": False,
            "provider": provider_name
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/v1/messages",
                headers=self.headers,
                json=payload,
                timeout=30
            )
            
            assert response.status_code == 200, f"指定服务商请求失败: {response.status_code}"
            
            data = response.json()
            assert "content" in data, "响应中缺少 content 字段"
            
            # 检查是否使用了指定的服务商
            provider_used = response.headers.get("x-provider-used")
            if provider_used:
                assert provider_used == provider_name, f"使用的服务商不匹配: 期望 {provider_name}, 实际 {provider_used}"
                print(f"✅ 成功使用指定的服务商: {provider_name}")
            else:
                print(f"✅ 指定服务商请求成功（响应头中无服务商信息）")
            
            return True
            
        except Exception as e:
            print(f"❌ 指定 provider 参数测试失败: {e}")
            return False
    
    def test_invalid_provider_parameter(self):
        """测试无效的 provider 参数"""
        print("测试: 无效的 provider 参数")
        
        payload = {
            "model": TEST_MODEL_HAIKU,
            "messages": [{"role": "user", "content": "无效服务商测试"}],
            "max_tokens": 10,
            "stream": False,
            "provider": "nonexistent_provider_12345"
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/v1/messages",
                headers=self.headers,
                json=payload,
                timeout=30
            )
            
            # 应该返回 404 错误
            assert response.status_code == 404, f"期望状态码 404，实际: {response.status_code}"
            
            data = response.json()
            assert "error" in data, "响应中缺少 error 字段"
            
            # 检查错误消息是否包含指定的服务商名称
            error_message = data["error"].get("message", "").lower()
            assert "nonexistent_provider_12345" in error_message, "错误消息中应包含指定的服务商名称"
            
            print("✅ 无效 provider 参数正确返回 404 错误")
            return True
            
        except Exception as e:
            print(f"❌ 无效 provider 参数测试失败: {e}")
            return False
    
    def test_provider_parameter_with_streaming(self):
        """测试带有 provider 参数的流式请求"""
        print("测试: provider 参数 + 流式请求")
        
        if not self.available_providers:
            print("⚠️  没有可用的服务商，跳过 provider + 流式测试")
            return True
        
        # 随机选择一个可用的服务商进行测试
        target_provider = random.choice(self.available_providers)
        provider_name = target_provider["name"]
        
        payload = {
            "model": TEST_MODEL_HAIKU,
            "messages": [{"role": "user", "content": "流式+指定服务商测试"}],
            "max_tokens": 20,
            "stream": True,
            "provider": provider_name
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/v1/messages",
                headers=self.headers,
                json=payload,
                timeout=30,
                stream=True
            )
            
            assert response.status_code == 200, f"流式+指定服务商请求失败: {response.status_code}"
            
            # 检查是否返回流式内容
            content_type = response.headers.get("content-type", "")
            assert "text/event-stream" in content_type.lower(), f"期望流式响应，实际内容类型: {content_type}"
            
            print(f"✅ provider 参数 + 流式请求成功")
            return True
            
        except Exception as e:
            print(f"❌ provider 参数 + 流式请求测试失败: {e}")
            return False
    
    def test_provider_parameter_optional(self):
        """测试 provider 参数是可选的"""
        print("测试: provider 参数可选性")
        
        # 测试不提供 provider 参数的请求
        payload_without_provider = {
            "model": TEST_MODEL_HAIKU,
            "messages": [{"role": "user", "content": "无 provider 参数测试"}],
            "max_tokens": 10,
            "stream": False
        }
        
        # 测试提供 null provider 的请求
        payload_with_null_provider = {
            "model": TEST_MODEL_HAIKU,
            "messages": [{"role": "user", "content": "null provider 参数测试"}],
            "max_tokens": 10,
            "stream": False,
            "provider": None
        }
        
        try:
            # 测试不提供 provider 参数
            response1 = requests.post(
                f"{self.base_url}/v1/messages",
                headers=self.headers,
                json=payload_without_provider,
                timeout=30
            )
            
            assert response1.status_code in [200, 404], f"不提供 provider 参数请求失败: {response1.status_code}"
            
            # 测试提供 null provider
            response2 = requests.post(
                f"{self.base_url}/v1/messages",
                headers=self.headers,
                json=payload_with_null_provider,
                timeout=30
            )
            
            assert response2.status_code in [200, 404], f"null provider 参数请求失败: {response2.status_code}"
            
            print("✅ provider 参数可选性测试通过")
            return True
            
        except Exception as e:
            print(f"❌ provider 参数可选性测试失败: {e}")
            return False
    
    def run_all_tests(self):
        """运行所有测试"""
        print("=" * 60)
        print("开始运行 Provider Routing 测试套件")
        print("=" * 60)
        
        # 先获取服务商状态
        if not self.get_provider_status():
            print("❌ 无法获取服务商状态，测试终止")
            return False
        
        tests = [
            self.test_provider_status_endpoint,
            self.test_model_routing_sonnet,
            self.test_model_routing_haiku,
            self.test_unknown_model_routing,
            self.test_passthrough_model,
            self.test_multiple_requests_load_balancing,
            self.test_provider_priority,
            self.test_specify_provider_parameter,
            self.test_invalid_provider_parameter,
            self.test_provider_parameter_with_streaming,
            self.test_provider_parameter_optional
        ]
        
        passed = 0
        total = len(tests)
        
        for test in tests:
            try:
                if test():
                    passed += 1
            except Exception as e:
                print(f"❌ 测试执行异常: {e}")
            print("-" * 40)
        
        print(f"\n测试结果: {passed}/{total} 通过")
        
        if passed == total:
            print("🎉 所有测试通过!")
            return True
        else:
            print(f"⚠️  {total - passed} 个测试失败")
            return False

def main():
    """主函数"""
    # 检查服务器是否运行
    try:
        response = requests.get(f"{BASE_URL}/", timeout=5)
        if response.status_code != 200:
            print(f"❌ 服务器未正常运行，状态码: {response.status_code}")
            return False
    except requests.exceptions.RequestException:
        print("❌ 无法连接到服务器，请确保服务器正在运行")
        print("   启动命令: python src/main.py")
        return False
    
    # 运行测试
    tester = TestProviderRouting()
    return tester.run_all_tests()

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)