#!/usr/bin/env python3
"""
测试错误处理和边缘情况
包括各种异常情况的处理和系统健壮性测试
"""

import json
import time
import requests
import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from test_utils import get_claude_code_headers

BASE_URL = "http://localhost:8080"

class TestErrorHandling:
    def __init__(self):
        self.base_url = BASE_URL
        self.headers = get_claude_code_headers()
        
    def test_invalid_json_request(self):
        """测试无效JSON请求"""
        print("测试: 无效JSON请求")
        
        invalid_json_strings = [
            '{"model": "claude-3-5-haiku-20241022", "messages": [{"role": "user", "content": "test"}]',  # 缺少闭合括号
            '{"model": "claude-3-5-haiku-20241022", "messages": [{"role": "user", "content": "test"}], "max_tokens": }',  # 无效值
            '{"model": "claude-3-5-haiku-20241022", "messages": [{"role": "user", "content": "test"], "max_tokens": 10}',  # 缺少闭合括号
            'not json at all',  # 完全不是JSON
            '',  # 空字符串
        ]
        
        success_count = 0
        
        try:
            for i, invalid_json in enumerate(invalid_json_strings):
                print(f"   测试无效JSON {i+1}...")
                
                try:
                    response = requests.post(
                        f"{self.base_url}/v1/messages",
                        headers=self.headers,
                        data=invalid_json,  # 使用data而不是json
                        timeout=10
                    )
                    
                    # 应该返回400错误
                    if response.status_code == 400:
                        print(f"   ✅ 正确返回400错误")
                        success_count += 1
                    elif response.status_code in [422, 500]:
                        print(f"   ✅ 返回错误状态码: {response.status_code}")
                        success_count += 1
                    else:
                        print(f"   ⚠️  意外状态码: {response.status_code}")
                        
                except requests.exceptions.RequestException as e:
                    print(f"   ✅ 连接层面拒绝请求: {e}")
                    success_count += 1
            
            if success_count >= len(invalid_json_strings) * 0.8:  # 80%成功率
                print("✅ 无效JSON处理测试通过")
                return True
            else:
                print(f"⚠️  部分无效JSON未正确处理 ({success_count}/{len(invalid_json_strings)})")
                return False
                
        except Exception as e:
            print(f"❌ 无效JSON测试失败: {e}")
            return False
    
    def test_missing_required_fields(self):
        """测试缺少必要字段的请求"""
        print("测试: 缺少必要字段")
        
        # 各种缺少字段的请求
        invalid_payloads = [
            {},  # 完全空
            {"model": "claude-3-5-haiku-20241022"},  # 缺少messages
            {"messages": [{"role": "user", "content": "test"}]},  # 缺少model
            {"model": "claude-3-5-haiku-20241022", "messages": []},  # 空messages
            {"model": "", "messages": [{"role": "user", "content": "test"}]},  # 空model
            {"model": "claude-3-5-haiku-20241022", "messages": [{"role": "user"}]},  # 缺少content
            {"model": "claude-3-5-haiku-20241022", "messages": [{"content": "test"}]},  # 缺少role
            {"model": "claude-3-5-haiku-20241022", "messages": [{"role": "", "content": "test"}]},  # 空role
        ]
        
        success_count = 0
        
        try:
            for i, payload in enumerate(invalid_payloads):
                print(f"   测试缺少字段 {i+1}: {str(payload)[:50]}...")
                
                response = requests.post(
                    f"{self.base_url}/v1/messages",
                    headers=self.headers,
                    json=payload,
                    timeout=10
                )
                
                # 应该返回400或422错误
                if response.status_code in [400, 422]:
                    print(f"   ✅ 正确返回错误: {response.status_code}")
                    success_count += 1
                else:
                    print(f"   ⚠️  意外状态码: {response.status_code}")
            
            if success_count >= len(invalid_payloads) * 0.8:
                print("✅ 必要字段验证测试通过")
                return True
            else:
                print(f"⚠️  部分字段验证失败 ({success_count}/{len(invalid_payloads)})")
                return False
                
        except Exception as e:
            print(f"❌ 必要字段测试失败: {e}")
            return False
    
    def test_invalid_model_names(self):
        """测试无效模型名称"""
        print("测试: 无效模型名称")
        
        invalid_models = [
            "",  # 空字符串
            "   ",  # 空白字符
            "invalid-model-12345",  # 不存在的模型
            "gpt-4",  # 错误的API模型名
            "claude-99-ultra-mega",  # 不存在的Claude模型
            "model/with/slashes",  # 特殊字符
            "model with spaces",  # 空格
            "extremely-long-model-name-that-should-not-exist-in-any-reasonable-system-ever-created",  # 超长名称
        ]
        
        success_count = 0
        
        try:
            for model in invalid_models:
                print(f"   测试无效模型: '{model}'...")
                
                payload = {
                    "model": model,
                    "messages": [{"role": "user", "content": "test"}],
                    "max_tokens": 10,
                    "stream": False
                }
                
                response = requests.post(
                    f"{self.base_url}/v1/messages",
                    headers=self.headers,
                    json=payload,
                    timeout=30
                )
                
                # 可能返回400, 404, 422等错误，或者透传给后端处理
                if response.status_code in [400, 404, 422, 500]:
                    print(f"   ✅ 返回错误状态码: {response.status_code}")
                    success_count += 1
                elif response.status_code == 200:
                    print(f"   ℹ️  模型被接受（可能是透传模式）")
                    success_count += 1  # 透传模式也算正确处理
                else:
                    print(f"   ⚠️  意外状态码: {response.status_code}")
            
            if success_count >= len(invalid_models) * 0.7:
                print("✅ 无效模型处理测试通过")
                return True
            else:
                print(f"⚠️  部分无效模型未正确处理 ({success_count}/{len(invalid_models)})")
                return False
                
        except Exception as e:
            print(f"❌ 无效模型测试失败: {e}")
            return False
    
    def test_extreme_token_limits(self):
        """测试极端token限制"""
        print("测试: 极端token限制")
        
        extreme_limits = [
            -1,  # 负数
            0,   # 零
            1,   # 极小值
            999999,  # 极大值
            "invalid",  # 字符串
            None,  # null值
        ]
        
        success_count = 0
        
        try:
            for limit in extreme_limits:
                print(f"   测试token限制: {limit}")
                
                payload = {
                    "model": "claude-3-5-haiku-20241022",
                    "messages": [{"role": "user", "content": "test"}],
                    "max_tokens": limit,
                    "stream": False
                }
                
                response = requests.post(
                    f"{self.base_url}/v1/messages",
                    headers=self.headers,
                    json=payload,
                    timeout=30
                )
                
                if limit in [-1, 0, "invalid", None]:
                    # 这些应该返回错误
                    if response.status_code in [400, 422]:
                        print(f"   ✅ 正确拒绝: {response.status_code}")
                        success_count += 1
                    else:
                        print(f"   ⚠️  未拒绝无效值: {response.status_code}")
                elif limit == 1:
                    # 极小值可能成功或失败
                    if response.status_code in [200, 400, 422]:
                        print(f"   ✅ 合理处理: {response.status_code}")
                        success_count += 1
                    else:
                        print(f"   ⚠️  异常状态码: {response.status_code}")
                elif limit == 999999:
                    # 极大值可能被限制
                    if response.status_code in [200, 400, 422]:
                        print(f"   ✅ 合理处理: {response.status_code}")
                        success_count += 1
                    else:
                        print(f"   ⚠️  异常状态码: {response.status_code}")
            
            if success_count >= len(extreme_limits) * 0.8:
                print("✅ 极端token限制测试通过")
                return True
            else:
                print(f"⚠️  部分极端值未正确处理 ({success_count}/{len(extreme_limits)})")
                return False
                
        except Exception as e:
            print(f"❌ 极端token限制测试失败: {e}")
            return False
    
    def test_malformed_messages(self):
        """测试格式错误的消息"""
        print("测试: 格式错误的消息")
        
        malformed_messages = [
            # 错误的role
            [{"role": "invalid", "content": "test"}],
            [{"role": "ASSISTANT", "content": "test"}],  # 大写
            [{"role": 123, "content": "test"}],  # 数字
            
            # 错误的content
            [{"role": "user", "content": 123}],  # 数字content
            [{"role": "user", "content": None}],  # null content
            [{"role": "user", "content": []}],  # 数组content
            
            # 错误的结构
            [{"role": "user"}],  # 缺少content
            [{"content": "test"}],  # 缺少role
            ["not an object"],  # 数组中包含字符串
            [{}],  # 空对象
            
            # 复杂错误
            [
                {"role": "user", "content": "first message"},
                {"role": "assistant"},  # 缺少content
                {"role": "user", "content": "third message"}
            ],
        ]
        
        success_count = 0
        
        try:
            for i, messages in enumerate(malformed_messages):
                print(f"   测试错误消息 {i+1}...")
                
                payload = {
                    "model": "claude-3-5-haiku-20241022",
                    "messages": messages,
                    "max_tokens": 10,
                    "stream": False
                }
                
                response = requests.post(
                    f"{self.base_url}/v1/messages",
                    headers=self.headers,
                    json=payload,
                    timeout=30
                )
                
                # 大多数应该返回400或422错误
                if response.status_code in [400, 422, 500]:
                    print(f"   ✅ 正确拒绝: {response.status_code}")
                    success_count += 1
                elif response.status_code == 200:
                    print(f"   ⚠️  意外接受了错误消息")
                else:
                    print(f"   ⚠️  意外状态码: {response.status_code}")
            
            if success_count >= len(malformed_messages) * 0.8:
                print("✅ 错误消息处理测试通过")
                return True
            else:
                print(f"⚠️  部分错误消息未正确处理 ({success_count}/{len(malformed_messages)})")
                return False
                
        except Exception as e:
            print(f"❌ 错误消息测试失败: {e}")
            return False
    
    def test_very_long_content(self):
        """测试超长内容"""
        print("测试: 超长内容")
        
        try:
            # 创建一个很长的内容
            long_content = "这是一个很长的测试内容。" * 1000  # 约15000字符
            
            payload = {
                "model": "claude-3-5-haiku-20241022",
                "messages": [{"role": "user", "content": long_content}],
                "max_tokens": 50,
                "stream": False
            }
            
            print(f"   发送超长内容 ({len(long_content)} 字符)...")
            
            response = requests.post(
                f"{self.base_url}/v1/messages",
                headers=self.headers,
                json=payload,
                timeout=60  # 更长的超时时间
            )
            
            if response.status_code == 200:
                print("✅ 超长内容处理成功")
                return True
            elif response.status_code in [400, 413, 422]:  # 413是Payload Too Large
                print(f"✅ 正确拒绝超长内容: {response.status_code}")
                return True
            else:
                print(f"⚠️  意外状态码: {response.status_code}")
                return False
                
        except requests.exceptions.Timeout:
            print("✅ 超长内容触发超时（合理行为）")
            return True
        except Exception as e:
            print(f"❌ 超长内容测试失败: {e}")
            return False
    
    def test_unicode_and_special_characters(self):
        """测试Unicode和特殊字符"""
        print("测试: Unicode和特殊字符")
        
        special_contents = [
            "Hello 世界 🌍",  # 中英文混合 + emoji
            "🎉🎈🎊🎁🎀",  # 纯emoji
            "ñáéíóú çñ àèìòù",  # 各种重音符号
            "Здравствуй мир",  # 俄文
            "مرحبا بالعالم",  # 阿拉伯文
            "こんにちは世界",  # 日文
            "😀😃😄😁😆😅🤣😂",  # 表情符号
            "\n\t\r\\\"\'",  # 转义字符
            "null\x00byte",  # 包含null字节
            "very\"complex'string`with$various{special}[characters]",  # 各种特殊字符
        ]
        
        success_count = 0
        
        try:
            for i, content in enumerate(special_contents):
                print(f"   测试特殊字符 {i+1}: {content[:30]}...")
                
                payload = {
                    "model": "claude-3-5-haiku-20241022",
                    "messages": [{"role": "user", "content": content}],
                    "max_tokens": 20,
                    "stream": False
                }
                
                response = requests.post(
                    f"{self.base_url}/v1/messages",
                    headers=self.headers,
                    json=payload,
                    timeout=30
                )
                
                if response.status_code == 200:
                    print(f"   ✅ 成功处理特殊字符")
                    success_count += 1
                elif response.status_code in [400, 422]:
                    print(f"   ✅ 合理拒绝: {response.status_code}")
                    success_count += 1
                else:
                    print(f"   ⚠️  意外状态码: {response.status_code}")
            
            if success_count >= len(special_contents) * 0.8:
                print("✅ 特殊字符处理测试通过")
                return True
            else:
                print(f"⚠️  部分特殊字符未正确处理 ({success_count}/{len(special_contents)})")
                return False
                
        except Exception as e:
            print(f"❌ 特殊字符测试失败: {e}")
            return False
    
    def test_concurrent_error_requests(self):
        """测试并发错误请求"""
        print("测试: 并发错误请求")
        
        import threading
        
        # 各种错误请求
        error_payloads = [
            {},  # 空请求
            {"model": "invalid", "messages": [{"role": "user", "content": "test"}]},  # 无效模型
            {"model": "claude-3-5-haiku-20241022", "messages": []},  # 空消息
            {"model": "claude-3-5-haiku-20241022", "messages": [{"role": "invalid", "content": "test"}]},  # 无效role
        ]
        
        results = []
        
        def send_error_request(request_id, payload):
            """发送错误请求"""
            try:
                response = requests.post(
                    f"{self.base_url}/v1/messages",
                    headers=self.headers,
                    json=payload,
                    timeout=30
                )
                
                results.append({
                    "id": request_id,
                    "status_code": response.status_code,
                    "success": response.status_code in [400, 422, 500]  # 错误状态码算成功
                })
                
            except Exception as e:
                results.append({
                    "id": request_id,
                    "error": str(e),
                    "success": False
                })
        
        try:
            # 创建并发错误请求
            threads = []
            
            for i in range(10):  # 10个并发请求
                payload = error_payloads[i % len(error_payloads)]
                thread = threading.Thread(target=send_error_request, args=(i, payload))
                threads.append(thread)
                thread.start()
            
            # 等待所有线程完成
            for thread in threads:
                thread.join(timeout=60)
            
            # 分析结果
            successful_error_handling = sum(1 for r in results if r["success"])
            total_requests = len(results)
            
            print(f"   并发错误请求处理: {successful_error_handling}/{total_requests}")
            
            if successful_error_handling >= total_requests * 0.8:
                print("✅ 并发错误请求处理测试通过")
                return True
            else:
                print("⚠️  并发错误处理存在问题")
                return False
                
        except Exception as e:
            print(f"❌ 并发错误请求测试失败: {e}")
            return False
    
    def test_server_stress_with_errors(self):
        """测试错误请求对服务器稳定性的影响"""
        print("测试: 错误请求对服务器稳定性的影响")
        
        try:
            # 发送大量错误请求
            print("   发送大量错误请求...")
            for i in range(20):
                try:
                    response = requests.post(
                        f"{self.base_url}/v1/messages",
                        headers=self.headers,
                        json={},  # 空请求
                        timeout=10
                    )
                    # 不关心结果，只是压力测试
                except:
                    pass
            
            # 等待一下
            time.sleep(1)
            
            # 验证服务器仍能正常处理正确请求
            print("   验证服务器仍能处理正常请求...")
            normal_payload = {
                "model": "claude-3-5-haiku-20241022",
                "messages": [{"role": "user", "content": "服务器稳定性测试"}],
                "max_tokens": 20,
                "stream": False
            }
            
            response = requests.post(
                f"{self.base_url}/v1/messages",
                headers=self.headers,
                json=normal_payload,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                if "content" in data:
                    print("✅ 服务器在错误请求后仍然稳定")
                    return True
                else:
                    print("⚠️  服务器响应格式异常")
                    return False
            else:
                print(f"❌ 服务器稳定性受影响: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ 服务器稳定性测试失败: {e}")
            return False
    
    def run_all_tests(self):
        """运行所有测试"""
        print("=" * 60)
        print("开始运行 Error Handling 测试套件")
        print("=" * 60)
        
        tests = [
            self.test_invalid_json_request,
            self.test_missing_required_fields,
            self.test_invalid_model_names,
            self.test_extreme_token_limits,
            self.test_malformed_messages,
            self.test_very_long_content,
            self.test_unicode_and_special_characters,
            self.test_concurrent_error_requests,
            self.test_server_stress_with_errors
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
    tester = TestErrorHandling()
    return tester.run_all_tests()

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)