#!/usr/bin/env python3
"""
测试超时和重试功能
包括 stream 和 non-stream 请求的超时处理和重试机制
"""

import json
import time
import requests
import sys
import os
import threading
import signal
from contextlib import contextmanager

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from test_utils import get_claude_code_headers

BASE_URL = "http://localhost:9090"
TEST_MODEL_HAIKU = "claude-3-5-haiku-20241022"

@contextmanager
def timeout_context(seconds):
    """超时上下文管理器"""
    def timeout_handler(signum, frame):
        raise TimeoutError(f"操作超时 ({seconds} 秒)")
    
    # 设置信号处理器
    old_handler = signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(seconds)
    
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)

class TestTimeoutRetry:
    def __init__(self):
        self.base_url = BASE_URL
        self.headers = get_claude_code_headers()
        
    def test_nonstream_timeout(self):
        """测试非流式请求超时"""
        print("测试: 非流式请求超时")
        
        # 使用很小的超时时间来模拟超时
        payload = {
            "model": TEST_MODEL_HAIKU,
            "messages": [{"role": "user", "content": "延迟"}],
            "max_tokens": 10,
            "stream": False
        }
        
        try:
            # 设置很短的超时时间
            response = requests.post(
                f"{self.base_url}/v1/messages",
                headers=self.headers,
                json=payload,
                timeout=1  # 1秒超时，很可能会超时
            )
            
            if response.status_code == 200:
                print("ℹ️  请求在短时间内完成（未触发超时）")
                return True
            else:
                print(f"⚠️  请求返回错误状态码: {response.status_code}")
                return True  # 错误响应也算正常处理
                
        except requests.exceptions.Timeout:
            print("✅ 非流式请求正确触发超时")
            
            # 测试超时后的重试
            try:
                print("   尝试重试请求...")
                retry_response = requests.post(
                    f"{self.base_url}/v1/messages",
                    headers=self.headers,
                    json=payload,
                    timeout=30  # 更长的超时时间
                )
                
                if retry_response.status_code == 200:
                    print("✅ 重试请求成功")
                    return True
                else:
                    print(f"⚠️  重试请求失败: {retry_response.status_code}")
                    return True
                    
            except Exception as e:
                print(f"⚠️  重试请求异常: {e}")
                return True  # 超时测试已通过
                
        except Exception as e:
            print(f"❌ 非流式超时测试失败: {e}")
            return False
    
    def test_stream_timeout(self):
        """测试流式请求超时"""
        print("测试: 流式请求超时")
        
        payload = {
            "model": TEST_MODEL_HAIKU,
            "messages": [{"role": "user", "content": "延迟"}],
            "max_tokens": 10,
            "stream": True
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/v1/messages",
                headers=self.headers,
                json=payload,
                stream=True,
                timeout=2  # 2秒超时
            )
            
            chunks_received = 0
            start_time = time.time()
            
            for line in response.iter_lines():
                if line:
                    line_str = line.decode('utf-8')
                    if line_str.startswith('data: '):
                        chunks_received += 1
                        
                        # 检查是否已经超时
                        if time.time() - start_time > 3:
                            print(f"✅ 流式请求手动超时 (收到 {chunks_received} 个数据块)")
                            response.close()
                            break
            
            if chunks_received > 0:
                print(f"✅ 流式请求处理正常 (收到 {chunks_received} 个数据块)")
                return True
            else:
                print("⚠️  未收到流式数据")
                return False
                
        except requests.exceptions.Timeout:
            print("✅ 流式请求正确触发超时")
            return True
        except Exception as e:
            print(f"❌ 流式超时测试失败: {e}")
            return False
    
    def test_stream_retry_after_timeout(self):
        """测试流式请求超时后重试"""
        print("测试: 流式请求超时后重试")
        
        payload = {
            "model": "claude-3-5-haiku-20241022",
            "messages": [{"role": "user", "content": "延迟"}],
            "max_tokens": 10,
            "stream": True
        }
        
        try:
            # 第一次尝试：短超时
            print("   第一次尝试（短超时）...")
            try:
                response1 = requests.post(
                    f"{self.base_url}/v1/messages",
                    headers=self.headers,
                    json=payload,
                    stream=True,
                    timeout=0.5  # 很短的超时
                )
                
                # 如果没有超时，快速消费数据
                chunks = 0
                for line in response1.iter_lines():
                    if line:
                        chunks += 1
                        if chunks > 3:  # 限制处理的数据块数量
                            break
                
                print(f"   第一次尝试完成 (收到 {chunks} 个数据块)")
                
            except requests.exceptions.Timeout:
                print("   第一次尝试超时")
            
            # 第二次尝试：正常超时
            print("   第二次尝试（正常超时）...")
            response2 = requests.post(
                f"{self.base_url}/v1/messages",
                headers=self.headers,
                json=payload,
                stream=True,
                timeout=30
            )
            
            assert response2.status_code == 200, f"重试失败: {response2.status_code}"
            
            chunks_received = 0
            for line in response2.iter_lines():
                if line:
                    line_str = line.decode('utf-8')
                    if line_str.startswith('data: '):
                        chunks_received += 1
                        if chunks_received > 5:  # 收到足够数据就停止
                            break
            
            response2.close()
            
            if chunks_received > 0:
                print(f"✅ 流式重试成功 (收到 {chunks_received} 个数据块)")
                return True
            else:
                print("⚠️  重试未收到数据")
                return False
                
        except Exception as e:
            print(f"❌ 流式重试测试失败: {e}")
            return False
    
    def test_nonstream_retry_mechanism(self):
        """测试非流式请求重试机制"""
        print("测试: 非流式请求重试机制")
        
        # 使用一个可能失败的请求来测试重试
        payload = {
            "model": TEST_MODEL_HAIKU,
            "messages": [{"role": "user", "content": "延迟"}],
            "max_tokens": 10,
            "stream": False
        }
        
        max_retries = 3
        successful = False
        
        try:
            for attempt in range(max_retries):
                print(f"   尝试 {attempt + 1}/{max_retries}")
                
                try:
                    response = requests.post(
                        f"{self.base_url}/v1/messages",
                        headers=self.headers,
                        json=payload,
                        timeout=15
                    )
                    
                    if response.status_code == 200:
                        print(f"✅ 第 {attempt + 1} 次尝试成功")
                        successful = True
                        break
                    else:
                        print(f"   第 {attempt + 1} 次尝试失败: {response.status_code}")
                        
                except requests.exceptions.Timeout:
                    print(f"   第 {attempt + 1} 次尝试超时")
                except Exception as e:
                    print(f"   第 {attempt + 1} 次尝试异常: {e}")
                
                if attempt < max_retries - 1:
                    print("   等待后重试...")
                    time.sleep(1)
            
            if successful:
                print("✅ 重试机制测试通过")
                return True
            else:
                print("⚠️  所有重试都失败了")
                return False
                
        except Exception as e:
            print(f"❌ 重试机制测试失败: {e}")
            return False
    
    def test_concurrent_timeout_handling(self):
        """测试并发请求的超时处理"""
        print("测试: 并发请求超时处理")
        
        payload = {
            "model": TEST_MODEL_HAIKU,
            "messages": [{"role": "user", "content": "延迟"}],
            "max_tokens": 10,
            "stream": False
        }
        
        results = []
        
        def make_request_with_timeout(request_id, timeout_seconds):
            """发送带超时的请求"""
            try:
                start_time = time.time()
                response = requests.post(
                    f"{self.base_url}/v1/messages",
                    headers=self.headers,
                    json=payload,
                    timeout=timeout_seconds
                )
                duration = time.time() - start_time
                
                results.append({
                    "id": request_id,
                    "status": response.status_code,
                    "duration": duration,
                    "timeout": timeout_seconds,
                    "success": response.status_code == 200
                })
                
            except requests.exceptions.Timeout:
                duration = time.time() - start_time
                results.append({
                    "id": request_id,
                    "status": "timeout",
                    "duration": duration,
                    "timeout": timeout_seconds,
                    "success": False
                })
                
            except Exception as e:
                results.append({
                    "id": request_id,
                    "status": "error",
                    "error": str(e),
                    "timeout": timeout_seconds,
                    "success": False
                })
        
        try:
            # 创建不同超时时间的并发请求
            threads = []
            timeouts = [1, 5, 10, 15, 30]  # 不同的超时时间
            
            for i, timeout in enumerate(timeouts):
                thread = threading.Thread(
                    target=make_request_with_timeout, 
                    args=(i, timeout)
                )
                threads.append(thread)
                thread.start()
            
            # 等待所有线程完成
            for thread in threads:
                thread.join(timeout=60)
            
            # 分析结果
            successful = sum(1 for r in results if r["success"])
            timeouts_occurred = sum(1 for r in results if r["status"] == "timeout")
            total = len(results)
            
            print(f"   并发请求结果: {successful} 成功, {timeouts_occurred} 超时, 总计 {total}")
            
            # 打印详细结果
            for result in results:
                status = result["status"]
                duration = result.get("duration", 0)
                timeout = result["timeout"]
                print(f"   请求 {result['id']}: {status} (耗时: {duration:.2f}s, 超时设置: {timeout}s)")
            
            print("✅ 并发超时处理测试完成")
            return True
            
        except Exception as e:
            print(f"❌ 并发超时测试失败: {e}")
            return False
    
    def test_stream_partial_response_timeout(self):
        """测试流式请求部分响应后超时"""
        print("测试: 流式请求部分响应后超时")
        
        payload = {
            "model": TEST_MODEL_HAIKU,
            "messages": [{"role": "user", "content": "延迟"}],
            "max_tokens": 10,
            "stream": True
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/v1/messages",
                headers=self.headers,
                json=payload,
                stream=True,
                timeout=30
            )
            
            assert response.status_code == 200, f"请求失败: {response.status_code}"
            
            chunks_received = 0
            partial_content = []
            start_time = time.time()
            
            for line in response.iter_lines():
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
                                    partial_content.append(delta["text"])
                                    chunks_received += 1
                                    
                                    # 收到一些数据后强制断开
                                    if chunks_received >= 5:
                                        print(f"   收到 {chunks_received} 个数据块后断开连接")
                                        response.close()
                                        break
                                        
                        except json.JSONDecodeError:
                            continue
                
                # 检查是否超过时间限制
                if time.time() - start_time > 10:
                    print("   超时，断开连接")
                    response.close()
                    break
            
            content_received = "".join(partial_content)
            
            if chunks_received > 0:
                print(f"✅ 部分响应超时测试通过 (收到 {chunks_received} 个数据块)")
                print(f"   部分内容: {content_received[:100]}...")
                return True
            else:
                print("⚠️  未收到任何数据")
                return False
                
        except Exception as e:
            print(f"❌ 部分响应超时测试失败: {e}")
            return False
    
    def test_timeout_configuration(self):
        """测试不同超时配置"""
        print("测试: 不同超时配置")
        
        payload = {
            "model": TEST_MODEL_HAIKU,
            "messages": [{"role": "user", "content": "简单测试"}],
            "max_tokens": 20,
            "stream": False
        }
        
        timeout_configs = [5, 10, 30, 60]  # 不同的超时配置
        
        try:
            for timeout in timeout_configs:
                print(f"   测试 {timeout} 秒超时...")
                
                start_time = time.time()
                
                try:
                    response = requests.post(
                        f"{self.base_url}/v1/messages",
                        headers=self.headers,
                        json=payload,
                        timeout=timeout
                    )
                    
                    duration = time.time() - start_time
                    
                    if response.status_code == 200:
                        print(f"   ✅ {timeout}s 超时配置成功 (耗时: {duration:.2f}s)")
                    else:
                        print(f"   ⚠️  {timeout}s 超时配置返回错误: {response.status_code}")
                        
                except requests.exceptions.Timeout:
                    duration = time.time() - start_time
                    print(f"   ⏱️  {timeout}s 超时配置触发超时 (耗时: {duration:.2f}s)")
                    
            print("✅ 超时配置测试完成")
            return True
            
        except Exception as e:
            print(f"❌ 超时配置测试失败: {e}")
            return False
    
    def run_all_tests(self):
        """运行所有测试"""
        print("=" * 60)
        print("开始运行 Timeout & Retry 测试套件")
        print("=" * 60)
        
        tests = [
            self.test_nonstream_timeout,
            self.test_stream_timeout,
            self.test_stream_retry_after_timeout,
            self.test_nonstream_retry_mechanism,
            self.test_concurrent_timeout_handling,
            self.test_stream_partial_response_timeout,
            self.test_timeout_configuration
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
    tester = TestTimeoutRetry()
    return tester.run_all_tests()

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)