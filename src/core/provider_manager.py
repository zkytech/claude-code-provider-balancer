"""
Provider Manager for Claude Code Provider Balancer
Manages multiple Claude Code and OpenAI-compatible providers with simplified model routing.
"""

import os
import time
import yaml
import re
import random
import threading
from typing import List, Optional, Dict, Any, Tuple
from pathlib import Path
from dataclasses import dataclass
from enum import Enum
import httpx

# OAuth manager will be imported dynamically when needed
from utils import info, warning, error, debug, LogRecord, LogEvent


class ProviderType(str, Enum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"


class AuthType(str, Enum):
    API_KEY = "api_key"
    AUTH_TOKEN = "auth_token"
    OAUTH = "oauth"


class SelectionStrategy(str, Enum):
    PRIORITY = "priority"
    ROUND_ROBIN = "round_robin"
    RANDOM = "random"


class StreamingMode(str, Enum):
    AUTO = "auto"  # Based on provider type (anthropic=direct, openai=background)
    DIRECT = "direct"  # Direct provider streaming without background collection
    BACKGROUND = "background"  # Background collection then streaming to client


@dataclass
class ModelRoute:
    provider: str
    model: str
    priority: int
    enabled: bool = True


@dataclass
class Provider:
    name: str
    type: ProviderType
    base_url: str
    auth_type: AuthType
    auth_value: str
    enabled: bool = True
    proxy: Optional[str] = None
    streaming_mode: StreamingMode = StreamingMode.AUTO
    failure_count: int = 0
    last_failure_time: float = 0
    
    def is_healthy(self, cooldown_seconds: int = 60) -> bool:
        """Check if provider is healthy (not in cooldown period)"""
        if self.failure_count == 0:
            return True
        return time.time() - self.last_failure_time > cooldown_seconds
    
    def mark_failure(self):
        """Mark provider as failed"""
        self.failure_count += 1
        self.last_failure_time = time.time()
    
    def mark_success(self):
        """Mark provider as successful (reset failure count)"""
        self.failure_count = 0
        self.last_failure_time = 0
    
    def get_effective_streaming_mode(self) -> StreamingMode:
        """Get the effective streaming mode based on configuration and provider type"""
        if self.streaming_mode == StreamingMode.AUTO:
            # Auto mode: anthropic providers use direct, openai providers use background
            if self.type == ProviderType.ANTHROPIC:
                return StreamingMode.DIRECT
            else:  # ProviderType.OPENAI
                return StreamingMode.BACKGROUND
        else:
            # Use explicitly configured mode
            return self.streaming_mode


class ProviderManager:
    def __init__(self, config_path: str = "config.yaml"):
        # Determine the absolute path to the config file
        if not os.path.isabs(config_path):
            # If relative path, look for it in project root (two levels up from src/core)
            current_dir = Path(__file__).parent
            project_root = current_dir.parent.parent
            config_path = project_root / config_path
        
        self.config_path = Path(config_path)
        self.providers: List[Provider] = []
        self.settings: Dict[str, Any] = {}
        
        # 简化的配置
        self.model_routes: Dict[str, List[ModelRoute]] = {}
        self.selection_strategy: SelectionStrategy = SelectionStrategy.PRIORITY
        
        # 用于round_robin策略的索引记录
        self._round_robin_indices: Dict[str, int] = {}
        
        # 请求活跃状态跟踪
        self._last_request_time: float = 0
        self._last_successful_provider: Optional[str] = None  # 记录最后成功的provider名称
        self._sticky_provider_duration: float = 300  # 默认粘滞provider持续时间为5分钟
        
        # OAuth配置
        self.oauth_auto_refresh_enabled: bool = True
        
        # 健康检查配置
        self.unhealthy_threshold: int = 2
        self.unhealthy_reset_on_success: bool = True 
        self.unhealthy_reset_timeout: float = 300  # 5分钟
        
        # Provider错误计数状态
        self._error_counts: Dict[str, int] = {}            # {provider_name: error_count}
        self._last_error_time: Dict[str, float] = {}       # {provider_name: timestamp}
        self._last_success_time: Dict[str, float] = {}     # {provider_name: timestamp}
        self._lock = threading.Lock()  # 保护并发访问
        
        self.load_config()
    
    def load_config(self):
        """Load simplified configuration from YAML file"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            self.settings = config.get('settings', {})
            self.selection_strategy = SelectionStrategy(
                self.settings.get('selection_strategy', 'priority')
            )
            
            # 加载OAuth配置
            oauth_config = self.settings.get('oauth', {})
            self.oauth_auto_refresh_enabled = oauth_config.get('enable_auto_refresh', True)
            
            # 加载智能恢复配置
            self._sticky_provider_duration = self.settings.get('sticky_provider_duration', 300)
            
            # 加载健康检查配置
            self.unhealthy_threshold = self.settings.get('unhealthy_threshold', 2)
            self.unhealthy_reset_on_success = self.settings.get('unhealthy_reset_on_success', True)
            self.unhealthy_reset_timeout = self.settings.get('unhealthy_reset_timeout', 300)
            
            # 加载服务商配置（简化版）
            providers_config = config.get('providers', [])
            self.providers = []
            
            for provider_config in providers_config:
                if provider_config.get('enabled', True):
                    # Parse streaming_mode with default to AUTO
                    streaming_mode_str = provider_config.get('streaming_mode', 'auto')
                    try:
                        streaming_mode = StreamingMode(streaming_mode_str)
                    except ValueError:
                        print(f"Warning: Invalid streaming_mode '{streaming_mode_str}' for provider '{provider_config['name']}', using 'auto'")
                        streaming_mode = StreamingMode.AUTO
                    
                    provider = Provider(
                        name=provider_config['name'],
                        type=ProviderType(provider_config['type']),
                        base_url=provider_config['base_url'],
                        auth_type=AuthType(provider_config['auth_type']),
                        auth_value=provider_config['auth_value'],
                        enabled=provider_config.get('enabled', True),
                        proxy=provider_config.get('proxy'),
                        streaming_mode=streaming_mode
                    )
                    debug(LogRecord(
                        event=LogEvent.PROVIDER_LOADED.value,
                        message=f"Loaded provider {provider.name} with auth_type={provider.auth_type}, auth_value=[DREDACTED]"
                    ))
                    self.providers.append(provider)
            
            # 加载模型路由配置
            self._load_model_routes(config.get('model_routes', {}))
            
            if not self.providers:
                raise ValueError("No enabled providers found in configuration")
                
        except Exception as e:
            raise RuntimeError(f"Failed to load provider configuration: {e}")
    
    def _load_model_routes(self, routes_config: Dict[str, Any]):
        """加载模型路由配置"""
        self.model_routes = {}
        
        for model_pattern, routes in routes_config.items():
            route_list = []
            for route_config in routes:
                if isinstance(route_config, dict):
                    route = ModelRoute(
                        provider=route_config['provider'],
                        model=route_config['model'],
                        priority=route_config['priority'],
                        enabled=route_config.get('enabled', True)
                    )
                    route_list.append(route)
            self.model_routes[model_pattern] = route_list
    
    def _get_provider_by_name(self, name: str) -> Optional[Provider]:
        """根据名称获取服务商"""
        for provider in self.providers:
            if provider.name == name:
                return provider
        return None
    
    def _matches_pattern(self, model_name: str, pattern: str) -> bool:
        """检查模型名是否匹配给定的模式"""
        model_lower = model_name.lower()
        pattern_lower = pattern.lower()
        
        # 支持通配符匹配
        if '*' in pattern:
            regex_pattern = pattern_lower.replace('*', '.*')
            return bool(re.search(regex_pattern, model_lower))
        else:
            # 精确匹配
            return pattern_lower == model_lower
    
    def select_model_and_provider_options(self, requested_model: str) -> List[Tuple[str, Provider]]:
        """
        简化的模型选择逻辑
        返回按优先级排序的 (target_model, provider) 列表
        """
        # 1. 精确匹配
        if requested_model in self.model_routes:
            options = self._build_options_from_routes(self.model_routes[requested_model], requested_model)
            if options:
                return self._apply_selection_strategy(options, requested_model)
        
        # 2. 通配符匹配
        for pattern, routes in self.model_routes.items():
            if self._matches_pattern(requested_model, pattern):
                options = self._build_options_from_routes(routes, requested_model)
                if options:
                    return self._apply_selection_strategy(options, requested_model)
        
        # 3. 没有匹配的路由
        return []
    
    def _build_options_from_routes(self, routes: List[ModelRoute], requested_model: str) -> List[Tuple[str, Provider, int]]:
        """从路由配置构建可用选项"""
        options = []
        cooldown = self.get_failure_cooldown()
        
        for route in routes:
            if not route.enabled:
                continue
                
            provider = self._get_provider_by_name(route.provider)
            if not provider or not provider.enabled or not provider.is_healthy(cooldown):
                continue
            
            # 处理模型名称
            target_model = route.model
            if target_model == "passthrough":
                target_model = requested_model
            
            options.append((target_model, provider, route.priority))
        
        return options
    
    def _apply_selection_strategy(self, options: List[Tuple[str, Provider, int]], requested_model: str) -> List[Tuple[str, Provider]]:
        """根据选择策略对选项进行排序和选择"""
        if not options:
            return []
        
        # 检查粘滞provider是否过期，如果是则使用正常的优先级选择
        current_time = time.time()
        is_sticky_expired = (current_time - self._last_request_time) > self._sticky_provider_duration
        
        if not is_sticky_expired and self._last_successful_provider:
            # 粘滞期间：优先使用上次成功的provider
            sticky_option = None
            other_options = []
            
            for model, provider, priority in options:
                if provider.name == self._last_successful_provider:
                    sticky_option = (model, provider, priority)
                else:
                    other_options.append((model, provider, priority))
            
            # 如果找到了粘滞provider，将其放在第一位
            if sticky_option:
                sorted_other_options = sorted(other_options, key=lambda x: x[2])
                final_options = [sticky_option] + sorted_other_options
                # print(f"[DEBUG] Sticky logic applied - prioritizing {self._last_successful_provider}")
                return [(model, provider) for model, provider, priority in final_options]
        
        if self.selection_strategy == SelectionStrategy.PRIORITY:
            # 按优先级排序（数字越小优先级越高）
            sorted_options = sorted(options, key=lambda x: x[2])
            return [(model, provider) for model, provider, priority in sorted_options]
        
        elif self.selection_strategy == SelectionStrategy.ROUND_ROBIN:
            # Round robin选择
            sorted_options = sorted(options, key=lambda x: x[2])
            key = f"{requested_model}_{len(sorted_options)}"
            
            if key not in self._round_robin_indices:
                self._round_robin_indices[key] = 0
            
            current_index = self._round_robin_indices[key]
            self._round_robin_indices[key] = (current_index + 1) % len(sorted_options)
            
            # 将当前选择的放在第一位，其他保持优先级顺序
            selected = sorted_options.pop(current_index)
            result = [selected] + sorted_options
            return [(model, provider) for model, provider, priority in result]
        
        elif self.selection_strategy == SelectionStrategy.RANDOM:
            # 随机选择，但仍然返回所有选项作为fallback
            sorted_options = sorted(options, key=lambda x: x[2])
            if len(sorted_options) > 1:
                # 从前3个优先级中随机选择
                top_options = sorted_options[:min(3, len(sorted_options))]
                selected = random.choice(top_options)
                remaining = [opt for opt in sorted_options if opt != selected]
                result = [selected] + remaining
                return [(model, provider) for model, provider, priority in result]
            return [(model, provider) for model, provider, priority in sorted_options]
        
        # 默认按优先级排序
        sorted_options = sorted(options, key=lambda x: x[2])
        return [(model, provider) for model, provider, priority in sorted_options]
    
    def get_failure_cooldown(self) -> int:
        """Get failure cooldown time from settings"""
        return self.settings.get('failure_cooldown', 60)
    
    def get_non_streaming_timeouts(self) -> Dict[str, int]:
        """获取非流式请求超时配置"""
        timeouts = self.settings.get('timeouts', {})
        non_streaming = timeouts.get('non_streaming', {})
        return {
            'connect_timeout': non_streaming.get('connect_timeout', 30),
            'read_timeout': non_streaming.get('read_timeout', 60),
            'pool_timeout': non_streaming.get('pool_timeout', 30)
        }
    
    def get_streaming_timeouts(self) -> Dict[str, int]:
        """获取流式请求超时配置"""
        timeouts = self.settings.get('timeouts', {})
        streaming = timeouts.get('streaming', {})
        return {
            'connect_timeout': streaming.get('connect_timeout', 30),
            'read_timeout': streaming.get('read_timeout', 120),
            'pool_timeout': streaming.get('pool_timeout', 30)
        }
    
    def get_timeouts_for_request(self, is_streaming: bool) -> Dict[str, int]:
        """根据请求类型获取相应的超时配置"""
        if is_streaming:
            return self.get_streaming_timeouts()
        else:
            return self.get_non_streaming_timeouts()
    
    def get_caching_timeouts(self) -> Dict[str, int]:
        """获取缓存相关超时配置"""
        timeouts = self.settings.get('timeouts', {})
        caching = timeouts.get('caching', {})
        return {
            'deduplication_timeout': caching.get('deduplication_timeout', 300)
        }
    
    def get_healthy_providers(self) -> List[Provider]:
        """Get list of healthy (non-failed) providers"""
        cooldown = self.get_failure_cooldown()
        
        # 简化逻辑：只返回健康的providers，粘滞逻辑已移至选择策略中
        healthy_providers = [p for p in self.providers if p.enabled and p.is_healthy(cooldown)]
        # Removed debug print - this would be too noisy in production
        return healthy_providers
    
    def mark_request_start(self):
        """标记请求开始，更新活跃状态"""
        # 不在请求开始时更新时间，而是在请求完成时更新
        pass
    
    def mark_provider_success(self, provider_name: str):
        """标记provider成功，更新粘滞状态"""
        self._last_successful_provider = provider_name
        # 在请求成功完成时更新最后请求时间
        self._last_request_time = time.time()
    
    def mark_provider_used(self, provider_name: str):
        """标记provider被使用（无论成功失败），用于sticky逻辑"""
        # 只要没有触发failover，就启用sticky
        self._last_successful_provider = provider_name
        self._last_request_time = time.time()
    
    def get_provider_by_name(self, name: str) -> Optional[Provider]:
        """根据名称获取provider"""
        for provider in self.providers:
            if provider.name == name:
                return provider
        return None
    
    def get_provider_headers(self, provider: Provider, original_headers: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """Get authentication headers for a provider, optionally merging with original headers"""
        headers = {
            "Content-Type": "application/json"
        }
        
        debug(LogRecord(
            event=LogEvent.GET_PROVIDER_HEADERS_START.value,
            message=f"Provider {provider.name}: auth_type={provider.auth_type}, auth_value=[REDACTED]"
        ))
        
        
        # 如果提供了原始请求头，先复制它们（排除需要替换的认证头、host头和content-length头）
        if original_headers:
            for key, value in original_headers.items():
                # 跳过需要替换的认证相关头部、host头部和content-length头部
                if key.lower() not in ['authorization', 'x-api-key', 'host', 'content-length']:
                    headers[key] = value
        
        # 检查auth_value模式
        if provider.auth_value == "passthrough":
            # 透传模式：使用原始请求的认证头
            if original_headers:
                # 保留原始请求的Authorization和x-api-key头部（不区分大小写查找）
                for key, value in original_headers.items():
                    if key.lower() == "authorization":
                        headers["Authorization"] = value
                    elif key.lower() == "x-api-key":
                        headers["x-api-key"] = value
            # 为Anthropic类型的provider添加版本头
            if provider.type == ProviderType.ANTHROPIC:
                headers["anthropic-version"] = "2023-06-01"
        elif provider.auth_type == AuthType.OAUTH:
            # OAuth模式：从OAuth manager获取token
            try:
                from oauth import get_oauth_manager
                oauth_manager = get_oauth_manager()
            except ImportError:
                oauth_manager = None
            
            debug(LogRecord(
                event=LogEvent.OAUTH_MANAGER_CHECK.value, 
                message=f"OAuth manager status: {oauth_manager is not None}, type: {type(oauth_manager)}"
            ))
            if not oauth_manager:
                # OAuth manager未初始化，触发OAuth授权流程
                self.handle_oauth_authorization_required(provider)
                from httpx import HTTPStatusError
                import httpx
                response = httpx.Response(
                    status_code=401,
                    text="Unauthorized: OAuth manager not initialized",
                    request=httpx.Request("POST", "http://example.com")
                )
                raise HTTPStatusError("401 Unauthorized", request=response.request, response=response)
            
            access_token = oauth_manager.get_current_token()
            if not access_token:
                # 触发OAuth授权流程 (永远启用)
                self.handle_oauth_authorization_required(provider)
                # 创建一个401错误来触发标准的错误处理流程
                from httpx import HTTPStatusError
                import httpx
                response = httpx.Response(
                    status_code=401,
                    text="Unauthorized: No valid token available",
                    request=httpx.Request("POST", "http://example.com")
                )
                raise HTTPStatusError("401 Unauthorized", request=response.request, response=response)
            
            # 使用OAuth token作为Bearer token
            headers["Authorization"] = f"Bearer {access_token}"
            
            # 为Anthropic类型的provider添加版本头
            if provider.type == ProviderType.ANTHROPIC:
                headers["anthropic-version"] = "2023-06-01"
        else:
            # 正常模式：使用配置的认证值
            if provider.auth_type == AuthType.API_KEY:
                if provider.type == ProviderType.ANTHROPIC:
                    headers["x-api-key"] = provider.auth_value
                    headers["anthropic-version"] = "2023-06-01"
                else:  # OpenAI compatible
                    headers["Authorization"] = f"Bearer {provider.auth_value}"
            elif provider.auth_type == AuthType.AUTH_TOKEN:
                # 对于使用auth_token的服务商
                headers["Authorization"] = f"Bearer {provider.auth_value}"
                if provider.type == ProviderType.ANTHROPIC:
                    headers["anthropic-version"] = "2023-06-01"
        
        return headers
    
    def get_request_url(self, provider: Provider, endpoint: str) -> str:
        """Get full request URL for a provider"""
        base_url = provider.base_url.rstrip('/')
        endpoint = endpoint.lstrip('/')
        return f"{base_url}/{endpoint}"
    
    def get_status(self) -> Dict[str, Any]:
        """Get status of all providers and model routes"""
        status = {
            "total_providers": len(self.providers),
            "healthy_providers": len(self.get_healthy_providers()),
            "selection_strategy": self.selection_strategy.value,
            "total_model_routes": len(self.model_routes),
            "providers": []
        }
        
        cooldown = self.get_failure_cooldown()
        for provider in self.providers:
            provider_status = {
                "name": provider.name,
                "type": provider.type.value,
                "base_url": provider.base_url,
                "enabled": provider.enabled,
                "healthy": provider.is_healthy(cooldown),
                "failure_count": provider.failure_count,
                "last_failure_time": provider.last_failure_time,
                "proxy": provider.proxy
            }
            status["providers"].append(provider_status)
        
        return status
    
    def reload_config(self):
        """Reload configuration from file"""
        self.load_config()
    
    def handle_oauth_authorization_required(self, provider: Provider, http_status_code: int = 401) -> str:
        """Handle 401/403 authorization required error for OAuth providers"""
        if provider.name == "Claude Code Official":
            # Check if OAuth manager is available
            try:
                from oauth import get_oauth_manager
                oauth_manager = get_oauth_manager()
            except ImportError:
                oauth_manager = None
                
            if not oauth_manager:
                print("\n" + "="*80)
                print("❌ OAUTH MANAGER NOT AVAILABLE")
                print("="*80)
                print("The OAuth manager failed to initialize properly.")
                print("Please check the logs for initialization errors.")
                print("OAuth authentication is not available at this time.")
                print("="*80)
                print()
                return ""
            
            # Print instructions to console
            status_text = "401 Unauthorized" if http_status_code == 401 else "403 Forbidden"
            print("\n" + "="*80)
            print("🔐 CLAUDE CODE OFFICIAL AUTHORIZATION REQUIRED")
            print("="*80)
            print(f"Provider '{provider.name}' returned {status_text}.")
            print("Please complete the OAuth authorization process:")
            print()
            print("1. 🌐 Click the following URL to generate and get authorization link:")
            print(f"   http://localhost:9090/oauth/generate-url")
            print()
            print("2. 📝 After successful login, you will be redirected to a callback URL.")
            print("   Copy the 'code' parameter from the callback URL.")
            print()
            print("3. 💻 Run the following command to complete the authorization:")
            print(f"   curl -X POST http://localhost:9090/oauth/exchange-code -d '{{\"code\": \"YOUR_CODE\", \"account_email\": \"user@example.com\"}}'")
            print("   Note: account_email is required for account identification and preventing duplicates")
            print()
            print("4. 🔄 The system will automatically exchange the code for tokens and start using them.")
            print("="*80)
            print()
            
            return "http://localhost:9090/oauth/generate-url"
        
        return ""
    
    def should_failover_on_error(self, error: Exception, http_status_code: Optional[int] = None, error_type: Optional[str] = None) -> bool:
        """
        判断是否应该对错误进行failover重试
        
        Args:
            error: 捕获的异常
            http_status_code: HTTP状态码（如果有）
            error_type: 错误类型字符串（如果有）
            
        Returns:
            bool: True表示应该failover，False表示直接返回给客户端
        """
        # 获取配置中的failover错误类型和HTTP状态码
        failover_error_types = self.settings.get('failover_error_types', [])
        failover_http_codes = self.settings.get('failover_http_codes', [])
        
        # 1. 检查HTTP状态码
        if http_status_code and http_status_code in failover_http_codes:
            return True
        
        # 2. 检查明确的错误类型
        if error_type and error_type in failover_error_types:
            return True
        
        # 3. 检查异常类型
        error_class_name = error.__class__.__name__.lower()
        error_message = str(error).lower()
        
        # 网络连接错误
        if isinstance(error, (httpx.ConnectError, httpx.ConnectTimeout)):
            return "connection_error" in failover_error_types or "connect_timeout" in failover_error_types
        
        # 读取超时错误
        if isinstance(error, httpx.ReadTimeout):
            return "read_timeout" in failover_error_types or "timeout_error" in failover_error_types
        
        # 池超时错误
        if isinstance(error, httpx.PoolTimeout):
            return "pool_timeout" in failover_error_types or "timeout_error" in failover_error_types
        
        # 一般超时错误
        if isinstance(error, httpx.TimeoutException):
            return "timeout_error" in failover_error_types
        
        # SSL错误
        if "ssl" in error_class_name or "certificate" in error_message:
            return "ssl_error" in failover_error_types
        
        # 检查错误消息中的关键词
        for error_type_key in failover_error_types:
            if error_type_key.lower() in error_message:
                return True
        
        # 默认不进行failover（直接返回给客户端）
        return False
    
    def get_error_classification(self, error: Exception, http_status_code: Optional[int] = None) -> tuple[str, bool]:
        """
        获取错误分类信息
        
        Args:
            error: 捕获的异常
            http_status_code: HTTP状态码（如果有）
            
        Returns:
            tuple: (error_type, should_failover)
        """
        # 确定错误类型
        if isinstance(error, httpx.ConnectError):
            error_type = "connection_error"
        elif isinstance(error, httpx.ReadTimeout):
            error_type = "read_timeout"
        elif isinstance(error, httpx.ConnectTimeout):
            error_type = "connect_timeout"
        elif isinstance(error, httpx.PoolTimeout):
            error_type = "pool_timeout"
        elif isinstance(error, httpx.TimeoutException):
            error_type = "timeout_error"
        elif http_status_code == 500:
            error_type = "internal_server_error"
        elif http_status_code == 502:
            error_type = "bad_gateway"
        elif http_status_code == 503:
            error_type = "service_unavailable"
        elif http_status_code == 504:
            error_type = "gateway_timeout"
        elif http_status_code == 429:
            error_type = "rate_limit_exceeded"
        else:
            error_type = "unknown_error"
        
        # 判断是否应该failover
        should_failover = self.should_failover_on_error(error, http_status_code, error_type)
        
        return error_type, should_failover

    def update_provider_auth(self, provider_name: str, new_auth_value: str):
        """更新provider的认证值（用于token刷新）"""
        provider = self.get_provider_by_name(provider_name)
        if provider:
            provider.auth_value = new_auth_value
            return True
        return False

    def record_health_check_result(self, provider_name: str, is_error_detected: bool, error_type: Optional[str] = None, request_id: str = "") -> bool:
        """记录健康检查结果，返回是否应该标记为unhealthy
        
        Args:
            provider_name: Provider名称
            is_error_detected: 是否检测到错误
            error_type: 错误类型
            request_id: 请求ID（用于日志）
            
        Returns:
            bool: 是否应该标记为unhealthy并触发failover
        """
        current_time = time.time()
        
        with self._lock:
            if is_error_detected:
                # 记录错误
                self._error_counts[provider_name] = self._error_counts.get(provider_name, 0) + 1
                self._last_error_time[provider_name] = current_time
                
                error_count = self._error_counts[provider_name]
                
                debug(LogRecord(
                    LogEvent.PROVIDER_HEALTH_ERROR_RECORDED.value,
                    f"Recorded error for provider {provider_name}: count={error_count}/{self.unhealthy_threshold}, error_type={error_type}",
                    request_id,
                    {
                        "provider": provider_name,
                        "error_count": error_count,
                        "threshold": self.unhealthy_threshold,
                        "error_type": error_type
                    }
                ))
                
                # 检查是否达到阈值
                if error_count >= self.unhealthy_threshold:
                    # 达到阈值，标记为unhealthy
                    provider = self.get_provider_by_name(provider_name)
                    if provider:
                        provider.mark_failure()
                        
                    warning(LogRecord(
                        LogEvent.PROVIDER_MARKED_UNHEALTHY.value,
                        f"Provider {provider_name} marked unhealthy after {error_count} errors (threshold: {self.unhealthy_threshold})",
                        request_id,
                        {
                            "provider": provider_name,
                            "error_count": error_count,
                            "threshold": self.unhealthy_threshold,
                            "error_type": error_type
                        }
                    ))
                    return True  # 应该标记为unhealthy并failover
                else:
                    debug(LogRecord(
                        LogEvent.PROVIDER_HEALTH_ERROR_BELOW_THRESHOLD.value, 
                        f"Provider {provider_name} error count {error_count} below threshold {self.unhealthy_threshold}",
                        request_id,
                        {
                            "provider": provider_name,
                            "error_count": error_count,
                            "threshold": self.unhealthy_threshold
                        }
                    ))
                    return False  # 错误数不够，不标记unhealthy
            else:
                # 成功请求
                self._last_success_time[provider_name] = current_time
                
                if self.unhealthy_reset_on_success:
                    # 成功后重置错误计数
                    old_count = self._error_counts.get(provider_name, 0)
                    if old_count > 0:
                        self._error_counts[provider_name] = 0
                        self._last_error_time.pop(provider_name, None)
                        
                        debug(LogRecord(
                            LogEvent.PROVIDER_HEALTH_ERROR_COUNT_RESET.value,
                            f"Provider {provider_name} error count reset from {old_count} to 0 after success",
                            request_id,
                            {
                                "provider": provider_name,
                                "old_error_count": old_count,
                                "reset_reason": "success"
                            }
                        ))
                return False  # 成功请求不需要failover
    
    def reset_error_counts_on_timeout(self):
        """按照超时配置重置错误计数"""
        current_time = time.time()
        
        with self._lock:
            providers_to_reset = []
            
            for provider_name, last_error_time in self._last_error_time.items():
                if current_time - last_error_time > self.unhealthy_reset_timeout:
                    providers_to_reset.append(provider_name)
            
            for provider_name in providers_to_reset:
                old_count = self._error_counts.get(provider_name, 0)
                if old_count > 0:
                    self._error_counts[provider_name] = 0
                    self._last_error_time.pop(provider_name, None)
                    
                    debug(LogRecord(
                        LogEvent.PROVIDER_HEALTH_ERROR_COUNT_TIMEOUT_RESET.value,
                        f"Provider {provider_name} error count reset from {old_count} to 0 after timeout ({self.unhealthy_reset_timeout}s)",
                        "",  # request_id not available in timeout reset
                        {
                            "provider": provider_name,
                            "old_error_count": old_count,
                            "reset_reason": "timeout",
                            "timeout_seconds": self.unhealthy_reset_timeout
                        }
                    ))
    
    def get_provider_error_status(self, provider_name: str) -> Dict[str, Any]:
        """获取Provider的错误状态信息"""
        with self._lock:
            return {
                "error_count": self._error_counts.get(provider_name, 0),
                "threshold": self.unhealthy_threshold,
                "last_error_time": self._last_error_time.get(provider_name),
                "last_success_time": self._last_success_time.get(provider_name),
                "reset_on_success": self.unhealthy_reset_on_success,
                "reset_timeout": self.unhealthy_reset_timeout
            }

    def shutdown(self):
        """Shutdown the provider manager"""
        pass