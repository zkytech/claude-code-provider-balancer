"""
Unit tests for the unhealthy counting mechanism in provider_manager.
These tests directly test the core logic without HTTP requests or mock providers.
"""

import pytest
import time
from core.provider_manager import ProviderManager


class TestUnhealthyCountingMechanism:
    """Test the unhealthy counting mechanism that requires multiple errors before marking unhealthy."""

    @pytest.fixture
    def provider_manager(self):
        """Create a provider manager with test configuration."""
        return ProviderManager(config_path="tests/config-test.yaml")

    @pytest.mark.asyncio
    async def test_single_error_does_not_mark_unhealthy_unit(self, provider_manager):
        """Unit test: single error should not immediately mark provider as unhealthy."""
        
        # Reset error counts using the health manager
        from core.provider_manager.health import reset_all_health_states
        reset_all_health_states()
        
        provider_name = "Test Provider"
        
        # Record one error
        should_mark_unhealthy = provider_manager.record_health_check_result(
            provider_name, True, "connection_error", "test_request_1"
        )
        
        # Should not mark unhealthy on first error
        assert not should_mark_unhealthy
        
        # Check error status
        error_status = provider_manager.get_provider_error_status(provider_name)
        assert error_status['error_count'] == 1
        assert error_status['threshold'] == 2  # Default threshold
        
        print(f"✅ Single error did not mark provider unhealthy: {provider_name}")

    @pytest.mark.asyncio
    async def test_multiple_errors_mark_unhealthy_unit(self, provider_manager):
        """Unit test: multiple errors (reaching threshold) should mark provider as unhealthy."""
        
        # Reset error counts using the health manager
        from core.provider_manager.health import reset_all_health_states
        reset_all_health_states()
        
        provider_name = "Test Provider"
        
        # Record first error
        should_mark_unhealthy_1 = provider_manager.record_health_check_result(
            provider_name, True, "connection_error", "test_request_1"
        )
        assert not should_mark_unhealthy_1  # First error should not mark unhealthy
        
        # Record second error (reaching threshold)
        should_mark_unhealthy_2 = provider_manager.record_health_check_result(
            provider_name, True, "connection_error", "test_request_2"
        )
        assert should_mark_unhealthy_2  # Second error should mark unhealthy
        
        # Check error status
        error_status = provider_manager.get_provider_error_status(provider_name)
        assert error_status['error_count'] == 2
        assert error_status['threshold'] == 2
        
        print(f"✅ Multiple errors correctly marked provider unhealthy: {provider_name}")

    @pytest.mark.asyncio
    async def test_success_resets_error_count_unit(self, provider_manager):
        """Unit test: successful requests should reset the error count."""
        
        # Reset error counts using the health manager
        from core.provider_manager.health import reset_all_health_states
        reset_all_health_states()
        
        provider_name = "Test Provider"
        
        # Record one error
        provider_manager.record_health_check_result(
            provider_name, True, "connection_error", "test_request_1"
        )
        
        # Verify error was recorded
        error_status = provider_manager.get_provider_error_status(provider_name)
        assert error_status['error_count'] == 1
        
        # Record success
        provider_manager.record_health_check_result(
            provider_name, False, None, "test_request_2"
        )
        
        # Verify error count was reset
        error_status = provider_manager.get_provider_error_status(provider_name)
        assert error_status['error_count'] == 0
        
        print(f"✅ Success correctly reset error count for provider: {provider_name}")

    @pytest.mark.asyncio
    async def test_independent_error_counting_per_provider_unit(self, provider_manager):
        """Unit test: error counts should be independent for each provider."""
        
        # Reset error counts using the health manager
        from core.provider_manager.health import reset_all_health_states
        reset_all_health_states()
        
        provider_a = "Provider A"
        provider_b = "Provider B"
        
        # Record one error for provider A
        should_mark_unhealthy_a1 = provider_manager.record_health_check_result(
            provider_a, True, "connection_error", "test_request_1"
        )
        
        # Record two errors for provider B
        should_mark_unhealthy_b1 = provider_manager.record_health_check_result(
            provider_b, True, "connection_error", "test_request_2"
        )
        should_mark_unhealthy_b2 = provider_manager.record_health_check_result(
            provider_b, True, "connection_error", "test_request_3"
        )
        
        # Check results
        status_a = provider_manager.get_provider_error_status(provider_a)
        status_b = provider_manager.get_provider_error_status(provider_b)
        
        # Provider A should have 1 error, not marked unhealthy
        assert status_a['error_count'] == 1
        assert not should_mark_unhealthy_a1
        
        # Provider B should have 2 errors, marked unhealthy
        assert status_b['error_count'] == 2
        assert not should_mark_unhealthy_b1  # First error shouldn't mark unhealthy
        assert should_mark_unhealthy_b2      # Second error should mark unhealthy
        
        print(f"✅ Independent error counting verified: A={status_a['error_count']}, B={status_b['error_count']}")

    @pytest.mark.asyncio
    async def test_timeout_reset_error_counts_unit(self, provider_manager):
        """Unit test: error counts should be reset after timeout period."""
        
        # Reset error counts using the health manager
        from core.provider_manager.health import reset_all_health_states
        reset_all_health_states()
        
        provider_name = "Test Provider"
        
        # Record an error
        provider_manager.record_health_check_result(
            provider_name, True, "connection_error", "test_timeout_reset"
        )
        
        # Verify error was recorded
        status_before = provider_manager.get_provider_error_status(provider_name)
        assert status_before['error_count'] == 1
        
        # Manually set error time to past (simulate timeout)
        from core.provider_manager.health import get_health_manager
        health_manager = get_health_manager()
        with health_manager._lock:
            if provider_name in health_manager._last_error_time:
                health_manager._last_error_time[provider_name] = time.time() - provider_manager.unhealthy_reset_timeout - 1
        
        # Trigger timeout reset
        provider_manager.reset_error_counts_on_timeout()
        
        # Verify error count was reset
        status_after = provider_manager.get_provider_error_status(provider_name)
        assert status_after['error_count'] == 0
        
        print(f"✅ Timeout reset successfully cleared error count for provider: {provider_name}")


