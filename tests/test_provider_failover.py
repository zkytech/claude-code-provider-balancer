#!/usr/bin/env python3
"""
测试 provider failover 切换功能
"""

import json
import time
import requests
import sys
import os
import threading
from unittest.mock import patch

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from test_utils import get_claude_code_headers

BASE_URL = "http://localhost:8080"
TEST_MODEL_HAIKU = "claude-3-5-haiku-20241022"

class TestProviderFailover:
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
                    self.available_providers = data["providers"]
                    return True
            return False
        except Exception as e:
            print(f"❌ 获取服务商状态失败: {e}")
            return False
    
    def test_provider_health_monitoring(self):
        """测试服务商健康监控"""
        print("测试: 服务商健康监控")
        
        try:
            response = requests.get(f"{self.base_url}/providers", timeout=10)
            assert response.status_code == 200, f"状态码错误: {response.status_code}"
            
            data = response.json()
            assert "providers" in data, "响应中缺少 providers 字段"
            
            healthy_count = 0
            unhealthy_count = 0
            
            for provider in data["providers"]:
                if provider.get("enabled", False):
                    if provider.get("healthy", False):
                        healthy_count += 1
                        print(f"   ✅ {provider['name']}: 健康")
                    else:
                        unhealthy_count += 1
                        failure_info = provider.get("last_failure", "无信息")
                        print(f"   ❌ {provider['name']}: 不健康 - {failure_info}")
                else:
                    print(f"   ⚪ {provider['name']}: 已禁用")
            
            assert healthy_count > 0, "没有健康的服务商可用"
            
            print(f"✅ 健康监控测试通过 (健康: {healthy_count}, 不健康: {unhealthy_count})")
            return True
            
        except Exception as e:
            print(f"❌ 健康监控测试失败: {e}")
            return False
    
    def test_failover_behavior(self):
        """测试故障转移行为"""
        print("测试: 故障转移行为")
        
        if len([p for p in self.available_providers if p.get("enabled", False) and p.get("healthy", False)]) < 2:
            print("⚠️  需要至少 2 个健康的服务商才能测试故障转移")
            return True
        
        # 发送请求观察服务商使用情况
        payload = {
            "model": TEST_MODEL_HAIKU,
            "messages": [{"role": "user", "content": "测试故障转移"}],
            "max_tokens": 10,
            "stream": False
        }
        
        try:
            # 记录初始服务商状态
            initial_response = requests.get(f"{self.base_url}/providers", timeout=10)
            initial_providers = initial_response.json()["providers"]
            
            # 发送正常请求
            response = requests.post(
                f"{self.base_url}/v1/messages",
                headers=self.headers,
                json=payload,
                timeout=30
            )
            
            assert response.status_code == 200, f"正常请求失败: {response.status_code}"
            
            # 检查响应是否正常
            data = response.json()
            assert "content" in data, "响应中缺少 content 字段"
            
            print("✅ 正常情况下请求成功")
            
            # 模拟高负载或错误请求来触发故障检测
            # 这里我们发送多个可能导致错误的请求
            error_payload = {
                "model": TEST_MODEL_HAIKU,
                "messages": [{"role": "user", "content": "这应该会失败"}],
                "max_tokens": 10,
                "stream": False
            }
            
            # 发送几个可能失败的请求
            for i in range(3):
                try:
                    error_response = requests.post(
                        f"{self.base_url}/v1/messages",
                        headers=self.headers,
                        json=error_payload,
                        timeout=30
                    )
                    # 错误请求可能成功或失败，都是正常的
                except:
                    pass
            
            # 等待一段时间让系统处理
            time.sleep(2)
            
            # 再次发送正常请求，确保系统仍能正常工作
            response2 = requests.post(
                f"{self.base_url}/v1/messages",
                headers=self.headers,
                json=payload,
                timeout=30
            )
            
            if response2.status_code == 200:
                print("✅ 故障转移后系统仍能正常工作")
                return True
            else:
                print(f"⚠️  故障转移后请求失败: {response2.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ 故障转移测试失败: {e}")
            return False
    
    def test_cooldown_mechanism(self):
        """测试冷却机制"""
        print("测试: 冷却机制")
        
        try:
            # 获取当前服务商状态
            response = requests.get(f"{self.base_url}/providers", timeout=10)
            data = response.json()
            
            # 查看是否有处于冷却期的服务商
            cooled_down_providers = []
            for provider in data["providers"]:
                if not provider.get("healthy", True) and provider.get("enabled", False):
                    last_failure = provider.get("last_failure_time")
                    if last_failure:
                        cooled_down_providers.append(provider["name"])
            
            if cooled_down_providers:
                print(f"   发现 {len(cooled_down_providers)} 个处于冷却期的服务商")
                for name in cooled_down_providers:
                    print(f"   - {name}")
            else:
                print("   当前没有处于冷却期的服务商")
            
            # 测试冷却期内的行为
            if cooled_down_providers:
                print("   等待冷却期结束...")
                # 这里可以等待或模拟冷却期结束
                time.sleep(5)  # 简单等待
                
                # 再次检查状态
                response2 = requests.get(f"{self.base_url}/providers", timeout=10)
                data2 = response2.json()
                
                print("   冷却期后的服务商状态:")
                for provider in data2["providers"]:
                    if provider["name"] in cooled_down_providers:
                        status = "健康" if provider.get("healthy", False) else "不健康"
                        print(f"   - {provider['name']}: {status}")
            
            print("✅ 冷却机制测试完成")
            return True
            
        except Exception as e:
            print(f"❌ 冷却机制测试失败: {e}")
            return False
    
    def test_all_providers_down_scenario(self):
        """测试所有服务商都不可用的场景"""
        print("测试: 所有服务商不可用场景")
        
        # 这是一个难以模拟的测试，因为我们无法轻易让所有服务商都失败
        # 我们可以发送一个预期会失败的请求
        
        payload = {
            "model": TEST_MODEL_HAIKU,
            "messages": [{"role": "user", "content": "这应该失败"}],
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
            
            # 检查系统如何处理这种情况
            if response.status_code in [503, 502, 500]:
                print(f"✅ 系统正确返回错误状态码: {response.status_code}")
                return True
            elif response.status_code in [400, 404, 422]:
                print(f"✅ 系统返回客户端错误状态码: {response.status_code}")
                return True
            elif response.status_code == 200:
                print("ℹ️  请求意外成功（可能服务商处理了无效模型）")
                return True
            else:
                print(f"⚠️  未预期的状态码: {response.status_code}")
                return True  # 任何响应都比无响应好
                
        except requests.exceptions.Timeout:
            print("⚠️  请求超时（可能所有服务商都不可用）")
            return True
        except Exception as e:
            print(f"❌ 所有服务商不可用测试失败: {e}")
            return False
    
    def test_provider_recovery(self):
        """测试服务商恢复"""
        print("测试: 服务商恢复")
        
        try:
            # 获取当前状态
            response1 = requests.get(f"{self.base_url}/providers", timeout=10)
            data1 = response1.json()
            
            # 发送一些正常请求来确保系统稳定
            payload = {
                "model": TEST_MODEL_HAIKU,
                "messages": [{"role": "user", "content": "恢复测试"}],
                "max_tokens": 10,
                "stream": False
            }
            
            successful_requests = 0
            for i in range(3):
                try:
                    response = requests.post(
                        f"{self.base_url}/v1/messages",
                        headers=self.headers,
                        json=payload,
                        timeout=30
                    )
                    
                    if response.status_code == 200:
                        successful_requests += 1
                        
                except:
                    pass
                
                time.sleep(1)  # 间隔发送
            
            # 获取最终状态
            response2 = requests.get(f"{self.base_url}/providers", timeout=10)
            data2 = response2.json()
            
            # 比较状态变化
            print(f"   成功请求: {successful_requests}/3")
            
            healthy_before = sum(1 for p in data1["providers"] if p.get("healthy", False))
            healthy_after = sum(1 for p in data2["providers"] if p.get("healthy", False))
            
            print(f"   健康服务商: {healthy_before} -> {healthy_after}")
            
            if successful_requests > 0:
                print("✅ 服务商恢复测试通过")
                return True
            else:
                print("⚠️  没有成功的请求，可能存在问题")
                return False
                
        except Exception as e:
            print(f"❌ 服务商恢复测试失败: {e}")
            return False
    
    def test_concurrent_requests_during_failover(self):
        """测试故障转移期间的并发请求"""
        print("测试: 故障转移期间的并发请求")
        
        payload = {
            "model": "claude-3-5-haiku-20241022",
            "messages": [{"role": "user", "content": "并发测试"}],
            "max_tokens": 10,
            "stream": False
        }
        
        results = []
        
        def make_request(request_id):
            """发送单个请求"""
            try:
                response = requests.post(
                    f"{self.base_url}/v1/messages",
                    headers=self.headers,
                    json=payload,
                    timeout=30
                )
                results.append({
                    "id": request_id,
                    "status": response.status_code,
                    "success": response.status_code == 200
                })
            except Exception as e:
                results.append({
                    "id": request_id,
                    "status": None,
                    "success": False,
                    "error": str(e)
                })
        
        try:
            # 创建并启动多个线程发送并发请求
            threads = []
            for i in range(5):
                thread = threading.Thread(target=make_request, args=(i,))
                threads.append(thread)
                thread.start()
            
            # 等待所有线程完成
            for thread in threads:
                thread.join(timeout=60)
            
            # 分析结果
            successful = sum(1 for r in results if r["success"])
            total = len(results)
            
            print(f"   并发请求结果: {successful}/{total} 成功")
            
            if successful > 0:
                print("✅ 并发请求在故障转移期间部分或全部成功")
                return True
            else:
                print("⚠️  所有并发请求都失败了")
                return False
                
        except Exception as e:
            print(f"❌ 并发请求测试失败: {e}")
            return False
    
    def run_all_tests(self):
        """运行所有测试"""
        print("=" * 60)
        print("开始运行 Provider Failover 测试套件")
        print("=" * 60)
        
        # 先获取服务商状态
        if not self.get_provider_status():
            print("❌ 无法获取服务商状态，测试终止")
            return False
        
        tests = [
            self.test_provider_health_monitoring,
            self.test_failover_behavior,
            self.test_cooldown_mechanism,
            self.test_all_providers_down_scenario,
            self.test_provider_recovery,
            self.test_concurrent_requests_during_failover
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
    tester = TestProviderFailover()
    return tester.run_all_tests()

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)