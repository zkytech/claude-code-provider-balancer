"""
OAuth authentication module.

This module handles OAuth 2.0 authentication flow for Claude Code Official provider.
It provides functionality for:
- OAuth URL generation
- Authorization code exchange
- Token management and refresh
- Persistent token storage
"""

from .oauth_manager import (
    OAuthManager, TokenCredentials, 
    oauth_manager, init_oauth_manager, start_oauth_auto_refresh
)

__all__ = [
    "OAuthManager", "TokenCredentials",
    "oauth_manager", "init_oauth_manager", "start_oauth_auto_refresh"
]