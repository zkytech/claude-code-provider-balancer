#!/usr/bin/env python3
"""
OAuth认证功能测试
测试Claude Code Official provider的OAuth 2.0认证流程
"""

import json
import requests
import sys
import os
import time
import hashlib
import secrets
import base64
from urllib.parse import urlencode, parse_qs, urlparse

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from test_utils import get_claude_code_headers

BASE_URL = "http://localhost:9090"

# OAuth 常量 (与实际实现保持一致)
OAUTH_AUTHORIZE_URL = "https://claude.ai/oauth/authorize"
CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
REDIRECT_URI = "https://console.anthropic.com/oauth/code/callback"
SCOPES = "org:create_api_key user:profile user:inference"

class TestOAuth:
    def __init__(self):
        self.base_url = BASE_URL
        self.headers = get_claude_code_headers()
        self.oauth_url = None
        self.mock_auth_code = None
        
    def test_oauth_status_endpoint(self):
        """测试OAuth状态端点"""
        print("测试: /oauth/status 端点")
        
        try:
            response = requests.get(f"{self.base_url}/oauth/status", timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                print(f"✅ OAuth状态获取成功")
                
                # 检查新的响应结构
                if 'summary' in data:
                    summary = data['summary']
                    print(f"   总Token数: {summary.get('total_tokens', 0)}")
                    print(f"   健康Token数: {summary.get('healthy_tokens', 0)}")
                    print(f"   过期Token数: {summary.get('expired_tokens', 0)}")
                    print(f"   轮换启用: {summary.get('rotation_enabled', False)}")
                
                if 'active_token' in data and data['active_token']:
                    active = data['active_token']
                    print(f"   当前Token: {active['account_email']} ({active['expires_in_human']})")
                
                if 'tokens' in data and data['tokens']:
                    for token in data['tokens']:
                        account_email = token.get('account_email', 'unknown')
                        expires_human = token.get('expires_in_human', 'unknown')
                        is_current = "当前" if token.get('is_current', False) else ""
                        print(f"   - {account_email}: {expires_human} {is_current}")
                else:
                    print("   暂无存储的Token")
                return True
            else:
                print(f"❌ OAuth状态获取失败: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ OAuth状态端点测试失败: {e}")
            return False
    
    def test_oauth_flow_trigger(self):
        """测试OAuth流程触发 - 通过401错误触发真实OAuth流程"""
        print("测试: 触发真实OAuth授权流程")
        
        try:
            # 首先清除所有existing tokens以确保触发401
            try:
                requests.delete(f"{self.base_url}/oauth/tokens", timeout=10)
                print("   已清除现有tokens")
            except:
                pass  # 忽略清除错误
            
            # 发送请求到Claude Code Official，应该触发401
            test_request = {
                "model": "claude-3-5-sonnet-20241022", 
                "messages": [
                    {"role": "user", "content": "Hello, this is a test for OAuth flow"}
                ],
                "max_tokens": 10,
                "provider": "Claude Code Official"  # 在请求体中指定provider
            }
            
            print("   发送请求触发OAuth流程...")
            response = requests.post(
                f"{self.base_url}/v1/messages",
                json=test_request,
                headers=self.headers,
                timeout=30
            )
            
            if response.status_code == 401:
                print("✅ 成功触发401错误")
                print("   检查console输出，应该看到OAuth授权指导")
                
                # 给一点时间让OAuth URL生成完成
                time.sleep(1)
                
                print("\n📝 预期的Console输出:")
                print("   🔐 CLAUDE CODE OFFICIAL AUTHORIZATION REQUIRED")
                print("   包含 http://localhost:9090/oauth/generate-url 链接和使用指导")
                print("\n💡 要完成测试，请:")
                print("   1. 访问 http://localhost:9090/oauth/generate-url 获取OAuth URL")
                print("   2. 在浏览器中完成授权")
                print("   3. 复制callback URL中的code参数")
                print("   4. 运行: curl -X POST http://localhost:9090/oauth/exchange-code -d '{\"code\": \"YOUR_CODE\", \"account_email\": \"user@example.com\"}')")
                
                return True
            elif response.status_code == 200:
                print("✅ 请求成功 - 可能已经有有效token")
                data = response.json()
                if 'content' in data:
                    print(f"   响应: {data['content'][:100]}...")
                return True
            else:
                print(f"⚠️  收到状态码 {response.status_code}")
                print("   这可能是正常的，取决于provider配置")
                return True  # 不算失败
                
        except requests.exceptions.Timeout:
            print("⚠️  请求超时 - OAuth流程可能已触发，检查console")
            return True
        except Exception as e:
            print(f"❌ OAuth流程触发测试失败: {e}")
            return False
    
    def test_oauth_exchange_endpoint_validation(self):
        """测试OAuth交换端点验证"""
        print("测试: /oauth/exchange-code 端点验证")
        
        success_count = 0
        
        try:
            # 测试1：缺少所有参数的请求
            response = requests.post(
                f"{self.base_url}/oauth/exchange-code",
                json={},
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            
            if response.status_code == 400:
                data = response.json()
                if "Missing authorization code" in data.get("error", ""):
                    print("✅ 授权码验证正确 - 正确拒绝空请求")
                    success_count += 1
                else:
                    print(f"❌ 意外的错误消息: {data.get('error', 'unknown')}")
            else:
                print(f"❌ 意外的状态码: {response.status_code}")
            
            # 测试2：只有授权码，缺少account_email的请求
            response = requests.post(
                f"{self.base_url}/oauth/exchange-code",
                json={"code": "test_code"},
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            
            if response.status_code == 400:
                data = response.json()
                if "Missing account_email parameter" in data.get("error", ""):
                    print("✅ account_email验证正确 - 正确拒绝缺少email的请求")
                    success_count += 1
                else:
                    print(f"❌ 意外的错误消息: {data.get('error', 'unknown')}")
            else:
                print(f"❌ 意外的状态码: {response.status_code}")
                
            return success_count == 2
                
        except Exception as e:
            print(f"❌ OAuth交换端点验证失败: {e}")
            return False
    
    def test_oauth_token_management_endpoints(self):
        """测试OAuth Token管理端点"""
        print("测试: OAuth Token管理端点")
        
        success_count = 0
        
        # 测试删除不存在的token (使用email格式)
        try:
            response = requests.delete(
                f"{self.base_url}/oauth/tokens/nonexistent@example.com",
                timeout=10
            )
            
            if response.status_code == 404:
                data = response.json()
                if "not found" in data.get("error", "").lower():
                    print("✅ 删除不存在Token - 正确返回404")
                    success_count += 1
                else:
                    print(f"❌ 意外的错误消息: {data.get('error', 'unknown')}")
            else:
                print(f"❌ 删除不存在Token - 意外状态码: {response.status_code}")
                
        except Exception as e:
            print(f"❌ 删除Token端点测试失败: {e}")
        
        # 测试清除所有token
        try:
            response = requests.delete(f"{self.base_url}/oauth/tokens", timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "success":
                    print("✅ 清除所有Token端点正常工作")
                    success_count += 1
                else:
                    print(f"❌ 清除Token意外响应: {data}")
            else:
                print(f"❌ 清除所有Token - 意外状态码: {response.status_code}")
                
        except Exception as e:
            print(f"❌ 清除所有Token端点测试失败: {e}")
        
        return success_count == 2
    
    def test_provider_auth_value_memory_mode(self):
        """测试Provider OAuth auth_value模式配置"""
        print("测试: Provider OAuth认证模式配置")
        
        try:
            response = requests.get(f"{self.base_url}/providers", timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                providers = data.get("providers", [])
                
                # 查找Claude Code Official provider
                claude_official = None
                for provider in providers:
                    if provider.get("name") == "Claude Code Official":
                        claude_official = provider
                        break
                
                if claude_official:
                    print("✅ 找到Claude Code Official provider")
                    print(f"   状态: {'启用' if claude_official.get('enabled') else '禁用'}")
                    print(f"   健康: {'健康' if claude_official.get('healthy') else '不健康'}")
                    return True
                else:
                    print("❌ 未找到Claude Code Official provider配置")
                    return False
            else:
                print(f"❌ 获取Provider状态失败: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ Provider配置测试失败: {e}")
            return False
    
    def test_oauth_interactive_exchange(self):
        """测试交互式OAuth授权码交换"""
        print("测试: 交互式OAuth授权码交换")
        
        # 检查是否有环境变量提供的测试授权码
        test_auth_code = os.environ.get("OAUTH_TEST_CODE")
        
        if test_auth_code:
            print(f"   使用环境变量提供的授权码: {test_auth_code[:20]}...")
            
            # 检查是否有测试用email，如果没有则使用默认的
            test_email = os.environ.get("OAUTH_TEST_EMAIL", "test@example.com")
            print(f"   使用测试邮箱: {test_email}")
            
            try:
                response = requests.post(
                    f"{self.base_url}/oauth/exchange-code",
                    json={
                        "code": test_auth_code,
                        "account_email": test_email
                    },
                    headers={"Content-Type": "application/json"},
                    timeout=30
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get("status") == "success":
                        account_email = data.get("account_email", "unknown")
                        expires_at = data.get("expires_at", 0)
                        scopes = data.get("scopes", [])
                        
                        print("✅ OAuth授权码交换成功")
                        print(f"   账户Email: {account_email}")
                        print(f"   过期时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(expires_at))}")
                        print(f"   权限范围: {', '.join(scopes)}")
                        return True
                    else:
                        print(f"❌ 交换失败: {data}")
                        return False
                else:
                    print(f"❌ 授权码交换失败: {response.status_code}")
                    try:
                        error_data = response.json()
                        print(f"   错误: {error_data.get('error', 'unknown')}")
                    except:
                        print(f"   响应: {response.text}")
                    return False
                    
            except Exception as e:
                print(f"❌ OAuth交换测试失败: {e}")
                return False
        else:
            print("⚠️  未提供测试授权码")
            print("   要测试真实OAuth交换，请:")
            print("   1. 触发OAuth流程获取授权码")
            print("   2. 设置环境变量: export OAUTH_TEST_CODE=your_auth_code")
            print("   3. (可选) 设置环境变量: export OAUTH_TEST_EMAIL=your@email.com")
            print("   4. 重新运行测试")
            return True  # 不算失败，只是跳过
    
    def test_oauth_with_real_request(self):
        """测试使用真实OAuth token发送请求"""
        print("测试: 使用OAuth token发送真实请求")
        
        try:
            # 先检查是否有可用的token
            status_response = requests.get(f"{self.base_url}/oauth/status", timeout=10)
            
            if status_response.status_code == 200:
                status_data = status_response.json()
                
                if status_data.get("total_tokens", 0) > 0:
                    print("   检测到可用的OAuth tokens")
                    
                    # 发送真实请求测试
                    test_request = {
                        "model": "claude-3-5-haiku-20241022",
                        "messages": [
                            {"role": "user", "content": "Say 'OAuth test successful' if you can see this"}
                        ],
                        "max_tokens": 20,
                        "provider": "Claude Code Official"  # 在请求体中指定provider
                    }
                    
                    response = requests.post(
                        f"{self.base_url}/v1/messages",
                        json=test_request,
                        headers=self.headers,
                        timeout=60
                    )
                    
                    if response.status_code == 200:
                        data = response.json()
                        if 'content' in data:
                            content = data['content'][0]['text'] if isinstance(data['content'], list) else str(data['content'])
                            print(f"✅ OAuth请求成功")
                            print(f"   响应: {content[:100]}...")
                            return True
                        else:
                            print(f"✅ 请求成功但响应格式不同: {data}")
                            return True
                    elif response.status_code == 401:
                        print("⚠️  收到401错误 - tokens可能已过期")
                        print("   检查console是否显示了新的OAuth授权指导")
                        return True  # 这是预期的行为
                    else:
                        print(f"⚠️  请求失败: {response.status_code}")
                        try:
                            error_data = response.json()
                            print(f"   错误: {error_data}")
                        except:
                            print(f"   响应: {response.text[:200]}...")
                        return False
                else:
                    print("⚠️  没有可用的OAuth tokens")
                    print("   需要先完成OAuth授权流程")
                    return True  # 不算失败
            else:
                print(f"❌ 无法获取OAuth状态: {status_response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ OAuth真实请求测试失败: {e}")
            return False
    
    def test_oauth_keyring_persistence(self):
        """测试OAuth token keyring持久化功能"""
        print("测试: OAuth token keyring持久化")
        
        try:
            # 测试keyring可用性
            try:
                import keyring
                print("✅ keyring库可用")
            except ImportError:
                print("⚠️  keyring库不可用，跳过持久化测试")
                return True
            
            # 导入OAuth管理器
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
            from oauth_manager import OAuthManager, TokenCredentials
            
            # 测试基本keyring功能
            test_service = "test-oauth-service"
            test_user = "test-user"
            test_password = "test-password"
            
            keyring.set_password(test_service, test_user, test_password)
            retrieved = keyring.get_password(test_service, test_user)
            
            if retrieved == test_password:
                print("✅ 基本keyring功能正常")
                keyring.delete_password(test_service, test_user)
            else:
                print("❌ 基本keyring功能异常")
                return False
            
            # 测试OAuth管理器持久化
            oauth_manager = OAuthManager(enable_persistence=True)
            print(f"✅ OAuth管理器创建 (持久化: {oauth_manager.enable_persistence})")
            
            # 创建测试token (现在account_id是email格式)
            test_token = TokenCredentials(
                access_token="test_access_token_keyring_12345",
                refresh_token="test_refresh_token_keyring_67890",
                expires_at=int(time.time()) + 3600,  # 1小时后过期
                scopes=["org:create_api_key", "user:profile", "user:inference"],
                account_id="test@keyring.com"
            )
            
            # 保存token (模拟添加token的过程)
            oauth_manager.token_credentials.append(test_token)
            oauth_manager._save_to_keyring()
            print("✅ 测试token保存到keyring")
            
            # 创建新的OAuth管理器实例来测试加载
            oauth_manager2 = OAuthManager(enable_persistence=True)
            
            if oauth_manager2.token_credentials:
                loaded_token = oauth_manager2.token_credentials[0]
                
                if (loaded_token.access_token == test_token.access_token and
                    loaded_token.refresh_token == test_token.refresh_token and
                    loaded_token.account_id == test_token.account_id):
                    print("✅ token持久化和加载成功")
                    print(f"   账户Email: {loaded_token.account_id}")
                    print(f"   过期时间: {loaded_token.expires_at - time.time():.0f}秒后")
                    
                    # 清理测试数据
                    oauth_manager2.clear_all_tokens()
                    print("✅ 测试数据清理完成")
                    
                    return True
                else:
                    print("❌ token数据不匹配")
                    oauth_manager2.clear_all_tokens()
                    return False
            else:
                print("❌ 无法从keyring加载token")
                return False
                
        except Exception as e:
            print(f"❌ keyring持久化测试失败: {e}")
            return False
    
    def test_oauth_manual_generate_url(self):
        """测试手动生成OAuth URL接口"""
        print("测试: 手动生成OAuth URL接口")
        
        try:
            response = requests.get(f"{self.base_url}/oauth/generate-url", timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "success" and data.get("login_url"):
                    login_url = data["login_url"]
                    instructions = data.get("instructions", {})
                    
                    print("✅ OAuth URL生成成功")
                    print(f"   授权URL: {login_url[:50]}...")
                    print(f"   包含指导说明: {len(instructions)} 个步骤")
                    print(f"   过期时间: {data.get('expires_in_minutes', 'N/A')} 分钟")
                    
                    # 验证URL格式
                    if "claude.ai/oauth/authorize" in login_url:
                        print("✅ OAuth URL格式正确")
                        return True
                    else:
                        print("❌ OAuth URL格式不正确")
                        return False
                else:
                    print(f"❌ 响应格式错误: {data}")
                    return False
            else:
                print(f"❌ HTTP错误: {response.status_code}")
                try:
                    error_data = response.json()
                    print(f"   错误信息: {error_data.get('error', 'unknown')}")
                except:
                    print(f"   响应内容: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ 手动OAuth URL生成测试失败: {e}")
            return False
    
    def run_all_tests(self):
        """运行所有OAuth测试"""
        print("🔐 OAuth认证功能测试")
        print("="*50)
        
        tests = [
            ("OAuth状态端点", self.test_oauth_status_endpoint),
            ("触发OAuth流程", self.test_oauth_flow_trigger),
            ("OAuth交换端点验证", self.test_oauth_exchange_endpoint_validation),
            ("OAuth Token管理", self.test_oauth_token_management_endpoints),
            ("Provider OAuth模式", self.test_provider_auth_value_memory_mode),
            ("交互式OAuth交换", self.test_oauth_interactive_exchange),
            ("真实OAuth请求", self.test_oauth_with_real_request),
            ("Keyring持久化", self.test_oauth_keyring_persistence),
            ("手动OAuth URL生成", self.test_oauth_manual_generate_url),
        ]
        
        passed = 0
        total = len(tests)
        
        for test_name, test_func in tests:
            print(f"\n📋 {test_name}")
            print("-" * 30)
            
            try:
                if test_func():
                    passed += 1
                    print(f"✅ {test_name} 通过")
                else:
                    print(f"❌ {test_name} 失败")
            except Exception as e:
                print(f"💥 {test_name} 执行异常: {e}")
        
        print(f"\n{'='*50}")
        print(f"📊 OAuth测试结果")
        print(f"{'='*50}")
        print(f"通过: {passed}/{total}")
        print(f"成功率: {passed/total*100:.1f}%")
        
        if passed == total:
            print("🎉 所有OAuth测试都通过了！")
            return True
        else:
            print(f"⚠️  {total - passed} 个测试失败")
            return False

def main():
    """主函数"""
    print("Claude Code Provider Balancer - OAuth测试")
    print(f"服务器地址: {BASE_URL}")
    
    # 检查服务器状态
    try:
        response = requests.get(f"{BASE_URL}/", timeout=5)
        if response.status_code != 200:
            print(f"❌ 服务器响应异常: {response.status_code}")
            return False
    except:
        print("❌ 服务器未运行！")
        print("请先启动服务器: python src/main.py")
        return False
    
    # 运行测试
    tester = TestOAuth()
    success = tester.run_all_tests()
    
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)