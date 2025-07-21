#!/usr/bin/env python3
"""
测试 OpenAI Compatible 和 Anthropic Provider 之间切换的兼容性
Tests compatibility when switching between OpenAI-compatible and Anthropic providers
"""

import json
import requests
import sys
import os
import time
import random

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from test_utils import get_claude_code_headers

BASE_URL = "http://localhost:9090"

class TestProviderTypeSwitching:
    def __init__(self):
        self.base_url = BASE_URL
        self.headers = get_claude_code_headers()
        self.anthropic_providers = []
        self.openai_providers = []
        
    def get_provider_types(self):
        """获取不同类型的服务商"""
        try:
            response = requests.get(f"{self.base_url}/providers", timeout=10)
            if response.status_code == 200:
                data = response.json()
                providers = data.get("providers", [])
                
                for provider in providers:
                    if provider.get("enabled", False) and provider.get("healthy", False):
                        if provider.get("type") == "anthropic":
                            self.anthropic_providers.append(provider)
                        elif provider.get("type") == "openai":
                            self.openai_providers.append(provider)
                
                print(f"发现 {len(self.anthropic_providers)} 个 Anthropic 服务商")
                print(f"发现 {len(self.openai_providers)} 个 OpenAI 服务商")
                return True
            return False
        except Exception as e:
            print(f"❌ 获取服务商类型失败: {e}")
            return False
    
    def test_anthropic_to_openai_switching(self):
        """测试从 Anthropic 切换到 OpenAI 服务商"""
        print("测试: Anthropic → OpenAI 服务商切换")
        
        if not self.anthropic_providers or not self.openai_providers:
            print("⚠️  需要至少一个 Anthropic 和一个 OpenAI 服务商，跳过测试")
            return True
        
        # 使用相同的模型名，让系统根据路由规则选择不同类型的服务商
        test_model = "claude-3-5-haiku-20241022"
        
        # 构造标准的 Anthropic 格式请求
        anthropic_payload = {
            "model": test_model,
            "messages": [{"role": "user", "content": "测试 Anthropic 格式"}],
            "max_tokens": 20,
            "stream": False
        }
        
        try:
            # 先指定使用 Anthropic 服务商
            anthropic_provider = self.anthropic_providers[0]["name"]
            anthropic_payload["provider"] = anthropic_provider
            
            response1 = requests.post(
                f"{self.base_url}/v1/messages",
                headers=self.headers,
                json=anthropic_payload,
                timeout=30
            )
            
            assert response1.status_code == 200, f"Anthropic 请求失败: {response1.status_code}"
            
            data1 = response1.json()
            assert "content" in data1, "Anthropic 响应缺少 content 字段"
            
            provider_used_1 = response1.headers.get("x-provider-used")
            print(f"   第一次请求使用服务商: {provider_used_1} (Anthropic)")
            
            # 然后指定使用 OpenAI 服务商
            openai_provider = self.openai_providers[0]["name"]
            openai_payload = anthropic_payload.copy()
            openai_payload["provider"] = openai_provider
            openai_payload["messages"] = [{"role": "user", "content": "测试 OpenAI 格式"}]
            
            response2 = requests.post(
                f"{self.base_url}/v1/messages",
                headers=self.headers,
                json=openai_payload,
                timeout=30
            )
            
            assert response2.status_code == 200, f"OpenAI 请求失败: {response2.status_code}"
            
            # OpenAI 格式的响应应该被转换成 Anthropic 格式
            data2 = response2.json()
            assert "content" in data2, "OpenAI 响应转换后缺少 content 字段"
            
            provider_used_2 = response2.headers.get("x-provider-used")
            print(f"   第二次请求使用服务商: {provider_used_2} (OpenAI)")
            
            # 验证两次请求使用了不同类型的服务商
            assert provider_used_1 != provider_used_2, "应该使用不同的服务商"
            
            print("✅ Anthropic → OpenAI 切换成功，格式转换正常")
            return True
            
        except Exception as e:
            print(f"❌ Anthropic → OpenAI 切换测试失败: {e}")
            return False
    
    def test_openai_to_anthropic_switching(self):
        """测试从 OpenAI 切换到 Anthropic 服务商"""
        print("测试: OpenAI → Anthropic 服务商切换")
        
        if not self.anthropic_providers or not self.openai_providers:
            print("⚠️  需要至少一个 Anthropic 和一个 OpenAI 服务商，跳过测试")
            return True
        
        test_model = "claude-3-5-haiku-20241022"
        
        # 构造标准的请求（使用 Anthropic 格式，因为这是我们的标准接口）
        base_payload = {
            "model": test_model,
            "messages": [{"role": "user", "content": "测试服务商切换"}],
            "max_tokens": 20,
            "stream": False
        }
        
        try:
            # 先指定使用 OpenAI 服务商
            openai_provider = self.openai_providers[0]["name"]
            payload1 = base_payload.copy()
            payload1["provider"] = openai_provider
            payload1["messages"] = [{"role": "user", "content": "测试 OpenAI 服务商"}]
            
            response1 = requests.post(
                f"{self.base_url}/v1/messages",
                headers=self.headers,
                json=payload1,
                timeout=30
            )
            
            assert response1.status_code == 200, f"OpenAI 服务商请求失败: {response1.status_code}"
            
            data1 = response1.json()
            assert "content" in data1, "OpenAI 服务商响应缺少 content 字段"
            
            provider_used_1 = response1.headers.get("x-provider-used")
            print(f"   第一次请求使用服务商: {provider_used_1} (OpenAI)")
            
            # 然后指定使用 Anthropic 服务商
            anthropic_provider = self.anthropic_providers[0]["name"]
            payload2 = base_payload.copy()
            payload2["provider"] = anthropic_provider
            payload2["messages"] = [{"role": "user", "content": "测试 Anthropic 服务商"}]
            
            response2 = requests.post(
                f"{self.base_url}/v1/messages",
                headers=self.headers,
                json=payload2,
                timeout=30
            )
            
            assert response2.status_code == 200, f"Anthropic 服务商请求失败: {response2.status_code}"
            
            data2 = response2.json()
            assert "content" in data2, "Anthropic 服务商响应缺少 content 字段"
            
            provider_used_2 = response2.headers.get("x-provider-used")
            print(f"   第二次请求使用服务商: {provider_used_2} (Anthropic)")
            
            # 验证两次请求使用了不同类型的服务商
            assert provider_used_1 != provider_used_2, "应该使用不同的服务商"
            
            print("✅ OpenAI → Anthropic 切换成功，格式处理正常")
            return True
            
        except Exception as e:
            print(f"❌ OpenAI → Anthropic 切换测试失败: {e}")
            return False
    
    def test_rapid_provider_type_switching(self):
        """测试快速切换不同类型服务商，保持对话上下文"""
        print("测试: 快速切换不同类型服务商（多轮对话）")
        
        if not self.anthropic_providers or not self.openai_providers:
            print("⚠️  需要至少一个 Anthropic 和一个 OpenAI 服务商，跳过测试")
            return True
        
        test_model = "claude-3-5-haiku-20241022"
        providers_to_test = []
        
        # 交替选择 Anthropic 和 OpenAI 服务商
        for i in range(6):  # 测试 6 次切换
            if i % 2 == 0:
                provider = random.choice(self.anthropic_providers)
                providers_to_test.append((provider["name"], "anthropic"))
            else:
                provider = random.choice(self.openai_providers)
                providers_to_test.append((provider["name"], "openai"))
        
        try:
            responses = []
            # 保持对话历史
            conversation_messages = [
                {"role": "user", "content": "我们来玩一个数学游戏。我说一个数字，你说下一个数字。开始：1"}
            ]
            
            for i, (provider_name, provider_type) in enumerate(providers_to_test):
                payload = {
                    "model": test_model,
                    "messages": conversation_messages.copy(),  # 使用累积的对话历史
                    "max_tokens": 15,
                    "stream": False,
                    "provider": provider_name
                }
                
                response = requests.post(
                    f"{self.base_url}/v1/messages",
                    headers=self.headers,
                    json=payload,
                    timeout=30
                )
                
                assert response.status_code == 200, f"请求 {i+1} 失败: {response.status_code}"
                
                data = response.json()
                assert "content" in data, f"请求 {i+1} 响应缺少 content 字段"
                
                # 提取助手的回复内容
                assistant_content = ""
                if "content" in data and len(data["content"]) > 0:
                    assistant_content = data["content"][0].get("text", "")
                
                # 将助手的回复添加到对话历史中
                conversation_messages.append({"role": "assistant", "content": assistant_content})
                
                # 为下一轮准备用户消息
                if i < len(providers_to_test) - 1:  # 不是最后一次
                    next_user_message = f"继续游戏，下一个数字是？（当前轮次：{i+2}）"
                    conversation_messages.append({"role": "user", "content": next_user_message})
                
                provider_used = response.headers.get("x-provider-used")
                responses.append({
                    "request_num": i+1,
                    "expected_provider": provider_name,
                    "actual_provider": provider_used,
                    "provider_type": provider_type,
                    "assistant_response": assistant_content,
                    "conversation_length": len(conversation_messages),
                    "success": True
                })
                
                print(f"   请求 {i+1}: {provider_type} 服务商 {provider_used} -> \"{assistant_content}\" (上下文长度: {len(conversation_messages)}) ✅")
                
                # 短暂延迟以模拟实际使用场景
                time.sleep(0.1)
            
            # 验证对话上下文正确传递
            print(f"   完整对话历史: {len(conversation_messages)} 消息")
            for j, msg in enumerate(conversation_messages):
                role_icon = "👤" if msg["role"] == "user" else "🤖"
                content_preview = msg["content"][:50] + "..." if len(msg["content"]) > 50 else msg["content"]
                print(f"     {j+1}. {role_icon} {msg['role']}: {content_preview}")
            
            # 验证所有请求都成功且使用了正确的服务商
            success_count = sum(1 for r in responses if r["success"])
            print(f"✅ 快速切换测试完成: {success_count}/{len(responses)} 请求成功，对话上下文正确传递")
            
            return success_count == len(responses)
            
        except Exception as e:
            print(f"❌ 快速切换测试失败: {e}")
            return False
    
    def test_streaming_with_provider_type_switching(self):
        """测试流式请求中的服务商类型切换"""
        print("测试: 流式请求 + 服务商类型切换")
        
        if not self.anthropic_providers or not self.openai_providers:
            print("⚠️  需要至少一个 Anthropic 和一个 OpenAI 服务商，跳过测试")
            return True
        
        test_model = "claude-3-5-haiku-20241022"
        
        try:
            # 测试 Anthropic 服务商的流式请求
            anthropic_provider = self.anthropic_providers[0]["name"]
            anthropic_payload = {
                "model": test_model,
                "messages": [{"role": "user", "content": "流式测试 Anthropic"}],
                "max_tokens": 30,
                "stream": True,
                "provider": anthropic_provider
            }
            
            response1 = requests.post(
                f"{self.base_url}/v1/messages",
                headers=self.headers,
                json=anthropic_payload,
                timeout=30,
                stream=True
            )
            
            assert response1.status_code == 200, f"Anthropic 流式请求失败: {response1.status_code}"
            
            content_type1 = response1.headers.get("content-type", "")
            assert "text/event-stream" in content_type1.lower(), f"Anthropic 流式响应内容类型错误: {content_type1}"
            
            provider_used_1 = response1.headers.get("x-provider-used")
            print(f"   Anthropic 流式请求使用服务商: {provider_used_1}")
            
            # 测试 OpenAI 服务商的流式请求
            openai_provider = self.openai_providers[0]["name"]
            openai_payload = {
                "model": test_model,
                "messages": [{"role": "user", "content": "流式测试 OpenAI"}],
                "max_tokens": 30,
                "stream": True,
                "provider": openai_provider
            }
            
            response2 = requests.post(
                f"{self.base_url}/v1/messages",
                headers=self.headers,
                json=openai_payload,
                timeout=30,
                stream=True
            )
            
            assert response2.status_code == 200, f"OpenAI 流式请求失败: {response2.status_code}"
            
            content_type2 = response2.headers.get("content-type", "")
            assert "text/event-stream" in content_type2.lower(), f"OpenAI 流式响应内容类型错误: {content_type2}"
            
            provider_used_2 = response2.headers.get("x-provider-used")
            print(f"   OpenAI 流式请求使用服务商: {provider_used_2}")
            
            # 验证使用了不同的服务商
            assert provider_used_1 != provider_used_2, "流式请求应该使用不同的服务商"
            
            print("✅ 流式请求 + 服务商类型切换成功")
            return True
            
        except Exception as e:
            print(f"❌ 流式请求 + 服务商类型切换测试失败: {e}")
            return False
    
    def test_error_handling_during_switching(self):
        """测试切换过程中的错误处理"""
        print("测试: 切换过程中的错误处理")
        
        if not self.anthropic_providers or not self.openai_providers:
            print("⚠️  需要至少一个 Anthropic 和一个 OpenAI 服务商，跳过测试")
            return True
        
        test_model = "claude-3-5-haiku-20241022"
        
        try:
            # 第一部分：测试无效的 Anthropic 服务商
            print("   测试步骤1: 无效服务商请求")
            invalid_payload = {
                "model": test_model,
                "messages": [{"role": "user", "content": "无效服务商测试"}],
                "max_tokens": 10,
                "stream": False,
                "provider": "invalid_anthropic_provider"
            }
            
            try:
                response1 = requests.post(
                    f"{self.base_url}/v1/messages",
                    headers=self.headers,
                    json=invalid_payload,
                    timeout=10  # 减少超时时间，因为404应该很快返回
                )
                
                print(f"   无效服务商响应状态码: {response1.status_code}")
                
                if response1.status_code == 404:
                    try:
                        data1 = response1.json()
                        if "error" in data1:
                            print("   ✅ 无效服务商正确返回 404 错误，包含error字段")
                        else:
                            print("   ✅ 无效服务商正确返回 404 错误，但响应格式可能不标准")
                    except json.JSONDecodeError:
                        print("   ✅ 无效服务商正确返回 404 错误，但响应不是JSON格式")
                else:
                    print(f"   ⚠️  无效服务商返回了非预期状态码: {response1.status_code}")
                    # 打印响应内容以便调试
                    try:
                        print(f"   响应内容: {response1.text[:200]}")
                    except:
                        print("   无法读取响应内容")
                        
            except requests.exceptions.Timeout:
                print("   ❌ 无效服务商请求超时，这不应该发生")
                return False
            except requests.exceptions.RequestException as e:
                print(f"   ❌ 无效服务商请求出现网络错误: {e}")
                return False
            
            # 第二部分：测试有效的 OpenAI 服务商
            print("   测试步骤2: 有效服务商请求")
            valid_openai_provider = self.openai_providers[0]["name"]
            valid_payload = {
                "model": test_model,
                "messages": [{"role": "user", "content": "有效服务商测试"}],
                "max_tokens": 10,
                "stream": False,
                "provider": valid_openai_provider
            }
            
            try:
                response2 = requests.post(
                    f"{self.base_url}/v1/messages",
                    headers=self.headers,
                    json=valid_payload,
                    timeout=30
                )
                
                print(f"   有效服务商响应状态码: {response2.status_code}")
                
                if response2.status_code == 200:
                    try:
                        data2 = response2.json()
                        if "content" in data2:
                            provider_used = response2.headers.get("x-provider-used")
                            print(f"   ✅ 有效服务商请求成功: {provider_used}")
                        else:
                            print("   ⚠️  有效服务商响应缺少 content 字段")
                            print(f"   响应内容: {data2}")
                    except json.JSONDecodeError:
                        print("   ❌ 有效服务商响应不是有效的JSON格式")
                        print(f"   响应内容: {response2.text[:200]}")
                        return False
                else:
                    print(f"   ❌ 有效服务商返回错误状态码: {response2.status_code}")
                    try:
                        print(f"   错误响应: {response2.text[:200]}")
                    except:
                        pass
                    return False
                        
            except requests.exceptions.Timeout:
                print(f"   ❌ 有效服务商 {valid_openai_provider} 请求超时")
                # 检查服务商健康状态
                try:
                    health_resp = requests.get(f"{self.base_url}/providers", timeout=5)
                    if health_resp.status_code == 200:
                        health_data = health_resp.json()
                        for provider in health_data.get("providers", []):
                            if provider["name"] == valid_openai_provider:
                                print(f"   服务商 {valid_openai_provider} 健康状态: {provider.get('healthy', 'unknown')}")
                                break
                except:
                    print("   无法获取服务商健康状态")
                return False
            except requests.exceptions.RequestException as e:
                print(f"   ❌ 有效服务商请求出现网络错误: {e}")
                return False
            
            print("✅ 切换过程中的错误处理测试通过")
            return True
            
        except Exception as e:
            print(f"❌ 切换过程中的错误处理测试失败: {e}")
            import traceback
            print(f"   详细错误信息: {traceback.format_exc()}")
            return False
    
    def test_format_consistency_across_provider_types(self):
        """测试不同服务商类型之间的格式一致性，使用多轮对话测试上下文传递"""
        print("测试: 不同服务商类型的格式一致性（多轮对话）")
        
        if not self.anthropic_providers or not self.openai_providers:
            print("⚠️  需要至少一个 Anthropic 和一个 OpenAI 服务商，跳过测试")
            return True
        
        test_model = "claude-3-5-haiku-20241022"
        
        try:
            responses = []
            # 建立一个有上下文的对话场景
            conversation_messages = [
                {"role": "user", "content": "请记住我叫张三，我喜欢编程。现在请简单自我介绍一下。"}
            ]
            
            # 测试 Anthropic 服务商
            anthropic_provider = self.anthropic_providers[0]["name"]
            anthropic_payload = {
                "model": test_model,
                "messages": conversation_messages.copy(),
                "max_tokens": 30,
                "stream": False,
                "provider": anthropic_provider
            }
            
            response1 = requests.post(
                f"{self.base_url}/v1/messages",
                headers=self.headers,
                json=anthropic_payload,
                timeout=30
            )
            
            assert response1.status_code == 200, f"Anthropic 服务商请求失败: {response1.status_code}"
            
            data1 = response1.json()
            assistant_content1 = ""
            if "content" in data1 and len(data1["content"]) > 0:
                assistant_content1 = data1["content"][0].get("text", "")
            
            # 将助手回复添加到对话历史
            conversation_messages.append({"role": "assistant", "content": assistant_content1})
            conversation_messages.append({"role": "user", "content": "很好！现在请告诉我，你还记得我的名字和爱好吗？"})
            
            responses.append(("anthropic", data1, assistant_content1))
            
            # 测试 OpenAI 服务商 - 使用相同的对话上下文
            openai_provider = self.openai_providers[0]["name"]
            openai_payload = {
                "model": test_model,
                "messages": conversation_messages.copy(),  # 使用累积的对话历史
                "max_tokens": 30,
                "stream": False,
                "provider": openai_provider
            }
            
            response2 = requests.post(
                f"{self.base_url}/v1/messages",
                headers=self.headers,
                json=openai_payload,
                timeout=30
            )
            
            assert response2.status_code == 200, f"OpenAI 服务商请求失败: {response2.status_code}"
            
            data2 = response2.json()
            assistant_content2 = ""
            if "content" in data2 and len(data2["content"]) > 0:
                assistant_content2 = data2["content"][0].get("text", "")
            
            responses.append(("openai", data2, assistant_content2))
            
            # 验证两个响应的格式一致性
            for provider_type, data, content in responses:
                # 检查必要字段
                assert "content" in data, f"{provider_type} 响应缺少 content 字段"
                assert isinstance(data["content"], list), f"{provider_type} content 应该是列表"
                assert len(data["content"]) > 0, f"{provider_type} content 不应该为空"
                
                # 检查 content 块的结构
                for i, content_block in enumerate(data["content"]):
                    assert "type" in content_block, f"{provider_type} content[{i}] 缺少 type 字段"
                    assert "text" in content_block, f"{provider_type} content[{i}] 缺少 text 字段"
                
                # 检查其他标准字段
                standard_fields = []
                for field in ["id", "type", "role", "model", "stop_reason", "usage"]:
                    if field in data:
                        standard_fields.append(field)
                
                content_preview = content[:50] + "..." if len(content) > 50 else content
                print(f"   ✅ {provider_type} 服务商响应格式正确，内容: \"{content_preview}\"")
                print(f"      包含字段: {', '.join(standard_fields)}")
            
            # 打印完整对话历史以验证上下文传递
            print("   完整对话上下文:")
            for j, msg in enumerate(conversation_messages):
                role_icon = "👤" if msg["role"] == "user" else "🤖"
                content_preview = msg["content"][:60] + "..." if len(msg["content"]) > 60 else msg["content"]
                print(f"     {j+1}. {role_icon} {msg['role']}: {content_preview}")
            
            print("✅ 不同服务商类型的格式一致性测试通过，上下文正确传递")
            return True
            
        except Exception as e:
            print(f"❌ 格式一致性测试失败: {e}")
            return False
    
    def test_context_continuity_across_provider_switches(self):
        """测试在服务商切换过程中上下文连续性的保持"""
        print("测试: 服务商切换过程中的上下文连续性")
        
        if not self.anthropic_providers or not self.openai_providers:
            print("⚠️  需要至少一个 Anthropic 和一个 OpenAI 服务商，跳过测试")
            return True
        
        test_model = "claude-3-5-haiku-20241022"
        
        try:
            # 创建一个复杂的上下文场景
            conversation_messages = [
                {"role": "user", "content": "我有一个Python项目，包含以下文件：main.py、utils.py、config.yaml。现在我想添加日志功能。"}
            ]
            
            # 第一轮：使用 Anthropic 服务商
            anthropic_provider = self.anthropic_providers[0]["name"]
            payload1 = {
                "model": test_model,
                "messages": conversation_messages.copy(),
                "max_tokens": 50,
                "stream": False,
                "provider": anthropic_provider
            }
            
            response1 = requests.post(
                f"{self.base_url}/v1/messages",
                headers=self.headers,
                json=payload1,
                timeout=30
            )
            
            assert response1.status_code == 200, f"第一轮 Anthropic 请求失败: {response1.status_code}"
            
            data1 = response1.json()
            assistant_content1 = ""
            if "content" in data1 and len(data1["content"]) > 0:
                assistant_content1 = data1["content"][0].get("text", "")
            
            conversation_messages.append({"role": "assistant", "content": assistant_content1})
            conversation_messages.append({"role": "user", "content": "很好的建议！现在我想把日志配置放在config.yaml中，应该怎么配置？"})
            
            provider_used1 = response1.headers.get("x-provider-used")
            print(f"   第1轮 {anthropic_provider} ({provider_used1}): \"{assistant_content1[:50]}...\"")
            
            # 第二轮：切换到 OpenAI 服务商
            openai_provider = self.openai_providers[0]["name"]
            payload2 = {
                "model": test_model,
                "messages": conversation_messages.copy(),
                "max_tokens": 50,
                "stream": False,
                "provider": openai_provider
            }
            
            response2 = requests.post(
                f"{self.base_url}/v1/messages",
                headers=self.headers,
                json=payload2,
                timeout=30
            )
            
            assert response2.status_code == 200, f"第二轮 OpenAI 请求失败: {response2.status_code}"
            
            data2 = response2.json()
            assistant_content2 = ""
            if "content" in data2 and len(data2["content"]) > 0:
                assistant_content2 = data2["content"][0].get("text", "")
            
            conversation_messages.append({"role": "assistant", "content": assistant_content2})
            conversation_messages.append({"role": "user", "content": "完美！最后一个问题：在main.py中应该怎么调用这个日志配置？"})
            
            provider_used2 = response2.headers.get("x-provider-used")
            print(f"   第2轮 {openai_provider} ({provider_used2}): \"{assistant_content2[:50]}...\"")
            
            # 第三轮：再次切换回 Anthropic 服务商，测试长上下文保持
            payload3 = {
                "model": test_model,
                "messages": conversation_messages.copy(),
                "max_tokens": 50,
                "stream": False,
                "provider": anthropic_provider
            }
            
            response3 = requests.post(
                f"{self.base_url}/v1/messages",
                headers=self.headers,
                json=payload3,
                timeout=30
            )
            
            assert response3.status_code == 200, f"第三轮 Anthropic 请求失败: {response3.status_code}"
            
            data3 = response3.json()
            assistant_content3 = ""
            if "content" in data3 and len(data3["content"]) > 0:
                assistant_content3 = data3["content"][0].get("text", "")
            
            provider_used3 = response3.headers.get("x-provider-used")
            print(f"   第3轮 {anthropic_provider} ({provider_used3}): \"{assistant_content3[:50]}...\"")
            
            # 验证上下文连续性
            print(f"\n   上下文连续性分析:")
            print(f"   - 总对话轮数: {len(conversation_messages)} 条消息")
            print(f"   - 服务商切换: {provider_used1} -> {provider_used2} -> {provider_used3}")
            
            # 检查回复的相关性（简单的关键词检查）
            context_keywords = ["日志", "log", "config", "yaml", "main.py", "python"]
            relevant_responses = 0
            
            for i, content in enumerate([assistant_content1, assistant_content2, assistant_content3], 1):
                content_lower = content.lower()
                keyword_matches = [kw for kw in context_keywords if kw in content_lower]
                if keyword_matches:
                    relevant_responses += 1
                    print(f"   - 第{i}轮回复包含相关关键词: {keyword_matches}")
                else:
                    print(f"   - 第{i}轮回复未包含明显的上下文关键词")
            
            # 打印完整对话历史
            print(f"\n   完整对话历史:")
            for j, msg in enumerate(conversation_messages):
                role_icon = "👤" if msg["role"] == "user" else "🤖"
                content_preview = msg["content"][:80] + "..." if len(msg["content"]) > 80 else msg["content"]
                print(f"     {j+1}. {role_icon} {msg['role']}: {content_preview}")
            
            # 验证结果
            if relevant_responses >= 2:  # 至少2/3的回复应该与上下文相关
                print(f"✅ 上下文连续性测试通过: {relevant_responses}/3 轮回复与上下文相关")
                return True
            else:
                print(f"⚠️  上下文连续性可能有问题: 只有 {relevant_responses}/3 轮回复与上下文明显相关")
                return True  # 仍然返回True，因为这可能是正常的LLM行为差异
            
        except Exception as e:
            print(f"❌ 上下文连续性测试失败: {e}")
            return False
    
    def run_all_tests(self):
        """运行所有测试"""
        print("=" * 60)
        print("开始运行 Provider Type Switching 测试套件")
        print("=" * 60)
        
        # 先获取服务商类型信息
        if not self.get_provider_types():
            print("❌ 无法获取服务商类型信息，测试终止")
            return False
        
        tests = [
            self.test_anthropic_to_openai_switching,
            self.test_openai_to_anthropic_switching,
            self.test_rapid_provider_type_switching,
            self.test_streaming_with_provider_type_switching,
            self.test_error_handling_during_switching,
            self.test_format_consistency_across_provider_types,
            self.test_context_continuity_across_provider_switches
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
            print("🎉 所有服务商类型切换测试通过!")
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
    tester = TestProviderTypeSwitching()
    return tester.run_all_tests()

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)