"""
Test context management for tracking current test scenarios.
"""

from typing import Optional
from .test_scenario import TestScenario


class TestContextManager:
    """Manages test execution context and current scenario."""
    
    _current_scenario: Optional[TestScenario] = None
    
    @classmethod
    def set_scenario(cls, scenario: TestScenario) -> None:
        """Set the current test scenario."""
        cls._current_scenario = scenario
    
    @classmethod  
    def get_current_context(cls) -> Optional[TestScenario]:
        """Get the current test scenario."""
        return cls._current_scenario
    
    @classmethod
    def clear(cls) -> None:
        """Clear the current test scenario."""
        cls._current_scenario = None
    
    @classmethod
    def is_context_set(cls) -> bool:
        """Check if a test context is currently set."""
        return cls._current_scenario is not None