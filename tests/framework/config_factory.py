"""
Dynamic configuration factory for test scenarios.
"""

import uuid
from typing import Dict, List, Any, Optional
from .test_scenario import Scenario, ProviderConfig, ProviderBehavior, ExpectedBehavior


class TestConfigFactory:
    """Dynamic test configuration generator."""
    
    def __init__(self, mock_server_base: str = "http://localhost:8998"):
        self.mock_server_base = mock_server_base
    
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
        """Generate base test settings with optional overrides."""
        base_settings = {
            "selection_strategy": "priority",
            "timeouts": {
                "non_streaming": {
                    "connect_timeout": 10,
                    "read_timeout": 30,
                    "pool_timeout": 10
                },
                "streaming": {
                    "connect_timeout": 10,
                    "read_timeout": 30,
                    "pool_timeout": 10
                },
                "caching": {
                    "deduplication_timeout": 60
                }
            },
            "sticky_provider_duration": 30,
            "failure_cooldown": 30,
            "unhealthy_threshold": 2,
            "unhealthy_reset_on_success": True,
            "unhealthy_reset_timeout": 60,
            "unhealthy_exception_patterns": [
                "connection",
                "timeout", 
                "ssl",
                "network"
            ],
            "unhealthy_response_body_patterns": [
                '"error"\\s*:\\s*".*insufficient.*credits"',
                '"error_type"\\s*:\\s*"quota_exceeded"',
                '"message"\\s*:\\s*".*rate.?limit.*"',
                '"detail"\\s*:\\s*".*没有可用.*"',
                '"type"\\s*:\\s*"error"',
                'data:\\s*\\{"error"',
                'event:\\s*error'
            ],
            "unhealthy_http_codes": [402, 403, 404, 408, 429, 500, 502, 503, 504, 520, 521, 522, 523, 524],
            "log_level": "DEBUG",
            "log_color": True,
            "log_file_path": "logs/test-logs.jsonl",
            "enable_detailed_request_logging": True,  # Enable detailed request/response logging for tests
            "host": "127.0.0.1",
            "port": 8999,
            "app_name": "ClaudeCode Providers Balancer - Test Mode",
            "app_version": "0.1.1-test",
            "oauth": {
                "enable_persistence": False,
                "enable_auto_refresh": False
            },
            "deduplication": {
                "enabled": True,
                "include_max_tokens_in_signature": False,
                "sse_error_cleanup_delay": 3
            },
            "testing": {
                "simulate_delay": False,
                "delay_seconds": 0
            }
        }
        
        # Apply overrides if provided
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
    
    # Convenience methods for common scenarios
    def create_simple_success_config(self, model_name: Optional[str] = None) -> Dict[str, Any]:
        """Create simple success scenario configuration."""
        scenario = Scenario(
            name="simple_success",
            providers=[ProviderConfig("success_provider", ProviderBehavior.SUCCESS)],
            expected_behavior=ExpectedBehavior.SUCCESS
        )
        return self.create_config(scenario, model_name)
    
    def create_failover_config(self, model_name: Optional[str] = None) -> Dict[str, Any]:
        """Create failover scenario configuration."""
        scenario = Scenario(
            name="failover_test", 
            providers=[
                ProviderConfig("primary_fail", ProviderBehavior.ERROR, priority=1),
                ProviderConfig("secondary_success", ProviderBehavior.SUCCESS, priority=2)
            ],
            expected_behavior=ExpectedBehavior.FAILOVER
        )
        return self.create_config(scenario, model_name)
    
    def create_duplicate_test_config(self, model_name: Optional[str] = None) -> Dict[str, Any]:
        """Create duplicate request test configuration."""
        scenario = Scenario(
            name="duplicate_test",
            providers=[
                ProviderConfig(
                    "duplicate_provider", 
                    ProviderBehavior.DUPLICATE_CACHE,
                    response_data={"content": "cached_response"}
                )
            ],
            expected_behavior=ExpectedBehavior.SUCCESS
        )
        return self.create_config(scenario, model_name)
    
    def create_all_providers_fail_config(self, model_name: Optional[str] = None) -> Dict[str, Any]:
        """Create all providers fail scenario configuration."""
        scenario = Scenario(
            name="all_fail",
            providers=[
                ProviderConfig("fail1", ProviderBehavior.ERROR, priority=1),
                ProviderConfig("fail2", ProviderBehavior.ERROR, priority=2)
            ],
            expected_behavior=ExpectedBehavior.ALL_FAIL
        )
        return self.create_config(scenario, model_name)
    
    def create_timeout_test_config(self, model_name: Optional[str] = None) -> Dict[str, Any]:
        """Create timeout test scenario configuration."""
        scenario = Scenario(
            name="timeout_test",
            providers=[
                ProviderConfig("timeout_provider", ProviderBehavior.TIMEOUT, delay_ms=5000)
            ],
            expected_behavior=ExpectedBehavior.TIMEOUT
        )
        return self.create_config(scenario, model_name)