"""
Test environment context manager for automatic configuration management.
"""

import asyncio
import yaml
import tempfile
import os
import httpx
from typing import Optional, Dict, Any
from pathlib import Path

from .test_scenario import Scenario
from .config_factory import TestConfigFactory
from .test_context import TestContextManager
from .balancer_test_server import BalancerTestServer


class Environment:
    """
    Test environment context manager.
    
    Automatically generates and applies test configuration based on scenarios,
    then cleans up when done.
    """
    
    def __init__(
        self, 
        scenario: Scenario, 
        model_name: Optional[str] = None,
        config_factory: Optional[TestConfigFactory] = None,
        mock_server_url: str = "http://localhost:8998",
        balancer_test_port: int = 9091
    ):
        self.scenario = scenario
        self.model_name = model_name or scenario.model_name
        self.config_factory = config_factory or TestConfigFactory()
        self.mock_server_url = mock_server_url
        self.balancer_test_port = balancer_test_port
        
        # Internal state
        self._generated_config: Optional[Dict[str, Any]] = None
        self._temp_config_file: Optional[str] = None
        self._original_config_backup: Optional[str] = None
        self._balancer_server: Optional[BalancerTestServer] = None
        
    async def __aenter__(self) -> 'Environment':
        """Enter test environment - generate and apply configuration."""
        try:
            # 1. Generate configuration from scenario
            self._generated_config = self.config_factory.create_config(
                self.scenario, 
                self.model_name
            )
            
            # 2. Set test context locally
            TestContextManager.set_scenario(self.scenario)
            
            # 3. Set test context on mock server (cross-process communication)
            await self._set_mock_server_context()
            
            # 4. Start balancer test server with generated configuration
            await self._start_balancer_server()
            
            return self
            
        except Exception as e:
            # Cleanup on error
            await self._cleanup()
            raise RuntimeError(f"Failed to set up test environment: {str(e)}") from e
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit test environment - restore original configuration."""
        await self._cleanup()
    
    async def _start_balancer_server(self):
        """Start the balancer test server with generated configuration."""
        try:
            # Create and start balancer test server
            mock_server_port = int(self.mock_server_url.split(':')[-1])
            self._balancer_server = BalancerTestServer(
                test_port=self.balancer_test_port,
                mock_server_port=mock_server_port
            )
            
            await self._balancer_server.start_with_config(self._generated_config)
            
        except Exception as e:
            raise RuntimeError(f"Failed to start balancer test server: {str(e)}") from e
    
    async def _set_mock_server_context(self):
        """Set test context on mock server via HTTP API."""
        try:
            # Convert scenario to JSON-serializable format
            context_data = {
                "name": self.scenario.name,
                "expected_behavior": self.scenario.expected_behavior.value,
                "model_name": self.scenario.model_name,
                "description": self.scenario.description,
                "providers": [
                    {
                        "name": p.name,
                        "behavior": p.behavior.value,
                        "response_data": p.response_data,
                        "delay_ms": p.delay_ms,
                        "priority": p.priority,
                        "error_count": p.error_count,
                        "error_http_code": p.error_http_code,
                        "error_message": p.error_message,
                        "provider_type": p.provider_type
                    }
                    for p in self.scenario.providers
                ]
            }
            
            # Handle JSON serialization manually to support invalid Unicode in test data
            import json
            try:
                json_data = json.dumps(context_data, ensure_ascii=False)
                json_bytes = json_data.encode('utf-8')
            except UnicodeEncodeError:
                # Use ASCII encoding fallback for invalid Unicode characters in test data
                json_data = json.dumps(context_data, ensure_ascii=True)
                json_bytes = json_data.encode('utf-8')
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.mock_server_url}/mock-set-context",
                    content=json_bytes,
                    headers={"Content-Type": "application/json"},
                    timeout=5.0
                )
                
                if response.status_code != 200:
                    raise RuntimeError(f"Failed to set mock server context: {response.status_code} {response.text}")
                
                result = response.json()
                if result.get("status") != "success":
                    raise RuntimeError(f"Mock server rejected context: {result.get('message')}")
                    
        except httpx.RequestError as e:
            # Mock server might not be running - log warning but don't fail
            import logging
            logging.warning(f"Could not set mock server context (server may not be running): {e}")
        except Exception as e:
            raise RuntimeError(f"Failed to set mock server context: {str(e)}") from e
    
    async def _save_temp_config(self) -> str:
        """Save generated configuration to a temporary file."""
        with tempfile.NamedTemporaryFile(
            mode='w', 
            suffix='.yaml', 
            delete=False,
            prefix=f'test_config_{self.scenario.name}_'
        ) as f:
            yaml.dump(self._generated_config, f, default_flow_style=False)
            return f.name
    
    async def _cleanup(self):
        """Clean up test environment."""
        try:
            # Stop balancer test server
            if self._balancer_server:
                await self._balancer_server.stop()
                self._balancer_server = None
            
            # Clear local test context
            TestContextManager.clear()
            
            # Clear mock server context
            await self._clear_mock_server_context()
            
            # Remove temporary config file
            if self._temp_config_file and os.path.exists(self._temp_config_file):
                os.unlink(self._temp_config_file)
                self._temp_config_file = None
            
        except Exception as e:
            # Log cleanup errors but don't raise them
            import logging
            logging.warning(f"Error during test environment cleanup: {str(e)}")
    
    async def _clear_mock_server_context(self):
        """Clear test context on mock server."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.delete(
                    f"{self.mock_server_url}/mock-clear-context",
                    timeout=5.0
                )
                # Don't fail if clearing context fails
                if response.status_code != 200:
                    import logging
                    logging.warning(f"Failed to clear mock server context: {response.status_code}")
                    
        except httpx.RequestError:
            # Mock server might not be running - ignore
            pass
        except Exception as e:
            import logging
            logging.warning(f"Error clearing mock server context: {str(e)}")
    
    @property
    def effective_model_name(self) -> str:
        """Get the effective model name for this test environment."""
        if self.model_name:
            return self.model_name
        elif self.scenario.model_name:
            return self.scenario.model_name
        else:
            # Extract from generated config
            if self._generated_config and 'model_routes' in self._generated_config:
                routes = self._generated_config['model_routes']
                if routes:
                    return list(routes.keys())[0]
        
        raise RuntimeError("No model name available in test environment")
    
    @property
    def config(self) -> Dict[str, Any]:
        """Get the generated configuration."""
        if not self._generated_config:
            raise RuntimeError("Configuration not generated yet")
        return self._generated_config
    
    @property
    def balancer_url(self) -> str:
        """Get the balancer test server URL."""
        if not self._balancer_server:
            raise RuntimeError("Balancer server not started yet")
        return self._balancer_server.base_url
    
    def get_provider_config(self, provider_name: str):
        """Get provider configuration by name."""
        return self.scenario.get_provider_config(provider_name)
    
    def get_expected_behavior(self):
        """Get expected test behavior."""
        return self.scenario.expected_behavior