class TestErrorClassificationLogic:
    """Test the error classification and unhealthy detection logic."""

    @pytest.fixture
    def provider_manager(self):
        """Create a provider manager with test configuration."""
        return ProviderManager(config_path="tests/config-test.yaml")

    @pytest.mark.asyncio
    async def test_http_status_code_classification(self, provider_manager):
        """Test that HTTP status codes are correctly classified for unhealthy detection."""
        import httpx
        
        # Test 502 Bad Gateway
        error_reason, should_mark_unhealthy, can_failover = provider_manager.get_error_handling_decision(
            httpx.HTTPStatusError("502 Bad Gateway", request=None, response=None), 
            http_status_code=502
        )
        
        assert error_reason == "http_status_502"  # Updated to match actual format
        assert should_mark_unhealthy == True  # 502 is in unhealthy_http_codes
        assert can_failover == True  # Non-streaming request
        
        print(f"✅ HTTP 502 correctly classified as unhealthy")

    @pytest.mark.asyncio
    async def test_connection_error_classification(self, provider_manager):
        """Test that connection errors are correctly classified."""
        import httpx
        
        error = httpx.ConnectError("Connection failed")
        error_reason, should_mark_unhealthy, can_failover = provider_manager.get_error_handling_decision(error)
        
        assert error_reason == "network_exception_connecterror"  # Updated to match actual format
        assert should_mark_unhealthy == True  # ConnectError is in network exception types
        assert can_failover == True
        
        print(f"✅ Connection error correctly classified as unhealthy")

    @pytest.mark.asyncio
    async def test_streaming_failover_limitation(self, provider_manager):
        """Test that streaming requests can still failover for connection errors."""
        import httpx
        
        error = httpx.ConnectError("Connection failed")
        error_reason, should_mark_unhealthy, can_failover = provider_manager.get_error_handling_decision(
            error, 
            is_streaming=True
        )
        
        assert error_reason == "network_exception_connecterror"
        assert should_mark_unhealthy == True
        assert can_failover == True  # Connection errors can still failover even in streaming
        
        print(f"✅ Streaming connection error correctly allows failover")