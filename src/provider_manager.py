"""
Provider Manager for Claude Code Provider Balancer
Manages multiple Claude Code and OpenAI-compatible providers with load balancing and failure recovery.
"""

import os
import time
import yaml
from typing import List, Optional, Dict, Any
from pathlib import Path
from dataclasses import dataclass
from enum import Enum


class ProviderType(str, Enum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"


class AuthType(str, Enum):
    API_KEY = "api_key"
    AUTH_TOKEN = "auth_token"


@dataclass
class Provider:
    name: str
    type: ProviderType
    base_url: str
    auth_type: AuthType
    auth_value: str
    big_model: str
    small_model: str
    enabled: bool = True
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


class ProviderManager:
    def __init__(self, config_path: str = "providers.yaml"):
        # Determine the absolute path to the config file
        if not os.path.isabs(config_path):
            # If relative path, look for it in project root (one level up from src)
            current_dir = Path(__file__).parent
            project_root = current_dir.parent
            config_path = project_root / config_path
        
        self.config_path = Path(config_path)
        self.providers: List[Provider] = []
        self.current_provider_index: int = 0
        self.settings: Dict[str, Any] = {}
        self.load_config()
    
    def load_config(self):
        """Load providers configuration from YAML file"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            self.settings = config.get('settings', {})
            
            providers_config = config.get('providers', [])
            self.providers = []
            
            for provider_config in providers_config:
                if provider_config.get('enabled', True):
                    provider = Provider(
                        name=provider_config['name'],
                        type=ProviderType(provider_config['type']),
                        base_url=provider_config['base_url'],
                        auth_type=AuthType(provider_config['auth_type']),
                        auth_value=provider_config['auth_value'],
                        big_model=provider_config['big_model'],
                        small_model=provider_config['small_model'],
                        enabled=provider_config.get('enabled', True)
                    )
                    self.providers.append(provider)
            
            if not self.providers:
                raise ValueError("No enabled providers found in configuration")
                
        except Exception as e:
            raise RuntimeError(f"Failed to load provider configuration: {e}")
    
    def get_failure_cooldown(self) -> int:
        """Get failure cooldown time from settings"""
        return self.settings.get('failure_cooldown', 60)
    
    def get_request_timeout(self) -> int:
        """Get request timeout from settings"""
        return self.settings.get('request_timeout', 30)
    
    def get_healthy_providers(self) -> List[Provider]:
        """Get list of healthy (non-failed) providers"""
        cooldown = self.get_failure_cooldown()
        return [p for p in self.providers if p.enabled and p.is_healthy(cooldown)]
    
    def get_current_provider(self) -> Optional[Provider]:
        """Get current provider for load balancing"""
        healthy_providers = self.get_healthy_providers()
        
        if not healthy_providers:
            return None
        
        # 如果当前provider还健康，继续使用
        if (self.current_provider_index < len(self.providers) and 
            self.providers[self.current_provider_index] in healthy_providers):
            return self.providers[self.current_provider_index]
        
        # 否则选择第一个健康的provider
        for i, provider in enumerate(self.providers):
            if provider in healthy_providers:
                self.current_provider_index = i
                return provider
        
        return None
    
    def switch_to_next_provider(self) -> Optional[Provider]:
        """Switch to next healthy provider after current one fails"""
        if not self.providers:
            return None
        
        # 标记当前provider失败
        if self.current_provider_index < len(self.providers):
            current_provider = self.providers[self.current_provider_index]
            current_provider.mark_failure()
        
        # 寻找下一个健康的provider
        healthy_providers = self.get_healthy_providers()
        if not healthy_providers:
            return None
        
        # 从当前位置开始找下一个健康的
        start_index = (self.current_provider_index + 1) % len(self.providers)
        for i in range(len(self.providers)):
            check_index = (start_index + i) % len(self.providers)
            provider = self.providers[check_index]
            if provider in healthy_providers:
                self.current_provider_index = check_index
                return provider
        
        return None
    
    def mark_provider_success(self, provider: Provider):
        """Mark a provider as successful"""
        provider.mark_success()
    
    def get_provider_headers(self, provider: Provider, original_headers: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """Get authentication headers for a provider, optionally merging with original headers"""
        headers = {
            "Content-Type": "application/json"
        }
        
        # 如果提供了原始请求头，先复制它们（排除需要替换的认证头、host头和content-length头）
        if original_headers:
            for key, value in original_headers.items():
                # 跳过需要替换的认证相关头部、host头部和content-length头部
                if key.lower() not in ['authorization', 'x-api-key', 'host', 'content-length']:
                    headers[key] = value
        
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
        
        # 为anyrouter等服务商添加更多类似Claude Code的头部（如果原始头部中没有的话）
        if provider.name == "anyrouter":
            if "User-Agent" not in headers:
                headers["User-Agent"] = "claude-cli/1.0.52 (external, cli)"
            if "Accept" not in headers:
                headers["Accept"] = "application/json"
            if "Accept-Encoding" not in headers:
                headers["Accept-Encoding"] = "gzip, deflate, br"
        
        return headers
    
    def select_model(self, provider: Provider, requested_model: str) -> str:
        """Select appropriate model based on requested Claude model"""
        # 判断是大模型还是小模型的逻辑
        requested_lower = requested_model.lower()
        
        # Opus和Sonnet被认为是大模型
        if any(keyword in requested_lower for keyword in ['opus', 'sonnet']):
            target_model = provider.big_model
        # Haiku被认为是小模型
        elif 'haiku' in requested_lower:
            target_model = provider.small_model
        else:
            # 默认使用大模型
            target_model = provider.big_model
        
        # 如果配置的模型名为"passthrough"，则透传原始请求的模型名
        if target_model == "passthrough":
            return requested_model
        
        return target_model
    
    def get_request_url(self, provider: Provider, endpoint: str) -> str:
        """Get full request URL for a provider"""
        base_url = provider.base_url.rstrip('/')
        endpoint = endpoint.lstrip('/')
        return f"{base_url}/{endpoint}"
    
    def get_status(self) -> Dict[str, Any]:
        """Get status of all providers"""
        status = {
            "total_providers": len(self.providers),
            "healthy_providers": len(self.get_healthy_providers()),
            "current_provider": None,
            "providers": []
        }
        
        current = self.get_current_provider()
        if current:
            status["current_provider"] = current.name
        
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
                "big_model": provider.big_model,
                "small_model": provider.small_model
            }
            status["providers"].append(provider_status)
        
        return status
    
    def reload_config(self):
        """Reload configuration from file"""
        self.load_config()