class ConfigurableEnvironment(Environment):
    """
    Test environment with more configuration options.
    
    Allows for more complex test setups with custom settings.
    """
    
    def __init__(
        self,
        scenario: Scenario,
        model_name: Optional[str] = None,
        config_factory: Optional[TestConfigFactory] = None,
        auto_reload_config: bool = True,
        preserve_logs: bool = False
    ):
        super().__init__(scenario, model_name, config_factory)
        self.auto_reload_config = auto_reload_config
        self.preserve_logs = preserve_logs
    
    async def reload_configuration(self):
        """Manually reload configuration (useful for testing config changes)."""
        if not self._generated_config:
            raise RuntimeError("No configuration to reload")
        
        # Re-apply current configuration
        await self._apply_configuration()
    
    async def update_scenario(self, new_scenario: Scenario):
        """Update the test scenario and reload configuration."""
        self.scenario = new_scenario
        
        # Regenerate configuration
        self._generated_config = self.config_factory.create_config(
            new_scenario, 
            self.model_name
        )
        
        # Update context
        TestContextManager.set_scenario(new_scenario)
        
        # Reload if enabled
        if self.auto_reload_config:
            await self.reload_configuration()


# Convenience functions for common test patterns
async def with_simple_success_test(test_func, model_name: Optional[str] = None):
    """Run test with simple success scenario."""
    from .test_scenario import Scenario, ProviderConfig, ProviderBehavior, ExpectedBehavior
    
    scenario = Scenario(
        name="simple_success",
        providers=[ProviderConfig("success_provider", ProviderBehavior.SUCCESS)],
        expected_behavior=ExpectedBehavior.SUCCESS
    )
    
    async with Environment(scenario, model_name) as env:
        return await test_func(env)


async def with_failover_test(test_func, model_name: Optional[str] = None):
    """Run test with failover scenario."""
    from .test_scenario import Scenario, ProviderConfig, ProviderBehavior, ExpectedBehavior
    
    scenario = Scenario(
        name="failover_test",
        providers=[
            ProviderConfig("primary_fail", ProviderBehavior.ERROR, priority=1),
            ProviderConfig("secondary_success", ProviderBehavior.SUCCESS, priority=2)
        ],
        expected_behavior=ExpectedBehavior.FAILOVER
    )
    
    async with Environment(scenario, model_name) as env:
        return await test_func(env)