"""
Balancer test server for running isolated balancer instances during testing.

This module provides functionality to start and manage dedicated balancer instances
for testing, ensuring complete isolation from production environments.
"""

import asyncio
import os
import tempfile
import yaml
import uvicorn
import httpx
import time
import threading
from pathlib import Path
from typing import Dict, Any, Optional
from contextlib import asynccontextmanager
import sys

from .test_scenario import Scenario


class BalancerTestServer:
    """
    Manages a dedicated balancer instance for testing.
    
    This server runs on a separate port from production and uses
    test-specific configuration that points to mock providers.
    """
    
    def __init__(
        self,
        test_port: int = 9091,
        mock_server_port: int = 8998,
        test_host: str = "127.0.0.1"
    ):
        self.test_port = test_port
        self.mock_server_port = mock_server_port
        self.test_host = test_host
        
        # Internal state
        self._config_file: Optional[str] = None
        self._server_thread: Optional[threading.Thread] = None
        self._server: Optional[uvicorn.Server] = None
        self._is_running = False
        self._stop_event = threading.Event()
        
        # Get project paths
        self.test_dir = Path(__file__).parent.parent
        self.project_root = self.test_dir.parent
        self.src_dir = self.project_root / "src"
        
    async def start_with_config(self, config: Dict[str, Any]) -> None:
        """Start the balancer server with the given configuration."""
        try:
            # Create temporary config file
            self._config_file = await self._create_temp_config(config)
            
            # Start the server process
            await self._start_server_process()
            
            # Wait for server to be ready
            await self._wait_for_server_ready()
            
            self._is_running = True
            
        except Exception as e:
            await self._cleanup()
            raise RuntimeError(f"Failed to start balancer test server: {e}") from e
    
    async def stop(self) -> None:
        """Stop the balancer server and cleanup resources."""
        await self._cleanup()
    
    async def reload_config(self, config: Dict[str, Any]) -> None:
        """Reload the server configuration."""
        if not self._is_running:
            raise RuntimeError("Server is not running")
        
        # Update config file
        with open(self._config_file, 'w') as f:
            yaml.dump(config, f, default_flow_style=False)
        
        # Trigger config reload via API
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"http://{self.test_host}:{self.test_port}/providers/reload",
                    timeout=5.0
                )
                if response.status_code != 200:
                    raise RuntimeError(f"Config reload failed: {response.status_code}")
        except httpx.RequestError as e:
            raise RuntimeError(f"Failed to reload config: {e}") from e
    
    async def _create_temp_config(self, config: Dict[str, Any]) -> str:
        """Create a temporary configuration file."""
        # Ensure test-specific settings
        if 'settings' not in config:
            config['settings'] = {}
        
        config['settings'].update({
            'host': self.test_host,
            'port': self.test_port,
            'log_level': 'DEBUG',  # More verbose for testing
        })
        
        # Create temporary config file
        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.yaml',
            delete=False,
            prefix='balancer_test_config_'
        ) as f:
            yaml.dump(config, f, default_flow_style=False)
            config_path = f.name
            
        # Debug: print the config file content (optional)
        # print(f"Created config file: {config_path}")
        # with open(config_path, 'r') as f:
        #     content = f.read()
        #     print("Config file content:")
        #     print(content)
            
        return config_path
    
    async def _start_server_process(self) -> None:
        """Start the balancer server in a separate thread."""
        if not self._config_file:
            raise RuntimeError("Config file not created")
        
        # Add src directory to Python path
        if str(self.src_dir) not in sys.path:
            sys.path.insert(0, str(self.src_dir))
        
        # Import the test app factory
        try:
            # Import from our test framework
            from .test_app import create_test_app
        except ImportError:
            raise RuntimeError("Test app factory not found. Need test_app module in framework.")
        
        # Create the app with test configuration
        try:
            app = create_test_app(self._config_file)
        except Exception as e:
            print(f"Failed to create test app: {e}")
            import traceback
            traceback.print_exc()
            raise
        
        # Create uvicorn server configuration (simplify to avoid levelprefix issues)
        config = uvicorn.Config(
            app=app,
            host=self.test_host,
            port=self.test_port,
            log_level="warning",  # Make uvicorn quieter
            access_log=False      # Disable uvicorn access logs (we have our own)
        )
        
        self._server = uvicorn.Server(config)
        
        # Start server in a separate thread
        def run_server():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self._server.serve())
            except Exception as e:
                print(f"Server thread error: {e}")
                import traceback
                traceback.print_exc()
            finally:
                loop.close()
        
        self._server_thread = threading.Thread(target=run_server, daemon=True)
        self._server_thread.start()
        
        # Give the server more time to start
        await asyncio.sleep(2.0)
    
    async def _wait_for_server_ready(self, timeout: float = 10.0) -> None:
        """Wait for the server to be ready to accept requests."""
        start_time = time.time()
        health_url = f"http://{self.test_host}:{self.test_port}/"
        
        while time.time() - start_time < timeout:
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(health_url, timeout=1.0)
                    if response.status_code == 200:
                        return  # Server is ready
            except (httpx.RequestError, httpx.TimeoutException):
                pass  # Server not ready yet
            
            await asyncio.sleep(0.5)
            
        raise RuntimeError(f"Server did not become ready within {timeout} seconds")
    
    async def _cleanup(self) -> None:
        """Clean up server thread and temporary files."""
        # Stop server
        if self._server:
            try:
                # Signal the server to stop
                self._server.should_exit = True
                
                # Wait for server thread to finish
                if self._server_thread and self._server_thread.is_alive():
                    self._server_thread.join(timeout=5.0)
                    
            except Exception as e:
                print(f"Warning: Error stopping server: {e}")
            finally:
                self._server = None
                self._server_thread = None
        
        # Remove temporary config file
        if self._config_file and os.path.exists(self._config_file):
            try:
                os.unlink(self._config_file)
            except Exception:
                pass  # Ignore cleanup errors
            finally:
                self._config_file = None
        
        self._is_running = False
    
    @property
    def base_url(self) -> str:
        """Get the base URL for the test server."""
        return f"http://{self.test_host}:{self.test_port}"
    
    @property
    def is_running(self) -> bool:
        """Check if the server is currently running."""
        return (self._is_running and 
                self._server_thread and 
                self._server_thread.is_alive() and
                self._server and 
                not self._server.should_exit)


@asynccontextmanager
async def balancer_test_server(config: Dict[str, Any], **kwargs):
    """
    Context manager for running a balancer test server.
    
    Usage:
        async with balancer_test_server(config) as server:
            # Make requests to server.base_url
            ...
    """
    server = BalancerTestServer(**kwargs)
    try:
        await server.start_with_config(config)
        yield server
    finally:
        await server.stop()


class BalancerTestServerFactory:
    """Factory for creating balancer test servers with common configurations."""
    
    @staticmethod
    def create_server_for_scenario(
        scenario: Scenario,
        mock_server_port: int = 8998,
        **server_kwargs
    ) -> BalancerTestServer:
        """Create a test server configured for a specific test scenario."""
        return BalancerTestServer(
            mock_server_port=mock_server_port,
            **server_kwargs
        )
    
    @staticmethod
    async def start_server_with_scenario(
        scenario: Scenario,
        config: Dict[str, Any],
        **server_kwargs
    ) -> BalancerTestServer:
        """Start a test server with configuration for a specific scenario."""
        server = BalancerTestServerFactory.create_server_for_scenario(
            scenario, **server_kwargs
        )
        await server.start_with_config(config)
        return server