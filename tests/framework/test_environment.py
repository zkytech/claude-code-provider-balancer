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

from .test_scenario import TestScenario
from .config_factory import TestConfigFactory
from .test_context import TestContextManager


class TestEnvironment:
    """
    Test environment context manager.
    
    Automatically generates and applies test configuration based on scenarios,
    then cleans up when done.
    """
    
    def __init__(
        self, 
        scenario: TestScenario, 
        model_name: Optional[str] = None,
        config_factory: Optional[TestConfigFactory] = None,
        mock_server_url: str = "http://localhost:8998"
    ):
        self.scenario = scenario
        self.model_name = model_name or scenario.model_name
        self.config_factory = config_factory or TestConfigFactory()
        self.mock_server_url = mock_server_url
        
        # Internal state
        self._generated_config: Optional[Dict[str, Any]] = None
        self._temp_config_file: Optional[str] = None
        self._original_config_backup: Optional[str] = None
        self._app_instance = None
        
    async def __aenter__(self) -> 'TestEnvironment':
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
            
            # 4. Apply configuration to the running application
            await self._apply_configuration()
            
            return self
            
        except Exception as e:
            # Cleanup on error
            await self._cleanup()
            raise RuntimeError(f"Failed to set up test environment: {str(e)}") from e
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit test environment - restore original configuration."""
        await self._cleanup()
    
    async def _apply_configuration(self):
        """Apply the generated configuration to the running application."""
        try:
            # For now, we'll save to a temporary config file
            # In a real implementation, this would reload the app configuration
            self._temp_config_file = await self._save_temp_config()
            
            # TODO: Implement actual configuration reload
            # This would involve calling the application's config reload endpoint
            # or directly updating the configuration in memory
            
        except Exception as e:
            raise RuntimeError(f"Failed to apply configuration: {str(e)}") from e
    
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
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.mock_server_url}/mock-set-context",
                    json=context_data,
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
            # Clear local test context
            TestContextManager.clear()
            
            # Clear mock server context
            await self._clear_mock_server_context()
            
            # Remove temporary config file
            if self._temp_config_file and os.path.exists(self._temp_config_file):
                os.unlink(self._temp_config_file)
                self._temp_config_file = None
            
            # TODO: Restore original configuration if needed
            
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
    
    def get_provider_config(self, provider_name: str):
        """Get provider configuration by name."""
        return self.scenario.get_provider_config(provider_name)
    
    def get_expected_behavior(self):
        """Get expected test behavior."""
        return self.scenario.expected_behavior


class ConfigurableTestEnvironment(TestEnvironment):
    """
    Test environment with more configuration options.
    
    Allows for more complex test setups with custom settings.
    """
    
    def __init__(
        self,
        scenario: TestScenario,
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
    
    async def update_scenario(self, new_scenario: TestScenario):
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
    from .test_scenario import TestScenario, ProviderConfig, ProviderBehavior, ExpectedBehavior
    
    scenario = TestScenario(
        name="simple_success",
        providers=[ProviderConfig("success_provider", ProviderBehavior.SUCCESS)],
        expected_behavior=ExpectedBehavior.SUCCESS
    )
    
    async with TestEnvironment(scenario, model_name) as env:
        return await test_func(env)


async def with_failover_test(test_func, model_name: Optional[str] = None):
    """Run test with failover scenario."""
    from .test_scenario import TestScenario, ProviderConfig, ProviderBehavior, ExpectedBehavior
    
    scenario = TestScenario(
        name="failover_test",
        providers=[
            ProviderConfig("primary_fail", ProviderBehavior.ERROR, priority=1),
            ProviderConfig("secondary_success", ProviderBehavior.SUCCESS, priority=2)
        ],
        expected_behavior=ExpectedBehavior.FAILOVER
    )
    
    async with TestEnvironment(scenario, model_name) as env:
        return await test_func(env)