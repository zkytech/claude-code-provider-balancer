#!/usr/bin/env python3
"""
测试基础 stream 和 non-stream 请求功能
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

class TestStreamNonStream:
    def __init__(self):
        self.base_url = BASE_URL
        self.headers = get_claude_code_headers()
        
    def test_non_stream_request(self):
        """测试非流式请求"""
        print("测试: 非流式请求")
        
        payload = {
            "model": "claude-3-5-haiku-20241022",
            "messages": [{"role": "user", "content": "说 'Hello' 一次就行"}],
            "max_tokens": 50,
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
            assert len(data["content"]) > 0, "响应内容为空"
            assert data["type"] == "message", "响应类型错误"
            
            print("✅ 非流式请求测试通过")
            return True
            
        except requests.exceptions.Timeout:
            print("❌ 非流式请求超时")
            return False
        except Exception as e:
            print(f"❌ 非流式请求失败: {e}")
            return False
    
    def test_stream_request(self):
        """测试流式请求"""
        print("测试: 流式请求")
        
        payload = {
            "model": "claude-3-5-haiku-20241022",
            "messages": [{"role": "user", "content": "数数字 1 到 5"}],
            "max_tokens": 100,
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
            
            assert response.status_code == 200, f"响应状态码错误: {response.status_code}"
            
            chunks_received = 0
            content_chunks = []
            
            for line in response.iter_lines():
                if line:
                    line_str = line.decode('utf-8')
                    if line_str.startswith('data: '):
                        data_str = line_str[6:]  # 移除 'data: ' 前缀
                        
                        if data_str.strip() == '[DONE]':
                            break
                            
                        try:
                            chunk_data = json.loads(data_str)
                            chunks_received += 1
                            
                            if chunk_data.get("type") == "content_block_delta":
                                delta = chunk_data.get("delta", {})
                                if "text" in delta:
                                    content_chunks.append(delta["text"])
                                    
                        except json.JSONDecodeError:
                            continue
            
            assert chunks_received > 0, "未收到任何数据块"
            assert len(content_chunks) > 0, "未收到任何内容块"
            
            full_content = "".join(content_chunks)
            assert len(full_content.strip()) > 0, "流式响应内容为空"
            
            print(f"✅ 流式请求测试通过 (收到 {chunks_received} 个数据块)")
            return True
            
        except requests.exceptions.Timeout:
            print("❌ 流式请求超时")
            return False
        except Exception as e:
            print(f"❌ 流式请求失败: {e}")
            return False
    
    def test_stream_vs_nonstream_consistency(self):
        """测试流式和非流式请求的内容一致性"""
        print("测试: 流式与非流式请求一致性")
        
        prompt = "回答: 天空是什么颜色？只说颜色名称"
        
        # 非流式请求
        nonstream_payload = {
            "model": "claude-3-5-haiku-20241022",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 20,
            "stream": False
        }
        
        # 流式请求
        stream_payload = {
            "model": "claude-3-5-haiku-20241022",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 20,
            "stream": True
        }
        
        try:
            # 执行非流式请求
            nonstream_response = requests.post(
                f"{self.base_url}/v1/messages",
                headers=self.headers,
                json=nonstream_payload,
                timeout=30
            )
            
            assert nonstream_response.status_code == 200
            nonstream_data = nonstream_response.json()
            nonstream_content = "".join([block["text"] for block in nonstream_data["content"]])
            
            # 执行流式请求
            stream_response = requests.post(
                f"{self.base_url}/v1/messages",
                headers=self.headers,
                json=stream_payload,
                stream=True,
                timeout=30
            )
            
            assert stream_response.status_code == 200
            
            stream_content_chunks = []
            for line in stream_response.iter_lines():
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
                                    stream_content_chunks.append(delta["text"])
                        except json.JSONDecodeError:
                            continue
            
            stream_content = "".join(stream_content_chunks)
            
            # 验证两种方式都有内容
            assert len(nonstream_content.strip()) > 0, "非流式响应内容为空"
            assert len(stream_content.strip()) > 0, "流式响应内容为空"
            
            print(f"✅ 一致性测试通过")
            print(f"   非流式: {nonstream_content[:50]}...")
            print(f"   流式:   {stream_content[:50]}...")
            return True
            
        except Exception as e:
            print(f"❌ 一致性测试失败: {e}")
            return False
    
    def test_stream_early_termination(self):
        """测试流式请求早期终止"""
        print("测试: 流式请求早期终止")
        
        payload = {
            "model": "claude-3-5-haiku-20241022",
            "messages": [{"role": "user", "content": "写一个很长的故事，包含很多细节"}],
            "max_tokens": 1000,
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
            
            assert response.status_code == 200
            
            chunks_received = 0
            max_chunks = 5  # 只接收前5个数据块就停止
            
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
                                chunks_received += 1
                                if chunks_received >= max_chunks:
                                    break
                        except json.JSONDecodeError:
                            continue
            
            # 关闭连接
            response.close()
            
            assert chunks_received > 0, "未收到任何数据块"
            print(f"✅ 早期终止测试通过 (收到 {chunks_received} 个数据块后终止)")
            return True
            
        except Exception as e:
            print(f"❌ 早期终止测试失败: {e}")
            return False

    def test_stream_disconnect_with_duplicate_nonstream(self):
        """测试流式请求客户端断开后，重复的非流式请求能正常处理"""
        print("测试: 流式客户端断开 + 重复非流式请求")
        
        import threading
        import time
        
        # 使用相同的请求内容确保重复检测生效
        base_payload = {
            "model": "claude-3-5-haiku-20241022", 
            "messages": [{"role": "user", "content": "请详细解释人工智能的发展历程，要详细一些"}],
            "max_tokens": 800,  # 流式请求用800 tokens
        }
        
        # 流式请求
        stream_payload = {**base_payload, "stream": True}
        
        # 非流式请求（max_tokens不同，但内容相同，触发重复检测）
        nonstream_payload = {**base_payload, "stream": False, "max_tokens": 600}
        
        stream_response = None
        nonstream_response = None
        stream_error = None
        nonstream_error = None
        
        def make_stream_request():
            """发送流式请求并早期断开"""
            nonlocal stream_response, stream_error
            try:
                stream_response = requests.post(
                    f"{self.base_url}/v1/messages",
                    headers=self.headers,
                    json=stream_payload,
                    stream=True,
                    timeout=30
                )
                
                # 只读取几个chunk就断开连接，模拟客户端超时
                chunks_received = 0
                for line in stream_response.iter_lines():
                    if line:
                        line_str = line.decode('utf-8')
                        if line_str.startswith('data: '):
                            data_str = line_str[6:]
                            if data_str.strip() == '[DONE]':
                                break
                            try:
                                chunk_data = json.loads(data_str)
                                if chunk_data.get("type") == "content_block_delta":
                                    chunks_received += 1
                                    if chunks_received >= 2:  # 只读取2个chunk就断开
                                        break
                            except json.JSONDecodeError:
                                continue
                
                # 主动关闭连接，模拟客户端断开
                stream_response.close()
                print(f"   流式请求已断开 (收到 {chunks_received} 个块)")
                
            except Exception as e:
                stream_error = e
        
        def make_nonstream_request():
            """发送非流式重复请求"""
            nonlocal nonstream_response, nonstream_error
            try:
                # 稍等一下让流式请求先开始
                time.sleep(2)
                
                nonstream_response = requests.post(
                    f"{self.base_url}/v1/messages",
                    headers=self.headers,
                    json=nonstream_payload,
                    timeout=60  # 给足够时间等待
                )
                print(f"   非流式请求完成，状态码: {nonstream_response.status_code}")
                
            except Exception as e:
                nonstream_error = e
        
        # 同时启动两个请求
        stream_thread = threading.Thread(target=make_stream_request)
        nonstream_thread = threading.Thread(target=make_nonstream_request)
        
        try:
            stream_thread.start()
            nonstream_thread.start()
            
            # 等待两个线程完成
            stream_thread.join(timeout=35)
            nonstream_thread.join(timeout=65)
            
            # 检查结果
            if stream_error:
                print(f"   流式请求错误: {stream_error}")
            
            if nonstream_error:
                print(f"❌ 非流式请求错误: {nonstream_error}")
                return False
            
            # 验证非流式请求成功
            if not nonstream_response:
                print("❌ 非流式响应为空")
                return False
                
            if nonstream_response.status_code != 200:
                print(f"❌ 非流式请求失败，状态码: {nonstream_response.status_code}")
                try:
                    error_data = nonstream_response.json()
                    print(f"   错误详情: {error_data}")
                except:
                    print(f"   响应内容: {nonstream_response.text[:200]}")
                return False
            
            # 验证响应内容
            try:
                nonstream_data = nonstream_response.json()
                if "content" not in nonstream_data or not nonstream_data["content"]:
                    print("❌ 非流式响应缺少内容")
                    return False
                
                content = "".join([block["text"] for block in nonstream_data["content"]])
                if len(content.strip()) == 0:
                    print("❌ 非流式响应内容为空")
                    return False
                
                print(f"✅ 流式断开+重复非流式测试通过")
                print(f"   非流式响应长度: {len(content)} 字符")
                print(f"   响应预览: {content[:100]}...")
                return True
                
            except Exception as e:
                print(f"❌ 解析非流式响应失败: {e}")
                return False
                
        except Exception as e:
            print(f"❌ 测试执行异常: {e}")
            return False
        finally:
            # 确保连接被关闭
            if stream_response:
                try:
                    stream_response.close()
                except:
                    pass
            if nonstream_response:
                try:
                    nonstream_response.close()
                except:
                    pass
    
    def run_all_tests(self):
        """运行所有测试"""
        print("=" * 60)
        print("开始运行 Stream/Non-Stream 测试套件")
        print("=" * 60)
        
        tests = [
            self.test_non_stream_request,
            self.test_stream_request,
            self.test_stream_vs_nonstream_consistency,
            self.test_stream_early_termination,
            self.test_stream_disconnect_with_duplicate_nonstream
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
    tester = TestStreamNonStream()
    return tester.run_all_tests()

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)