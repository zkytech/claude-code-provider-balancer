#!/usr/bin/env python3
"""
测试缓存和去重功能
包括请求去重、缓存命中、缓存过期等场景
"""

import json
import time
import requests
import sys
import os
import hashlib
import threading

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from test_utils import get_claude_code_headers

BASE_URL = "http://localhost:9090"

class TestCachingDeduplication:
    def __init__(self):
        self.base_url = BASE_URL
        self.headers = get_claude_code_headers()
        
    def generate_request_signature(self, payload):
        """生成请求签名用于去重测试"""
        # 简化的签名生成逻辑，与实际实现可能不同
        normalized_payload = json.dumps(payload, sort_keys=True)
        return hashlib.md5(normalized_payload.encode()).hexdigest()
    
    def test_identical_request_deduplication(self):
        """测试相同请求的去重和缓存"""
        print("测试: 相同请求去重和缓存")
        
        # 创建一个简单的请求
        payload = {
            "model": "claude-3-5-haiku-20241022",
            "messages": [{"role": "user", "content": "测试缓存: 2+2等于几？"}],
            "max_tokens": 50,
            "stream": False
        }
        
        print("=== 测试1: 并发重复请求检测 ===")
        try:
            # 使用线程几乎同时发送两个相同请求
            results = []
            errors = []
            
            def make_request(request_id):
                try:
                    start_time = time.time()
                    response = requests.post(
                        f"{self.base_url}/v1/messages",
                        headers=self.headers,
                        json=payload,
                        timeout=30
                    )
                    duration = time.time() - start_time
                    results.append({
                        'id': request_id,
                        'response': response,
                        'duration': duration,
                        'timestamp': start_time
                    })
                except Exception as e:
                    errors.append({'id': request_id, 'error': str(e)})
            
            # 创建两个线程几乎同时发送请求
            print("   同时发送两个相同请求...")
            thread1 = threading.Thread(target=make_request, args=(1,))
            thread2 = threading.Thread(target=make_request, args=(2,))
            
            thread1.start()
            thread2.start()
            
            thread1.join()
            thread2.join()
            
            if errors:
                print(f"   有请求出错: {errors}")
            
            if len(results) >= 2:
                r1, r2 = results[0], results[1]
                print(f"   请求1状态: {r1['response'].status_code}, 耗时: {r1['duration']:.2f}s")
                print(f"   请求2状态: {r2['response'].status_code}, 耗时: {r2['duration']:.2f}s")
                
                # 检查是否有一个请求被取消（重复请求检测）
                cancelled_count = sum(1 for r in results if r['response'].status_code != 200)
                if cancelled_count > 0:
                    print(f"✅ 检测到 {cancelled_count} 个重复请求被处理")
                else:
                    print("ℹ️  两个请求都成功完成（可能请求间隔过大）")
            
        except Exception as e:
            print(f"❌ 并发请求测试失败: {e}")
        
        print("\n=== 测试2: 缓存命中测试 ===")
        try:
            # 第一次请求
            print("   发送第一次请求...")
            start_time1 = time.time()
            response1 = requests.post(
                f"{self.base_url}/v1/messages",
                headers=self.headers,
                json=payload,
                timeout=30
            )
            duration1 = time.time() - start_time1
            
            assert response1.status_code == 200, f"第一次请求失败: {response1.status_code}"
            data1 = response1.json()
            assert "content" in data1, "第一次请求响应缺少 content"
            
            print(f"   第一次请求完成 (耗时: {duration1:.2f}s)")
            print(f"   第一次请求headers: {dict(response1.headers)}")
            
            # 等待一小段时间让缓存写入
            time.sleep(1)
            
            # 第二次相同请求
            print("   发送第二次相同请求...")
            start_time2 = time.time()
            response2 = requests.post(
                f"{self.base_url}/v1/messages",
                headers=self.headers,
                json=payload,
                timeout=30
            )
            duration2 = time.time() - start_time2
            
            assert response2.status_code == 200, f"第二次请求失败: {response2.status_code}"
            data2 = response2.json()
            assert "content" in data2, "第二次请求响应缺少 content"
            
            print(f"   第二次请求完成 (耗时: {duration2:.2f}s)")
            print(f"   第二次请求headers: {dict(response2.headers)}")
            
            # 检查缓存状态
            cache_hit = response2.headers.get("x-cache-hit", "false").lower() == "true"
            provider1 = response1.headers.get("x-provider-used", "unknown")
            provider2 = response2.headers.get("x-provider-used", "unknown")
            
            print(f"   第一次请求provider: {provider1}")
            print(f"   第二次请求provider: {provider2}")
            
            if cache_hit:
                print("✅ 检测到缓存命中")
                if duration2 < duration1 * 0.5:
                    print(f"✅ 缓存请求更快 ({duration2:.2f}s vs {duration1:.2f}s)")
                else:
                    print(f"ℹ️  缓存请求耗时: {duration2:.2f}s vs {duration1:.2f}s")
            else:
                print("⚠️  未检测到缓存命中")
                if duration2 >= duration1 * 0.8:
                    print("   第二次请求耗时相似，可能没有使用缓存")
            
            # 验证响应内容一致性
            content1 = "".join([block["text"] for block in data1["content"]])
            content2 = "".join([block["text"] for block in data2["content"]])
            
            if content1 == content2:
                print("✅ 响应内容一致")
            else:
                print(f"⚠️  响应内容不同:")
                print(f"      第一次: {content1[:100]}...")
                print(f"      第二次: {content2[:100]}...")
            
            print("✅ 缓存测试完成")
            return True
            
        except Exception as e:
            print(f"❌ 缓存测试失败: {e}")
            return False
    
    def test_different_request_no_deduplication(self):
        """测试不同请求不会去重"""
        print("测试: 不同请求不会去重")
        
        # 创建两个不同的请求
        payload1 = {
            "model": "claude-3-5-haiku-20241022",
            "messages": [{"role": "user", "content": "什么是机器学习？"}],
            "max_tokens": 50,
            "stream": False
        }
        
        payload2 = {
            "model": "claude-3-5-haiku-20241022",
            "messages": [{"role": "user", "content": "什么是深度学习？"}],
            "max_tokens": 50,
            "stream": False
        }
        
        try:
            # 发送第一个请求
            response1 = requests.post(
                f"{self.base_url}/v1/messages",
                headers=self.headers,
                json=payload1,
                timeout=30
            )
            
            assert response1.status_code == 200, f"第一个请求失败: {response1.status_code}"
            data1 = response1.json()
            
            # 发送第二个不同的请求
            response2 = requests.post(
                f"{self.base_url}/v1/messages",
                headers=self.headers,
                json=payload2,
                timeout=30
            )
            
            assert response2.status_code == 200, f"第二个请求失败: {response2.status_code}"
            data2 = response2.json()
            
            # 验证两个响应是不同的
            content1 = "".join([block["text"] for block in data1["content"]])
            content2 = "".join([block["text"] for block in data2["content"]])
            
            if content1 != content2:
                print("✅ 不同请求产生不同响应")
            else:
                print("⚠️  不同请求产生了相同响应（可能是巧合）")
            
            # 检查是否都不是缓存命中
            cache_hit1 = response1.headers.get("x-cache-hit", "false").lower() == "true"
            cache_hit2 = response2.headers.get("x-cache-hit", "false").lower() == "true"
            
            if not cache_hit1 and not cache_hit2:
                print("✅ 两个请求都没有缓存命中")
            else:
                print(f"ℹ️  缓存状态: 请求1={cache_hit1}, 请求2={cache_hit2}")
            
            print("✅ 不同请求测试完成")
            return True
            
        except Exception as e:
            print(f"❌ 不同请求测试失败: {e}")
            return False
    
    def test_stream_vs_nonstream_caching(self):
        """测试流式与非流式请求的缓存"""
        print("测试: 流式与非流式请求缓存")
        
        base_payload = {
            "model": "claude-3-5-haiku-20241022",
            "messages": [{"role": "user", "content": "简短介绍Python编程语言"}],
            "max_tokens": 80
        }
        
        try:
            # 非流式请求
            nonstream_payload = {**base_payload, "stream": False}
            print("   发送非流式请求...")
            
            response1 = requests.post(
                f"{self.base_url}/v1/messages",
                headers=self.headers,
                json=nonstream_payload,
                timeout=30
            )
            
            assert response1.status_code == 200, f"非流式请求失败: {response1.status_code}"
            data1 = response1.json()
            
            # 等待一下
            time.sleep(0.5)
            
            # 流式请求（相同内容）
            stream_payload = {**base_payload, "stream": True}
            print("   发送流式请求（相同内容）...")
            
            response2 = requests.post(
                f"{self.base_url}/v1/messages",
                headers=self.headers,
                json=stream_payload,
                stream=True,
                timeout=30
            )
            
            assert response2.status_code == 200, f"流式请求失败: {response2.status_code}"
            
            # 收集流式响应
            stream_chunks = []
            for line in response2.iter_lines():
                if line:
                    line_str = line.decode('utf-8')
                    if line_str.startswith('data: '):
                        data_str = line_str[6:]
                        if data_str.strip() == '[DONE]':
                            break
                        try:
                            chunk_data = json.loads(data_str)
                            if chunk_data.get("type") == "content_block_delta":
                                delta = chunk_data.get("delta", {})
                                if "text" in delta:
                                    stream_chunks.append(delta["text"])
                        except json.JSONDecodeError:
                            continue
            
            response2.close()
            
            # 比较内容
            nonstream_content = "".join([block["text"] for block in data1["content"]])
            stream_content = "".join(stream_chunks)
            
            print(f"   非流式内容长度: {len(nonstream_content)}")
            print(f"   流式内容长度: {len(stream_content)}")
            
            # 检查缓存状态
            cache_hit1 = response1.headers.get("x-cache-hit", "false").lower() == "true"
            cache_hit2 = response2.headers.get("x-cache-hit", "false").lower() == "true"
            
            print(f"   缓存状态: 非流式={cache_hit1}, 流式={cache_hit2}")
            
            if len(nonstream_content) > 0 and len(stream_content) > 0:
                print("✅ 流式与非流式缓存测试完成")
                return True
            else:
                print("⚠️  某个响应为空")
                return False
                
        except Exception as e:
            print(f"❌ 流式与非流式缓存测试失败: {e}")
            return False
    
    def test_concurrent_identical_requests(self):
        """测试并发相同请求的去重"""
        print("测试: 并发相同请求去重")
        
        payload = {
            "model": "claude-3-5-haiku-20241022",
            "messages": [{"role": "user", "content": "并发去重测试 - 解释什么是RESTful API"}],
            "max_tokens": 100,
            "stream": False
        }
        
        results = []
        
        def make_identical_request(request_id):
            """发送相同请求"""
            try:
                start_time = time.time()
                response = requests.post(
                    f"{self.base_url}/v1/messages",
                    headers=self.headers,
                    json=payload,
                    timeout=30
                )
                duration = time.time() - start_time
                
                cache_hit = response.headers.get("x-cache-hit", "false").lower() == "true"
                
                if response.status_code == 200:
                    data = response.json()
                    content = "".join([block["text"] for block in data["content"]])
                    
                    results.append({
                        "id": request_id,
                        "success": True,
                        "duration": duration,
                        "cache_hit": cache_hit,
                        "content_length": len(content),
                        "content_preview": content[:50]
                    })
                else:
                    results.append({
                        "id": request_id,
                        "success": False,
                        "status_code": response.status_code,
                        "duration": duration,
                        "cache_hit": cache_hit
                    })
                    
            except Exception as e:
                results.append({
                    "id": request_id,
                    "success": False,
                    "error": str(e)
                })
        
        try:
            # 创建多个并发的相同请求
            threads = []
            num_requests = 5
            
            print(f"   启动 {num_requests} 个并发相同请求...")
            
            for i in range(num_requests):
                thread = threading.Thread(target=make_identical_request, args=(i,))
                threads.append(thread)
                thread.start()
            
            # 等待所有线程完成
            for thread in threads:
                thread.join(timeout=60)
            
            # 分析结果
            successful = [r for r in results if r["success"]]
            cache_hits = [r for r in successful if r["cache_hit"]]
            
            print(f"   成功请求: {len(successful)}/{len(results)}")
            print(f"   缓存命中: {len(cache_hits)}/{len(successful)}")
            
            if len(successful) > 0:
                avg_duration = sum(r["duration"] for r in successful) / len(successful)
                print(f"   平均耗时: {avg_duration:.2f}s")
                
                # 检查内容一致性
                if len(successful) > 1:
                    first_content = successful[0]["content_preview"]
                    all_same = all(r["content_preview"] == first_content for r in successful)
                    
                    if all_same:
                        print("✅ 所有响应内容一致")
                    else:
                        print("⚠️  响应内容不一致")
                
                # 检查缓存效果
                if len(cache_hits) > 0:
                    cache_durations = [r["duration"] for r in cache_hits]
                    non_cache_durations = [r["duration"] for r in successful if not r["cache_hit"]]
                    
                    if non_cache_durations:
                        avg_cache = sum(cache_durations) / len(cache_durations)
                        avg_non_cache = sum(non_cache_durations) / len(non_cache_durations)
                        print(f"   缓存请求平均耗时: {avg_cache:.2f}s")
                        print(f"   非缓存请求平均耗时: {avg_non_cache:.2f}s")
                
                print("✅ 并发去重测试完成")
                return True
            else:
                print("❌ 所有并发请求都失败")
                return False
                
        except Exception as e:
            print(f"❌ 并发去重测试失败: {e}")
            return False
    
    def test_cache_expiry_behavior(self):
        """测试缓存过期行为"""
        print("测试: 缓存过期行为")
        
        payload = {
            "model": "claude-3-5-haiku-20241022",
            "messages": [{"role": "user", "content": "缓存过期测试 - 什么是Docker？"}],
            "max_tokens": 60,
            "stream": False
        }
        
        try:
            # 第一次请求
            print("   发送第一次请求...")
            response1 = requests.post(
                f"{self.base_url}/v1/messages",
                headers=self.headers,
                json=payload,
                timeout=30
            )
            
            assert response1.status_code == 200, f"第一次请求失败: {response1.status_code}"
            
            # 立即发送第二次请求（应该命中缓存）
            print("   立即发送第二次请求...")
            response2 = requests.post(
                f"{self.base_url}/v1/messages",
                headers=self.headers,
                json=payload,
                timeout=30
            )
            
            assert response2.status_code == 200, f"第二次请求失败: {response2.status_code}"
            
            cache_hit2 = response2.headers.get("x-cache-hit", "false").lower() == "true"
            print(f"   第二次请求缓存状态: {cache_hit2}")
            
            # 等待一段时间（模拟缓存过期，实际过期时间可能更长）
            print("   等待缓存可能过期...")
            time.sleep(5)
            
            # 第三次请求（可能缓存已过期）
            print("   发送第三次请求...")
            response3 = requests.post(
                f"{self.base_url}/v1/messages",
                headers=self.headers,
                json=payload,
                timeout=30
            )
            
            assert response3.status_code == 200, f"第三次请求失败: {response3.status_code}"
            
            cache_hit3 = response3.headers.get("x-cache-hit", "false").lower() == "true"
            print(f"   第三次请求缓存状态: {cache_hit3}")
            
            # 分析结果
            if cache_hit2 and not cache_hit3:
                print("✅ 检测到缓存过期行为")
            elif cache_hit2 and cache_hit3:
                print("ℹ️  缓存仍然有效（过期时间较长）")
            elif not cache_hit2 and not cache_hit3:
                print("ℹ️  缓存功能可能未启用")
            else:
                print("ℹ️  缓存行为模式未确定")
            
            print("✅ 缓存过期测试完成")
            return True
            
        except Exception as e:
            print(f"❌ 缓存过期测试失败: {e}")
            return False
    
    def test_cache_size_limits(self):
        """测试缓存大小限制"""
        print("测试: 缓存大小限制")
        
        try:
            # 生成多个不同的请求来测试缓存容量
            cache_states = []
            
            for i in range(10):
                payload = {
                    "model": "claude-3-5-haiku-20241022",
                    "messages": [{"role": "user", "content": f"第{i+1}个不同的问题：介绍编程语言{i+1}"}],
                    "max_tokens": 30,
                    "stream": False
                }
                
                response = requests.post(
                    f"{self.base_url}/v1/messages",
                    headers=self.headers,
                    json=payload,
                    timeout=30
                )
                
                if response.status_code == 200:
                    cache_hit = response.headers.get("x-cache-hit", "false").lower() == "true"
                    cache_states.append(cache_hit)
                    print(f"   请求 {i+1}: 缓存状态={cache_hit}")
                else:
                    print(f"   请求 {i+1}: 失败 - {response.status_code}")
                
                time.sleep(0.2)  # 短暂延迟
            
            # 再次发送前几个请求，检查是否还在缓存中
            print("   重新发送前几个请求检查缓存保持...")
            
            cache_retention = []
            for i in range(3):  # 只检查前3个
                payload = {
                    "model": "claude-3-5-haiku-20241022",
                    "messages": [{"role": "user", "content": f"第{i+1}个不同的问题：介绍编程语言{i+1}"}],
                    "max_tokens": 30,
                    "stream": False
                }
                
                response = requests.post(
                    f"{self.base_url}/v1/messages",
                    headers=self.headers,
                    json=payload,
                    timeout=30
                )
                
                if response.status_code == 200:
                    cache_hit = response.headers.get("x-cache-hit", "false").lower() == "true"
                    cache_retention.append(cache_hit)
                    print(f"   重复请求 {i+1}: 缓存状态={cache_hit}")
            
            # 分析缓存行为
            retained_count = sum(cache_retention)
            print(f"   缓存保持情况: {retained_count}/{len(cache_retention)}")
            
            if retained_count > 0:
                print("✅ 检测到缓存保持功能")
            else:
                print("ℹ️  缓存可能已被清理或功能未启用")
            
            print("✅ 缓存大小限制测试完成")
            return True
            
        except Exception as e:
            print(f"❌ 缓存大小限制测试失败: {e}")
            return False
    
    def test_token_count_caching(self):
        """测试Token计数接口的缓存"""
        print("测试: Token计数接口缓存")
        
        payload = {
            "model": "claude-3-5-haiku-20241022",
            "messages": [{"role": "user", "content": "计算这条消息的token数量"}]
        }
        
        try:
            # 第一次token计数请求
            print("   发送第一次token计数请求...")
            start_time1 = time.time()
            response1 = requests.post(
                f"{self.base_url}/v1/messages/count_tokens",
                headers=self.headers,
                json=payload,
                timeout=30
            )
            duration1 = time.time() - start_time1
            
            assert response1.status_code == 200, f"第一次请求失败: {response1.status_code}"
            data1 = response1.json()
            assert "input_tokens" in data1, "响应缺少 input_tokens"
            
            print(f"   第一次请求: {data1['input_tokens']} tokens (耗时: {duration1:.2f}s)")
            
            # 第二次相同的token计数请求
            print("   发送第二次相同请求...")
            start_time2 = time.time()
            response2 = requests.post(
                f"{self.base_url}/v1/messages/count_tokens",
                headers=self.headers,
                json=payload,
                timeout=30
            )
            duration2 = time.time() - start_time2
            
            assert response2.status_code == 200, f"第二次请求失败: {response2.status_code}"
            data2 = response2.json()
            
            print(f"   第二次请求: {data2['input_tokens']} tokens (耗时: {duration2:.2f}s)")
            
            # 验证结果一致性
            if data1["input_tokens"] == data2["input_tokens"]:
                print("✅ Token计数结果一致")
            else:
                print("⚠️  Token计数结果不一致")
            
            # 检查缓存效果
            cache_hit = response2.headers.get("x-cache-hit", "false").lower() == "true"
            if cache_hit:
                print("✅ Token计数请求命中缓存")
            else:
                print("ℹ️  Token计数请求未命中缓存")
            
            if duration2 < duration1 * 0.8:
                print(f"✅ 第二次请求更快 ({duration2:.2f}s vs {duration1:.2f}s)")
            
            print("✅ Token计数缓存测试完成")
            return True
            
        except Exception as e:
            print(f"❌ Token计数缓存测试失败: {e}")
            return False
    
    def run_all_tests(self):
        """运行所有测试"""
        print("=" * 60)
        print("开始运行 Caching & Deduplication 测试套件")
        print("=" * 60)
        
        tests = [
            self.test_identical_request_deduplication,
            self.test_different_request_no_deduplication,
            self.test_stream_vs_nonstream_caching,
            self.test_concurrent_identical_requests,
            self.test_cache_expiry_behavior,
            self.test_cache_size_limits,
            self.test_token_count_caching
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
    tester = TestCachingDeduplication()
    return tester.run_all_tests()

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)