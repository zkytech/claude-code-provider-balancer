#!/usr/bin/env python3
"""
测试运行器 - 运行所有测试套件
"""

import os
import sys
import time
import subprocess
import importlib.util
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# 测试文件列表（按优先级排序）
TEST_FILES = [
    # 核心功能测试
    "test_stream_nonstream.py",
    "test_provider_routing.py", 
    "test_provider_failover.py",
    "test_timeout_retry.py",
    "test_client_disconnect.py",
    "test_caching_deduplication.py",
    
    # 扩展功能测试
    "test_passthrough.py",
    "test_log_colors.py",
    "test_provider_type_switching.py",
    "test_error_handling.py",
]

class TestRunner:
    def __init__(self):
        self.test_dir = Path(__file__).parent
        self.results = {}
        
    def check_server_running(self):
        """检查服务器是否运行"""
        try:
            import requests
            response = requests.get("http://localhost:8080/", timeout=5)
            return response.status_code == 200
        except:
            return False
    
    def run_single_test(self, test_file):
        """运行单个测试文件"""
        test_path = self.test_dir / test_file
        
        if not test_path.exists():
            return {
                "status": "SKIP",
                "reason": "文件不存在",
                "duration": 0,
                "output": ""
            }
        
        print(f"\n{'='*60}")
        print(f"运行测试: {test_file}")
        print(f"{'='*60}")
        
        start_time = time.time()
        
        try:
            # 使用 subprocess 运行测试
            result = subprocess.run(
                [sys.executable, str(test_path)],
                capture_output=True,
                text=True,
                timeout=300  # 5分钟超时
            )
            
            duration = time.time() - start_time
            
            if result.returncode == 0:
                status = "PASS"
                print(result.stdout)
            else:
                status = "FAIL"
                print(result.stdout)
                if result.stderr:
                    print("STDERR:")
                    print(result.stderr)
            
            return {
                "status": status,
                "duration": duration,
                "returncode": result.returncode,
                "output": result.stdout,
                "error": result.stderr
            }
            
        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            return {
                "status": "TIMEOUT",
                "duration": duration,
                "output": "",
                "error": "测试超时"
            }
            
        except Exception as e:
            duration = time.time() - start_time
            return {
                "status": "ERROR",
                "duration": duration,
                "output": "",
                "error": str(e)
            }
    
    def run_all_tests(self, selected_tests=None):
        """运行所有测试"""
        if selected_tests is None:
            selected_tests = TEST_FILES
        
        # 检查服务器状态
        if not self.check_server_running():
            print("❌ 服务器未运行！")
            print("请先启动服务器: python src/main.py")
            return False
        
        print("🚀 开始运行测试套件")
        print(f"📋 计划运行 {len(selected_tests)} 个测试文件")
        
        total_start_time = time.time()
        
        # 运行测试
        for test_file in selected_tests:
            result = self.run_single_test(test_file)
            self.results[test_file] = result
            
            # 显示进度
            status_emoji = {
                "PASS": "✅",
                "FAIL": "❌", 
                "SKIP": "⏭️",
                "TIMEOUT": "⏰",
                "ERROR": "💥"
            }
            
            emoji = status_emoji.get(result["status"], "❓")
            print(f"{emoji} {test_file}: {result['status']} ({result['duration']:.2f}s)")
        
        total_duration = time.time() - total_start_time
        
        # 生成报告
        self.generate_report(total_duration)
        
        # 返回是否所有测试都通过
        return all(r["status"] == "PASS" for r in self.results.values())
    
    def generate_report(self, total_duration):
        """生成测试报告"""
        print(f"\n{'='*60}")
        print("📊 测试报告")
        print(f"{'='*60}")
        
        # 统计结果
        stats = {}
        for result in self.results.values():
            status = result["status"]
            stats[status] = stats.get(status, 0) + 1
        
        total_tests = len(self.results)
        passed_tests = stats.get("PASS", 0)
        failed_tests = stats.get("FAIL", 0)
        skipped_tests = stats.get("SKIP", 0)
        timeout_tests = stats.get("TIMEOUT", 0)
        error_tests = stats.get("ERROR", 0)
        
        print(f"总测试数: {total_tests}")
        print(f"✅ 通过: {passed_tests}")
        print(f"❌ 失败: {failed_tests}")
        print(f"⏭️ 跳过: {skipped_tests}")
        print(f"⏰ 超时: {timeout_tests}")
        print(f"💥 错误: {error_tests}")
        print(f"⏱️ 总耗时: {total_duration:.2f}秒")
        
        # 成功率
        if total_tests > 0:
            success_rate = (passed_tests / total_tests) * 100
            print(f"📈 成功率: {success_rate:.1f}%")
        
        # 详细结果
        if failed_tests > 0 or timeout_tests > 0 or error_tests > 0:
            print(f"\n{'='*40}")
            print("❌ 失败的测试详情:")
            print(f"{'='*40}")
            
            for test_file, result in self.results.items():
                if result["status"] in ["FAIL", "TIMEOUT", "ERROR"]:
                    print(f"\n🔍 {test_file} ({result['status']}):")
                    if result.get("error"):
                        print(f"   错误: {result['error']}")
                    if result.get("returncode"):
                        print(f"   返回码: {result['returncode']}")
        
        # 性能统计
        print(f"\n{'='*40}")
        print("⚡ 性能统计:")
        print(f"{'='*40}")
        
        durations = [r["duration"] for r in self.results.values() if r["status"] == "PASS"]
        if durations:
            avg_duration = sum(durations) / len(durations)
            max_duration = max(durations)
            min_duration = min(durations)
            
            print(f"平均耗时: {avg_duration:.2f}s")
            print(f"最长耗时: {max_duration:.2f}s")
            print(f"最短耗时: {min_duration:.2f}s")
            
            # 找出最慢的测试
            slowest_test = max(self.results.items(), key=lambda x: x[1]["duration"])
            print(f"最慢测试: {slowest_test[0]} ({slowest_test[1]['duration']:.2f}s)")
        
        # 最终结论
        print(f"\n{'='*60}")
        if passed_tests == total_tests:
            print("🎉 所有测试都通过了！")
        elif passed_tests > 0:
            print(f"⚠️  部分测试通过 ({passed_tests}/{total_tests})")
        else:
            print("💥 所有测试都失败了")
        print(f"{'='*60}")

def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="运行Claude Code Provider Balancer测试套件")
    parser.add_argument(
        "--tests", 
        nargs="+", 
        help="指定要运行的测试文件",
        choices=TEST_FILES,
        default=None
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="列出所有可用的测试文件"
    )
    parser.add_argument(
        "--check-server",
        action="store_true", 
        help="只检查服务器状态"
    )
    
    args = parser.parse_args()
    
    runner = TestRunner()
    
    if args.list:
        print("📋 可用的测试文件:")
        for i, test_file in enumerate(TEST_FILES, 1):
            exists = (runner.test_dir / test_file).exists()
            status = "✅" if exists else "❌"
            print(f"  {i:2d}. {status} {test_file}")
        return True
    
    if args.check_server:
        if runner.check_server_running():
            print("✅ 服务器正在运行")
            return True
        else:
            print("❌ 服务器未运行")
            print("启动命令: python src/main.py")
            return False
    
    # 运行测试
    selected_tests = args.tests if args.tests else TEST_FILES
    success = runner.run_all_tests(selected_tests)
    
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)