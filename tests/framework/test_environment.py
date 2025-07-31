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
from .test_server_manager import BalancerTestServer


class Environment:
    """
    Test environment context manager.
    
    Automatically generates and applies test configuration based on scenarios,
    then cleans up when done.
    """
    
    def __init__(self, scenario: Scenario):
        self.scenario = scenario
        self.config_factory = TestConfigFactory()
        
        # Internal state
        self._generated_config: Optional[Dict[str, Any]] = None
        self._temp_config_file: Optional[str] = None
        self._original_config_backup: Optional[str] = None
        self._balancer_server: Optional[BalancerTestServer] = None
        
    async def __aenter__(self) -> 'Environment':
        """Enter test environment - generate and apply configuration."""
        try:
            # 1. Generate configuration from scenario
            self._generated_config = self.config_factory.create_config(self.scenario)
            
            # 2. Set test context locally
            TestContextManager.set_scenario(self.scenario)
            
            # 3. Set test context on mock server (cross-process communication)
            await self._set_mock_server_context()
            
            # 4. Start balancer test server using port from config
            port = self._generated_config.get('settings', {}).get('port', 9091)
            await self._start_balancer_server(port)
            
            return self
            
        except Exception as e:
            # Cleanup on error
            await self._cleanup()
            raise RuntimeError(f"Failed to set up test environment: {str(e)}") from e
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit test environment - restore original configuration."""
        await self._cleanup()
    
    async def _start_balancer_server(self, port: int):
        """Start the balancer test server with generated configuration."""
        try:
            self._balancer_server = BalancerTestServer(
                test_port=port,
                mock_server_port=8998  # Fixed mock server port
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
                    "http://localhost:8998/mock-set-context",  # Fixed mock server URL
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
                    "http://localhost:8998/mock-clear-context",  # Fixed mock server URL
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
    def model_name(self) -> str:
        """Get the model name for this test environment."""
        if self.scenario.model_name:
            return self.scenario.model_name
        elif self._generated_config and 'model_routes' in self._generated_config:
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