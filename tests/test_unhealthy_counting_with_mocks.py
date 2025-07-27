"""
Test the unhealthy counting mechanism using real mock providers
"""

import pytest
import httpx
from httpx import AsyncClient
from conftest import claude_headers, async_client
import sys
from pathlib import Path

# Add src to path for imports
current_dir = Path(__file__).parent
src_dir = current_dir.parent / "src"
sys.path.insert(0, str(src_dir))

from core.provider_manager import ProviderManager

@pytest.fixture
def provider_manager():
    """Get provider manager from global test instance."""
    import conftest
    return conftest._test_provider_manager


class TestUnhealthyCountingWithRealMocks:
    """Test the new unhealthy counting mechanism using real mock providers."""

    @pytest.mark.asyncio
    async def test_single_error_does_not_mark_unhealthy(self, async_client: AsyncClient, claude_headers, provider_manager):
        """Test that a single error does not immediately mark provider as unhealthy."""
        # Reset test counters first
        async with httpx.AsyncClient() as client:
                                    await client.post("http://localhost:8998/test-providers/reset-test-counters")
        
        # Reset all providers to healthy state
        for provider in provider_manager.providers:
            provider.mark_success()
            
        # Reset error counts
        with provider_manager._lock:
            provider_manager._error_counts.clear()
            provider_manager._last_error_time.clear()
            provider_manager._last_success_time.clear()
        
        # Use model name that routes to single error test provider
        request_data = {
            "model": "unhealthy-single-check-model",
            "max_tokens": 100,
            "messages": [{"role": "user", "content": "Test single error"}]
        }
        
        # Make request - should succeed via fallback after single error
        response = await async_client.post(
            "/v1/messages",
            json=request_data,
            headers=claude_headers
        )
        
        # Should succeed via fallback
        assert response.status_code == 200
        data = response.json()
        # The request should succeed via failover - exact text doesn't matter
        assert "content" in data
        print(f"✅ Request succeeded via failover mechanism")
        
        # The key test: check if error was recorded for the Test Single Error Provider
        single_error_provider = None
        for provider in provider_manager.providers:
            if provider.name == "Test Single Error Provider":
                single_error_provider = provider
                break
        
        assert single_error_provider is not None, "Test Single Error Provider not found"
        error_status = provider_manager.get_provider_error_status(single_error_provider.name)
        
        print(f"Provider {single_error_provider.name} error count: {error_status['error_count']}/{error_status['threshold']}")
        print(f"Provider failure_count: {single_error_provider.failure_count}")
        print(f"Last error time: {error_status.get('last_error_time')}")
        
        # Verify error was recorded and provider is NOT marked unhealthy yet (single error < threshold)
        assert error_status['error_count'] == 1, f"Expected 1 error, got {error_status['error_count']}"
        assert error_status['threshold'] == 2, f"Expected threshold 2, got {error_status['threshold']}"
        assert single_error_provider.failure_count == 0, f"Provider should not be marked unhealthy yet, failure_count: {single_error_provider.failure_count}"
        
        print(f"✅ Single error recorded but provider {single_error_provider.name} not marked unhealthy before threshold")

    @pytest.mark.asyncio
    async def test_multiple_errors_mark_unhealthy(self, async_client: AsyncClient, claude_headers, provider_manager):
        """Test that multiple errors (reaching threshold) mark provider as unhealthy."""
        # Reset test counters first
        async with httpx.AsyncClient() as client:
                                    await client.post("http://localhost:8998/test-providers/reset-test-counters")
        
        # Reset all providers to healthy state
        for provider in provider_manager.providers:
            provider.mark_success()
            
        # Reset error counts
        with provider_manager._lock:
            provider_manager._error_counts.clear()
            provider_manager._last_error_time.clear()
            provider_manager._last_success_time.clear()
        
        # Use model name that routes to multiple error test provider
        request_data = {
            "model": "unhealthy-multiple-check-model",
            "max_tokens": 100,
            "messages": [{"role": "user", "content": "Test multiple errors"}]
        }
        
        # Make first request - should trigger first error
        response1 = await async_client.post(
            "/v1/messages",
            json=request_data,
            headers=claude_headers
        )
        assert response1.status_code == 200  # Should succeed via fallback
        
        # Debug: Check provider state after first request
        multiple_error_provider = None
        for provider in provider_manager.providers:
            if provider.name == "Test Multiple Error Provider":
                multiple_error_provider = provider
                break
        
        print(f"After first request - Provider failure_count: {multiple_error_provider.failure_count}")
        print(f"After first request - Provider is_healthy: {multiple_error_provider.is_healthy(30)}")
        error_status = provider_manager.get_provider_error_status(multiple_error_provider.name)
        print(f"After first request - Error count: {error_status['error_count']}/{error_status['threshold']}")
        
        # Reset sticky provider to ensure second request tries the multiple error provider first
        provider_manager._last_successful_provider = None
        
        # Make second request - should trigger second error and mark unhealthy
        # Use different content to avoid request deduplication
        request_data2 = {
            "model": "unhealthy-multiple-check-model",
            "max_tokens": 100,
            "messages": [{"role": "user", "content": "Test multiple errors - second request"}]
        }
        response2 = await async_client.post(
            "/v1/messages",
            json=request_data2,
            headers=claude_headers
        )
        assert response2.status_code == 200  # Should succeed via fallback
        
        # Find the multiple error provider
        multiple_error_provider = None
        for provider in provider_manager.providers:
            if provider.name == "Test Multiple Error Provider":
                multiple_error_provider = provider
                break
        
        assert multiple_error_provider is not None
        error_status = provider_manager.get_provider_error_status(multiple_error_provider.name)
        
        print(f"Provider {multiple_error_provider.name} error count: {error_status['error_count']}/{error_status['threshold']}")
        assert error_status['error_count'] == 2
        assert error_status['threshold'] == 2
        
        # Provider should now be marked as failed (unhealthy) after reaching threshold
        assert multiple_error_provider.failure_count > 0
        print(f"✅ Multiple errors marked provider unhealthy: {multiple_error_provider.name}")

    @pytest.mark.asyncio
    async def test_success_resets_error_count(self, async_client: AsyncClient, claude_headers, provider_manager):
        """Test that successful requests reset the error count."""
        # Reset test counters first
        async with httpx.AsyncClient() as client:
                                    await client.post("http://localhost:8998/test-providers/reset-test-counters")
        
        # Reset all providers to healthy state
        for provider in provider_manager.providers:
            provider.mark_success()
            
        # Reset error counts
        with provider_manager._lock:
            provider_manager._error_counts.clear()
            provider_manager._last_error_time.clear()
            provider_manager._last_success_time.clear()
        
        # Use model name that routes to error reset test provider (fail, succeed, fail, succeed)
        request_data = {
            "model": "unhealthy-reset-check-model",
            "max_tokens": 100,
            "messages": [{"role": "user", "content": "Test error reset"}]
        }
        
        # First request - should fail (call #1 = odd = fail)
        response1 = await async_client.post(
            "/v1/messages",
            json=request_data,
            headers=claude_headers
        )
        assert response1.status_code == 200  # Should succeed via fallback
        
        # Find the error reset provider and check error count
        reset_provider = None
        for provider in provider_manager.providers:
            if provider.name == "Test Error Reset Provider":
                reset_provider = provider
                break
        
        assert reset_provider is not None
        error_status = provider_manager.get_provider_error_status(reset_provider.name)
        print(f"After failure - Error count: {error_status['error_count']}/{error_status['threshold']}")
        assert error_status['error_count'] == 1
        
        # Reset sticky provider to ensure second request tries the reset provider first
        provider_manager._last_successful_provider = None
        
        # Second request - should succeed (call #2 = even = succeed)
        response2 = await async_client.post(
            "/v1/messages",
            json=request_data,
            headers=claude_headers
        )
        assert response2.status_code == 200
        data = response2.json()
        # This should come from the reset provider directly (not fallback)
        assert "Success that should reset error count" in data.get("content", [{}])[0].get("text", "")
        
        # Check that error count is reset after success
        error_status = provider_manager.get_provider_error_status(reset_provider.name)
        print(f"After success - Error count: {error_status['error_count']}/{error_status['threshold']}")
        
        # Error count should be reset to 0 after successful request
        assert error_status['error_count'] == 0
        print(f"✅ Success request reset error count for provider: {reset_provider.name}")

    def test_independent_error_counting_per_provider(self, provider_manager):
        """Test that error counts are independent for each provider."""
        # Ensure we have at least 2 providers
        assert len(provider_manager.providers) >= 2
        
        # Reset all providers to healthy state
        for provider in provider_manager.providers:
            provider.mark_success()
            
        # Reset error counts
        with provider_manager._lock:
            provider_manager._error_counts.clear()
            provider_manager._last_error_time.clear()
            provider_manager._last_success_time.clear()
        
        # Manually test error counting independence
        provider_a = provider_manager.providers[0]
        provider_b = provider_manager.providers[1]
        
        # Record one error for provider A
        should_mark_unhealthy_a1 = provider_manager.record_health_check_result(
            provider_a.name, True, "connection_error", "test_request_1"
        )
        
        # Record two errors for provider B
        should_mark_unhealthy_b1 = provider_manager.record_health_check_result(
            provider_b.name, True, "connection_error", "test_request_2"
        )
        should_mark_unhealthy_b2 = provider_manager.record_health_check_result(
            provider_b.name, True, "connection_error", "test_request_3"
        )
        
        # Check results
        status_a = provider_manager.get_provider_error_status(provider_a.name)
        status_b = provider_manager.get_provider_error_status(provider_b.name)
        
        print(f"Provider A error count: {status_a['error_count']}/{status_a['threshold']}")
        print(f"Provider B error count: {status_b['error_count']}/{status_b['threshold']}")
        
        # Provider A should have 1 error, not marked unhealthy
        assert status_a['error_count'] == 1
        assert not should_mark_unhealthy_a1
        
        # Provider B should have 2 errors, marked unhealthy
        assert status_b['error_count'] == 2
        assert not should_mark_unhealthy_b1  # First error shouldn't mark unhealthy
        assert should_mark_unhealthy_b2      # Second error should mark unhealthy
        
        print(f"✅ Independent error counting verified: A={status_a['error_count']}, B={status_b['error_count']}")

    def test_timeout_reset_error_counts(self, provider_manager):
        """Test that error counts are reset after timeout period."""
        import time
        
        # Reset all providers to healthy state
        for provider in provider_manager.providers:
            provider.mark_success()
            
        # Reset error counts
        with provider_manager._lock:
            provider_manager._error_counts.clear()
            provider_manager._last_error_time.clear()
            provider_manager._last_success_time.clear()
        
        provider_name = provider_manager.providers[0].name
        
        # Record an error
        provider_manager.record_health_check_result(
            provider_name, True, "connection_error", "test_timeout_reset"
        )
        
        # Verify error was recorded
        status_before = provider_manager.get_provider_error_status(provider_name)
        assert status_before['error_count'] == 1
        print(f"Before timeout reset - Error count: {status_before['error_count']}")
        
        # Manually set error time to past (simulate timeout)
        with provider_manager._lock:
            if provider_name in provider_manager._last_error_time:
                provider_manager._last_error_time[provider_name] = time.time() - provider_manager.unhealthy_reset_timeout - 1
        
        # Trigger timeout reset
        provider_manager.reset_error_counts_on_timeout()
        
        # Verify error count was reset
        status_after = provider_manager.get_provider_error_status(provider_name)
        assert status_after['error_count'] == 0
        print(f"After timeout reset - Error count: {status_after['error_count']}")
        print(f"✅ Timeout reset successfully cleared error count for provider: {provider_name}")