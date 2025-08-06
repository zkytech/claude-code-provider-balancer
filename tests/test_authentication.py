"""
Tests for API authentication functionality.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import sys
import os

# Add src to Python path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from main import create_app
from auth import AuthManager, AuthConfig


@pytest.fixture
def auth_config():
    """Create a test authentication configuration."""
    return {
        'auth': {
            'enabled': True,
            'auth_tokens': ['test-token-1', 'test-token-2'],
            'exempt_paths': ['/health', '/docs', '/redoc', '/openapi.json']
        },
        'settings': {
            'host': '127.0.0.1',
            'port': 9090,
            'log_level': 'INFO'
        },
        'providers': []
    }


@pytest.fixture
def no_auth_config():
    """Create a configuration with authentication disabled."""
    return {
        'auth': {
            'enabled': False,
            'auth_tokens': [],
            'exempt_paths': ['/health', '/docs', '/redoc', '/openapi.json']
        },
        'settings': {
            'host': '127.0.0.1', 
            'port': 9090,
            'log_level': 'INFO'
        },
        'providers': []
    }


class TestAuthentication:
    """Test cases for API authentication."""
    
    def test_auth_manager_token_validation(self):
        """Test AuthManager API key validation."""
        config = AuthConfig(
            enabled=True,
            api_key='test-key-123',
            exempt_paths=['/health']
        )
        auth_manager = AuthManager(config)
        
        # Valid API key
        assert auth_manager.validate_token('test-key-123')
        
        # Invalid API keys
        assert not auth_manager.validate_token('invalid-key')
        assert not auth_manager.validate_token('')
        assert not auth_manager.validate_token(None)
    
    def test_auth_manager_header_extraction(self):
        """Test API key extraction from headers using upstream logic."""
        config = AuthConfig()
        auth_manager = AuthManager(config)
        
        # Test x-api-key header (Anthropic style) - priority
        assert auth_manager.extract_token_from_headers('anthropic-key', 'Bearer openai-key') == 'anthropic-key'
        
        # Test Authorization Bearer header (OpenAI style)
        assert auth_manager.extract_token_from_headers(None, 'Bearer openai-key') == 'openai-key'
        
        # Test Authorization direct header
        assert auth_manager.extract_token_from_headers(None, 'direct-key') == 'direct-key'
        
        # Test both empty
        assert auth_manager.extract_token_from_headers(None, None) is None
        assert auth_manager.extract_token_from_headers('', '') is None
    
    def test_auth_manager_path_exemptions(self):
        """Test path exemption logic."""
        config = AuthConfig(
            enabled=True,
            exempt_paths=['/health', '/docs']
        )
        auth_manager = AuthManager(config)
        
        assert auth_manager.is_path_exempt('/health')
        assert auth_manager.is_path_exempt('/docs')
        assert not auth_manager.is_path_exempt('/v1/messages')
        assert not auth_manager.is_path_exempt('/other')
    
    @patch('main.yaml.safe_load')
    @patch('builtins.open')
    def test_authenticated_request_success(self, mock_open, mock_yaml):
        """Test successful authenticated request."""
        mock_yaml.return_value = {
            'settings': {
                'host': '127.0.0.1',
                'port': 9090,
                'log_level': 'INFO',
                'auth': {
                    'enabled': True,
                    'api_key': 'valid-key-123',
                    'exempt_paths': ['/health']
                }
            },
            'providers': []
        }
        
        with patch('main.ProviderManager') as mock_pm:
            # Configure mock properly
            mock_instance = MagicMock()
            mock_instance.get_status.return_value = {"providers": [], "enabled_count": 0}
            mock_pm.return_value = mock_instance
            
            app = create_app('test-config.yaml', 'test')
            client = TestClient(app)
            
            # Test exempt path (should work without auth, may return 404 but not 401)
            response = client.get('/health')
            assert response.status_code != 401  # Should pass authentication
            
            # Test protected path with valid API key using x-api-key (may return 404 but not 401)
            response = client.get(
                '/providers',
                headers={'x-api-key': 'valid-key-123'}
            )
            assert response.status_code != 401  # Should pass authentication
            
            # Test protected path with valid API key using Authorization Bearer (may return 404 but not 401)
            response = client.get(
                '/providers',
                headers={'Authorization': 'Bearer valid-key-123'}
            )
            assert response.status_code != 401  # Should pass authentication
    
    @patch('main.yaml.safe_load')
    @patch('builtins.open')  
    def test_authenticated_request_failure(self, mock_open, mock_yaml):
        """Test failed authentication."""
        mock_yaml.return_value = {
            'settings': {
                'host': '127.0.0.1',
                'port': 9090,
                'log_level': 'INFO',
                'auth': {
                    'enabled': True,
                    'api_key': 'valid-key-123',
                    'exempt_paths': ['/health']
                }
            },
            'providers': []
        }
        
        with patch('main.ProviderManager') as mock_pm:
            # Configure mock properly  
            mock_instance = MagicMock()
            mock_instance.get_status.return_value = {"providers": [], "enabled_count": 0}
            mock_pm.return_value = mock_instance
            
            app = create_app('test-config.yaml', 'test')
            client = TestClient(app)
            
            # Test protected path without API key
            response = client.get('/providers')
            assert response.status_code == 401
            assert 'authentication_error' in response.json()['error']['type']
            
            # Test protected path with invalid API key using x-api-key
            response = client.get(
                '/providers',
                headers={'x-api-key': 'invalid-key'}
            )
            assert response.status_code == 401
            assert 'authentication_error' in response.json()['error']['type']
            
            # Test protected path with invalid API key using Authorization Bearer
            response = client.get(
                '/providers',
                headers={'Authorization': 'Bearer invalid-key'}
            )
            assert response.status_code == 401
            assert 'authentication_error' in response.json()['error']['type']
    
    @patch('main.yaml.safe_load')
    @patch('builtins.open')
    def test_authentication_disabled(self, mock_open, mock_yaml):
        """Test behavior when authentication is disabled."""
        mock_yaml.return_value = {
            'settings': {
                'host': '127.0.0.1',
                'port': 9090,
                'log_level': 'INFO',
                'auth': {
                    'enabled': False,
                    'api_key': '',
                    'exempt_paths': []
                }
            },
            'providers': []
        }
        
        with patch('main.ProviderManager') as mock_pm:
            # Configure mock properly
            mock_instance = MagicMock()
            mock_instance.get_status.return_value = {"providers": [], "enabled_count": 0}
            mock_pm.return_value = mock_instance
            
            app = create_app('test-config.yaml', 'test')
            client = TestClient(app)
            
            # All paths should work without authentication when disabled
            # (may return 404 but should not return 401)
            response = client.get('/health')
            assert response.status_code != 401
            
            response = client.get('/providers')  
            assert response.status_code != 401


if __name__ == "__main__":
    pytest.main([__file__])