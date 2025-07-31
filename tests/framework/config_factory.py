"""
Dynamic configuration factory for test scenarios.
"""

import uuid
from typing import Dict, List, Any, Optional
from .test_scenario import Scenario, ProviderConfig, ProviderBehavior, ExpectedBehavior


class TestConfigFactory:
    """Dynamic test configuration generator."""
    
    def __init__(self, mock_server_base: str = "http://localhost:8998", default_port: int = 9091):
        self.mock_server_base = mock_server_base
        self.default_port = default_port
    
    def create_config(self, scenario: Scenario, model_name: Optional[str] = None) -> Dict[str, Any]:
        """Generate complete configuration from test scenario."""
        # Use scenario model_name if provided, otherwise use passed model_name or generate one
        final_model_name = scenario.model_name or model_name or f"test-{uuid.uuid4().hex[:8]}"
        
        config = {
            "providers": self._create_providers(scenario.providers),
            "model_routes": self._create_model_routes(final_model_name, scenario.providers),
            "settings": self._create_settings(scenario.settings_override)
        }
        
        return config
    
    def _create_providers(self, provider_configs: List[ProviderConfig]) -> List[Dict[str, Any]]:
        """Generate provider configurations."""
        providers = []
        
        for provider_config in provider_configs:
            provider = {
                "name": provider_config.name,
                "type": provider_config.provider_type or "anthropic",  # Use provider type from config
                "base_url": f"{self.mock_server_base}/mock-provider/{provider_config.name}",
                "auth_type": "api_key",
                "auth_value": "test-key",
                "enabled": True,
                "priority": provider_config.priority
            }
            providers.append(provider)
        
        return providers
    
    def _create_model_routes(self, model_name: str, provider_configs: List[ProviderConfig]) -> Dict[str, List[Dict[str, Any]]]:
        """Generate model routing configuration."""
        routes = []
        
        for provider_config in provider_configs:
            route = {
                "provider": provider_config.name,
                "model": "passthrough",
                "priority": provider_config.priority
            }
            routes.append(route)
        
        return {model_name: routes}
    
    def _create_settings(self, settings_override: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Generate minimal settings configuration for tests."""
        # Minimal essential settings for testing
        base_settings = {
            "host": "127.0.0.1",
            "port": self.default_port,  # Use factory's default port
            "log_level": "DEBUG",
            "app_name": "Claude Code Provider Balancer (Test)",
            "app_version": "0.1.6-test",
            "oauth": {
                "enable_persistence": False,
                "enable_auto_refresh": False
            },
            "reload": False
        }
        
        # Apply any scenario-specific overrides
        if settings_override:
            base_settings = self._deep_merge_dict(base_settings, settings_override)
        
        return base_settings
    
    def _deep_merge_dict(self, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """Deep merge two dictionaries."""
        result = base.copy()
        
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge_dict(result[key], value)
            else:
                result[key] = value
        
        return result
    
    # Convenience methods removed - use create_config with scenarios directly