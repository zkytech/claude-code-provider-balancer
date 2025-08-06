"""
Authentication Manager for Claude Code Provider Balancer.
Handles auth_token validation and authentication logic.
"""

from typing import Optional, List, Set
from dataclasses import dataclass
from fastapi import HTTPException, status
from utils import LogRecord, LogEvent, info, warning, error


@dataclass
class AuthConfig:
    """Configuration for API authentication."""
    enabled: bool = False
    api_key: str = ""
    exempt_paths: List[str] = None
    
    def __post_init__(self):
        if self.exempt_paths is None:
            self.exempt_paths = ["/health", "/docs", "/redoc", "/openapi.json"]


class AuthManager:
    """Manages API authentication using auth_token."""
    
    def __init__(self, config: AuthConfig):
        self.config = config
        
    def is_enabled(self) -> bool:
        """Check if authentication is enabled."""
        return self.config.enabled
    
    def is_path_exempt(self, path: str) -> bool:
        """Check if path is exempt from authentication."""
        return path in self.config.exempt_paths
    
    def validate_token(self, token: str, request_id: Optional[str] = None) -> bool:
        """Validate API key."""
        if not token:
            return False
            
        is_valid = token == self.config.api_key
        
        if is_valid:
            info(LogRecord(
                event=LogEvent.AUTH_SUCCESS.value,
                message="Authentication successful",
                request_id=request_id,
                data={"token_prefix": token[:8] + "***" if len(token) > 8 else "***"}
            ))
        else:
            warning(LogRecord(
                event=LogEvent.AUTH_FAILED.value,
                message="Authentication failed - invalid API key",
                request_id=request_id,
                data={"token_prefix": token[:8] + "***" if len(token) > 8 else "***"}
            ))
            
        return is_valid
    
    def extract_token_from_headers(self, api_key: Optional[str], authorization: Optional[str]) -> Optional[str]:
        """Extract token from headers using upstream provider logic."""
        # Priority: x-api-key first (Anthropic style), then Authorization Bearer (OpenAI style)
        if api_key:
            return api_key
            
        if authorization:
            # Support Bearer format
            if authorization.startswith("Bearer "):
                return authorization[7:]
            else:
                # Direct token format
                return authorization
                
        return None
    
    def authenticate_request(self, api_key: Optional[str], authorization: Optional[str], path: str, request_id: Optional[str] = None) -> None:
        """Authenticate request using upstream provider logic and raise HTTPException if invalid."""
        # Skip authentication if disabled
        if not self.is_enabled():
            return
            
        # Skip authentication for exempt paths
        if self.is_path_exempt(path):
            return
            
        # Extract token from headers using upstream logic
        token = self.extract_token_from_headers(api_key, authorization)
        
        if not token:
            error(LogRecord(
                event=LogEvent.AUTH_MISSING_TOKEN.value,
                message="Authentication failed - missing API key",
                request_id=request_id,
                data={"path": path}
            ))
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required. Please provide a valid API key in the x-api-key header or Authorization Bearer header."
            )
        
        if not self.validate_token(token, request_id):
            error(LogRecord(
                event=LogEvent.AUTH_INVALID_TOKEN.value,
                message="Authentication failed - invalid API key",
                request_id=request_id,
                data={"path": path, "token_prefix": token[:8] + "***" if len(token) > 8 else "***"}
            ))
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key."
            )
    
    def set_api_key(self, api_key: str) -> None:
        """Set the API key."""
        self.config.api_key = api_key
        info(LogRecord(
            event="auth_api_key_set",
            message="API key updated",
            data={"token_prefix": api_key[:8] + "***" if len(api_key) > 8 else "***"}
        ))
    
    def has_api_key(self) -> bool:
        """Check if API key is configured."""
        return bool(self.config.api_key)