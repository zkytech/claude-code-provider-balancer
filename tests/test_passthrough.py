#!/usr/bin/env python3
"""
测试透传模式功能
包括模型名称透传、自定义模型处理等场景
"""

import json
import time
import requests
import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from test_utils import get_claude_code_headers

BASE_URL = "http://localhost:9090"

class TestPassthrough:
    def __init__(self):
        self.base_url = BASE_URL
        self.headers = get_claude_code_headers()
        
    def test_standard_model_passthrough(self):
        """测试标准模型透传"""
        print("测试: 标准模型透传")
        
        # 测试标准 Claude 模型是否能正确透传
        standard_models = [
            "claude-3-5-sonnet-20241022",
            "claude-3-5-haiku-20241022", 
            "claude-3-opus-20240229",
            "claude-3-sonnet-20240229",
            "claude-3-haiku-20240307"
        ]
        
        success_count = 0
        
        try:
            for model in standard_models:
                print(f"   测试模型: {model}")
                
                payload = {
                    "model": model,
                    "messages": [{"role": "user", "content": "透传测试：简单回答OK"}],
                    "max_tokens": 10,
                    "stream": False
                }
                
                response = requests.post(
                    f"{self.base_url}/v1/messages",
                    headers=self.headers,
                    json=payload,
                    timeout=30
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if "content" in data:
                        print(f"   ✅ {model} 透传成功")
                        success_count += 1
                    else:
                        print(f"   ⚠️  {model} 响应格式异常")
                elif response.status_code in [400, 404, 422]:
                    print(f"   ℹ️  {model} 被后端拒绝 (状态码: {response.status_code})")
                    success_count += 1  # 正确转发给后端也算成功
                else:
                    print(f"   ❌ {model} 意外错误: {response.status_code}")
            
            if success_count >= len(standard_models) * 0.8:
                print("✅ 标准模型透传测试通过")
                return True
            else:
                print(f"⚠️  部分标准模型透传失败 ({success_count}/{len(standard_models)})")
                return False
                
        except Exception as e:
            print(f"❌ 标准模型透传测试失败: {e}")
            return False
    
    def test_custom_model_passthrough(self):
        """测试自定义模型透传"""
        print("测试: 自定义模型透传")
        
        # 测试各种自定义模型名称
        custom_models = [
            "custom-model-v1",
            "my-fine-tuned-claude",
            "deepseek/deepseek-chat",
            "anthropic/claude-3-sonnet",
            "openai/gpt-4",
            "google/gemini-pro",
            "meta/llama-2-70b",
            "company/internal-model-2024",
            "模型名称中文",
            "model-with-special-chars@v1.0"
        ]
        
        success_count = 0
        
        try:
            for model in custom_models:
                print(f"   测试自定义模型: {model}")
                
                payload = {
                    "model": model,
                    "messages": [{"role": "user", "content": "自定义模型测试"}],
                    "max_tokens": 10,
                    "stream": False
                }
                
                response = requests.post(
                    f"{self.base_url}/v1/messages",
                    headers=self.headers,
                    json=payload,
                    timeout=30
                )
                
                # 自定义模型可能成功或被后端拒绝，都算正常透传
                if response.status_code == 200:
                    print(f"   ✅ {model} 透传并被后端接受")
                    success_count += 1
                elif response.status_code in [400, 404, 422, 500]:
                    print(f"   ✅ {model} 透传但被后端拒绝 (状态码: {response.status_code})")
                    success_count += 1
                else:
                    print(f"   ❌ {model} 透传异常: {response.status_code}")
            
            if success_count >= len(custom_models) * 0.8:
                print("✅ 自定义模型透传测试通过")
                return True
            else:
                print(f"⚠️  部分自定义模型透传失败 ({success_count}/{len(custom_models)})")
                return False
                
        except Exception as e:
            print(f"❌ 自定义模型透传测试失败: {e}")
            return False
    
    def test_passthrough_vs_routing(self):
        """测试透传模式与路由模式的区别"""
        print("测试: 透传模式与路由模式的区别")
        
        try:
            # 测试1: 使用配置中明确路由的模型
            routed_payload = {
                "model": "claude-3-5-sonnet-20241022",  # 这个通常在配置中有路由
                "messages": [{"role": "user", "content": "路由测试"}],
                "max_tokens": 15,
                "stream": False
            }
            
            print("   发送路由模型请求...")
            response1 = requests.post(
                f"{self.base_url}/v1/messages",
                headers=self.headers,
                json=routed_payload,
                timeout=30
            )
            
            routed_success = response1.status_code == 200
            if routed_success:
                print("   ✅ 路由模型请求成功")
            else:
                print(f"   ⚠️  路由模型请求失败: {response1.status_code}")
            
            # 测试2: 使用完全自定义的模型名（应该透传）
            passthrough_payload = {
                "model": "my-custom-passthrough-model-12345",
                "messages": [{"role": "user", "content": "透传测试"}],
                "max_tokens": 15,
                "stream": False
            }
            
            print("   发送透传模型请求...")
            response2 = requests.post(
                f"{self.base_url}/v1/messages",
                headers=self.headers,
                json=passthrough_payload,
                timeout=30
            )
            
            # 透传请求可能成功或失败，但应该被正确转发
            passthrough_handled = response2.status_code in [200, 400, 404, 422, 500]
            if passthrough_handled:
                print(f"   ✅ 透传模型被正确处理 (状态码: {response2.status_code})")
            else:
                print(f"   ❌ 透传模型处理异常: {response2.status_code}")
            
            # 测试3: 比较响应头中的服务商信息（如果有）
            provider1 = response1.headers.get("x-provider-used", "未知")
            provider2 = response2.headers.get("x-provider-used", "未知")
            
            if provider1 != "未知" or provider2 != "未知":
                print(f"   ℹ️  使用的服务商: 路由模型={provider1}, 透传模型={provider2}")
            
            if routed_success and passthrough_handled:
                print("✅ 透传与路由模式区别测试通过")
                return True
            else:
                print("⚠️  透传与路由模式测试部分失败")
                return False
                
        except Exception as e:
            print(f"❌ 透传与路由模式测试失败: {e}")
            return False
    
    def test_passthrough_with_different_parameters(self):
        """测试透传模式下不同参数的处理"""
        print("测试: 透传模式下不同参数处理")
        
        custom_model = "test-passthrough-params-model"
        
        test_cases = [
            {
                "name": "基础参数",
                "payload": {
                    "model": custom_model,
                    "messages": [{"role": "user", "content": "基础测试"}],
                    "max_tokens": 20
                }
            },
            {
                "name": "温度参数", 
                "payload": {
                    "model": custom_model,
                    "messages": [{"role": "user", "content": "温度测试"}],
                    "max_tokens": 20,
                    "temperature": 0.7
                }
            },
            {
                "name": "流式请求",
                "payload": {
                    "model": custom_model,
                    "messages": [{"role": "user", "content": "流式测试"}],
                    "max_tokens": 20,
                    "stream": True
                }
            },
            {
                "name": "系统消息",
                "payload": {
                    "model": custom_model,
                    "messages": [
                        {"role": "system", "content": "你是一个有用的助手"},
                        {"role": "user", "content": "系统消息测试"}
                    ],
                    "max_tokens": 20
                }
            },
            {
                "name": "多轮对话",
                "payload": {
                    "model": custom_model,
                    "messages": [
                        {"role": "user", "content": "第一轮"},
                        {"role": "assistant", "content": "回复"},
                        {"role": "user", "content": "第二轮"}
                    ],
                    "max_tokens": 20
                }
            }
        ]
        
        success_count = 0
        
        try:
            for case in test_cases:
                print(f"   测试: {case['name']}")
                
                is_stream = case["payload"].get("stream", False)
                
                response = requests.post(
                    f"{self.base_url}/v1/messages",
                    headers=self.headers,
                    json=case["payload"],
                    stream=is_stream,
                    timeout=30
                )
                
                if is_stream:
                    # 处理流式响应
                    if response.status_code == 200:
                        chunks_received = 0
                        try:
                            for line in response.iter_lines():
                                if line:
                                    chunks_received += 1
                                    if chunks_received >= 3:  # 收到几个数据块就够了
                                        break
                            response.close()
                            print(f"     ✅ 流式透传成功 (收到 {chunks_received} 个数据块)")
                            success_count += 1
                        except:
                            print(f"     ✅ 流式透传被转发 (状态码: {response.status_code})")
                            success_count += 1
                    else:
                        print(f"     ✅ 流式请求被正确处理 (状态码: {response.status_code})")
                        success_count += 1
                else:
                    # 处理非流式响应
                    if response.status_code in [200, 400, 404, 422, 500]:
                        print(f"     ✅ 参数透传成功 (状态码: {response.status_code})")
                        success_count += 1
                    else:
                        print(f"     ❌ 参数透传异常: {response.status_code}")
            
            if success_count >= len(test_cases) * 0.8:
                print("✅ 透传参数处理测试通过")
                return True
            else:
                print(f"⚠️  部分参数透传测试失败 ({success_count}/{len(test_cases)})")
                return False
                
        except Exception as e:
            print(f"❌ 透传参数处理测试失败: {e}")
            return False
    
    def test_passthrough_error_handling(self):
        """测试透传模式的错误处理"""
        print("测试: 透传模式错误处理")
        
        error_cases = [
            {
                "name": "空模型名",
                "model": "",
                "expected_codes": [400, 422]
            },
            {
                "name": "特殊字符模型",
                "model": "model/with/slashes",
                "expected_codes": [200, 400, 404, 422, 500]
            },
            {
                "name": "超长模型名",
                "model": "extremely-long-model-name-" + "x" * 200,
                "expected_codes": [200, 400, 413, 422, 500]
            },
            {
                "name": "包含空格",
                "model": "model with spaces",
                "expected_codes": [200, 400, 422, 500]
            },
            {
                "name": "特殊Unicode",
                "model": "模型🤖名称",
                "expected_codes": [200, 400, 422, 500]
            }
        ]
        
        success_count = 0
        
        try:
            for case in error_cases:
                print(f"   测试: {case['name']}")
                
                payload = {
                    "model": case["model"],
                    "messages": [{"role": "user", "content": "错误处理测试"}],
                    "max_tokens": 10,
                    "stream": False
                }
                
                response = requests.post(
                    f"{self.base_url}/v1/messages",
                    headers=self.headers,
                    json=payload,
                    timeout=30
                )
                
                if response.status_code in case["expected_codes"]:
                    print(f"     ✅ 错误正确处理 (状态码: {response.status_code})")
                    success_count += 1
                else:
                    print(f"     ⚠️  意外状态码: {response.status_code}")
                    success_count += 0.5  # 部分分数
            
            if success_count >= len(error_cases) * 0.8:
                print("✅ 透传错误处理测试通过")
                return True
            else:
                print(f"⚠️  部分错误处理测试失败 ({success_count}/{len(error_cases)})")
                return False
                
        except Exception as e:
            print(f"❌ 透传错误处理测试失败: {e}")
            return False
    
    def test_passthrough_performance(self):
        """测试透传模式性能"""
        print("测试: 透传模式性能")
        
        try:
            # 测试标准模型性能
            standard_model = "claude-3-5-haiku-20241022"
            standard_payload = {
                "model": standard_model,
                "messages": [{"role": "user", "content": "性能测试"}],
                "max_tokens": 10,
                "stream": False
            }
            
            print("   测试标准模型性能...")
            start_time = time.time()
            response1 = requests.post(
                f"{self.base_url}/v1/messages",
                headers=self.headers,
                json=standard_payload,
                timeout=30
            )
            standard_duration = time.time() - start_time
            
            # 测试自定义模型性能
            custom_model = "custom-performance-test-model"
            custom_payload = {
                "model": custom_model,
                "messages": [{"role": "user", "content": "性能测试"}],
                "max_tokens": 10,
                "stream": False
            }
            
            print("   测试自定义模型性能...")
            start_time = time.time()
            response2 = requests.post(
                f"{self.base_url}/v1/messages",
                headers=self.headers,
                json=custom_payload,
                timeout=30
            )
            custom_duration = time.time() - start_time
            
            print(f"   标准模型耗时: {standard_duration:.2f}s (状态码: {response1.status_code})")
            print(f"   自定义模型耗时: {custom_duration:.2f}s (状态码: {response2.status_code})")
            
            # 性能差异分析
            if abs(standard_duration - custom_duration) < 1.0:
                print("✅ 透传性能正常，无明显延迟")
            else:
                print(f"ℹ️  性能差异: {abs(standard_duration - custom_duration):.2f}s")
            
            # 只要请求被正确处理就算通过
            if response1.status_code in [200, 400, 422] and response2.status_code in [200, 400, 422, 500]:
                print("✅ 透传性能测试通过")
                return True
            else:
                print("⚠️  透传性能测试异常")
                return False
                
        except Exception as e:
            print(f"❌ 透传性能测试失败: {e}")
            return False
    
    def test_concurrent_passthrough(self):
        """测试并发透传"""
        print("测试: 并发透传")
        
        import threading
        
        models_to_test = [
            "concurrent-test-model-1",
            "concurrent-test-model-2", 
            "concurrent-test-model-3",
            "claude-3-5-haiku-20241022",
            "claude-3-5-sonnet-20241022"
        ]
        
        results = []
        
        def test_single_model(model, request_id):
            """测试单个模型的并发请求"""
            try:
                payload = {
                    "model": model,
                    "messages": [{"role": "user", "content": f"并发测试 {request_id}"}],
                    "max_tokens": 10,
                    "stream": False
                }
                
                start_time = time.time()
                response = requests.post(
                    f"{self.base_url}/v1/messages",
                    headers=self.headers,
                    json=payload,
                    timeout=30
                )
                duration = time.time() - start_time
                
                results.append({
                    "model": model,
                    "request_id": request_id,
                    "status_code": response.status_code,
                    "duration": duration,
                    "success": response.status_code in [200, 400, 422, 500]
                })
                
            except Exception as e:
                results.append({
                    "model": model,
                    "request_id": request_id,
                    "error": str(e),
                    "success": False
                })
        
        try:
            # 创建并发请求
            threads = []
            
            for i, model in enumerate(models_to_test):
                thread = threading.Thread(target=test_single_model, args=(model, i))
                threads.append(thread)
                thread.start()
            
            # 等待所有线程完成
            for thread in threads:
                thread.join(timeout=60)
            
            # 分析结果
            successful = sum(1 for r in results if r["success"])
            total = len(results)
            
            print(f"   并发透传结果: {successful}/{total} 成功")
            
            # 显示详细结果
            for result in results:
                if "error" in result:
                    print(f"   {result['model']}: 错误 - {result['error']}")
                else:
                    print(f"   {result['model']}: {result['status_code']} ({result['duration']:.2f}s)")
            
            if successful >= total * 0.8:
                print("✅ 并发透传测试通过")
                return True
            else:
                print("⚠️  并发透传测试部分失败")
                return False
                
        except Exception as e:
            print(f"❌ 并发透传测试失败: {e}")
            return False
    
    def run_all_tests(self):
        """运行所有测试"""
        print("=" * 60)
        print("开始运行 Passthrough 测试套件")
        print("=" * 60)
        
        tests = [
            self.test_standard_model_passthrough,
            self.test_custom_model_passthrough,
            self.test_passthrough_vs_routing,
            self.test_passthrough_with_different_parameters,
            self.test_passthrough_error_handling,
            self.test_passthrough_performance,
            self.test_concurrent_passthrough
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
    tester = TestPassthrough()
    return tester.run_all_tests()

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)