"""
Test scenario data structures for simplified testing framework.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum


class ProviderBehavior(Enum):
    """Provider behavior types for testing."""
    SUCCESS = "success"
    STREAMING_SUCCESS = "streaming_success"
    ERROR = "error"
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    DUPLICATE_CACHE = "duplicate_cache"
    CONNECTION_ERROR = "connection_error"
    SSL_ERROR = "ssl_error"
    INTERNAL_SERVER_ERROR = "internal_server_error"
    BAD_GATEWAY = "bad_gateway"
    SERVICE_UNAVAILABLE = "service_unavailable"
    INSUFFICIENT_CREDITS = "insufficient_credits"


class ExpectedBehavior(Enum):
    """Expected test outcomes."""
    SUCCESS = "success"
    FAILOVER = "failover"
    ERROR = "error"
    ALL_FAIL = "all_fail"
    TIMEOUT = "timeout"


@dataclass
class ProviderConfig:
    """Configuration for a test provider."""
    name: str
    behavior: ProviderBehavior
    response_data: Optional[Dict[str, Any]] = None
    delay_ms: int = 0
    priority: int = 1
    error_count: int = 0  # For testing unhealthy provider counting
    error_http_code: int = 500  # HTTP status code for error responses
    error_message: str = "Mock provider error"
    provider_type: str = "anthropic"  # Provider type: anthropic or openai
    
    def __post_init__(self):
        """Convert string behavior to enum if needed."""
        if isinstance(self.behavior, str):
            self.behavior = ProviderBehavior(self.behavior)


@dataclass
class TestScenario:
    """Test scenario definition with providers and expected behavior."""
    name: str
    providers: List[ProviderConfig]
    expected_behavior: ExpectedBehavior = ExpectedBehavior.SUCCESS
    model_name: Optional[str] = None
    settings_override: Optional[Dict[str, Any]] = None
    description: Optional[str] = None
    
    def __post_init__(self):
        """Convert string expected_behavior to enum if needed."""
        if isinstance(self.expected_behavior, str):
            self.expected_behavior = ExpectedBehavior(self.expected_behavior)
            
        # Auto-assign priorities if not set
        for i, provider in enumerate(self.providers):
            if provider.priority == 1 and i > 0:  # Default priority, auto-assign
                provider.priority = i + 1
    
    def get_provider_config(self, provider_name: str) -> Optional[ProviderConfig]:
        """Get provider configuration by name."""
        for provider in self.providers:
            if provider.name == provider_name:
                return provider
        return None
    
    def get_primary_provider(self) -> Optional[ProviderConfig]:
        """Get the primary (highest priority) provider."""
        if not self.providers:
            return None
        return min(self.providers, key=lambda p: p.priority)
    
    def get_providers_by_priority(self) -> List[ProviderConfig]:
        """Get providers sorted by priority (ascending)."""
        return sorted(self.providers, key=lambda p: p.priority)