"""
Validation tests for the new simplified testing framework.

This file demonstrates and validates the new testing framework components.
"""

import pytest
import asyncio
from framework import (
    Scenario, ProviderConfig, ProviderBehavior, ExpectedBehavior,
    TestConfigFactory, TestContextManager, Environment
)


class TestFrameworkValidation:
    """Test the testing framework itself."""

    def test_provider_config_creation(self):
        """Test ProviderConfig creation and validation."""
        # Test with enum
        config1 = ProviderConfig("test_provider", ProviderBehavior.SUCCESS)
        assert config1.name == "test_provider"
        assert config1.behavior == ProviderBehavior.SUCCESS
        assert config1.priority == 1
        
        # Test with string (should convert to enum)
        config2 = ProviderConfig("test_provider2", "error")
        assert config2.behavior == ProviderBehavior.ERROR
        
        # Test with custom parameters
        config3 = ProviderConfig(
            "custom_provider",
            ProviderBehavior.TIMEOUT,
            delay_ms=5000,
            priority=2,
            response_data={"content": "custom response"}
        )
        assert config3.delay_ms == 5000
        assert config3.priority == 2
        assert config3.response_data == {"content": "custom response"}

    def test_test_scenario_creation(self):
        """Test Scenario creation and methods."""
        providers = [
            ProviderConfig("primary", ProviderBehavior.ERROR, priority=1),
            ProviderConfig("secondary", ProviderBehavior.SUCCESS, priority=2)
        ]
        
        scenario = Scenario(
            name="test_scenario",
            providers=providers,
            expected_behavior=ExpectedBehavior.FAILOVER,
            description="Test failover scenario"
        )
        
        assert scenario.name == "test_scenario"
        assert len(scenario.providers) == 2
        assert scenario.expected_behavior == ExpectedBehavior.FAILOVER
        
        # Test provider lookup
        primary = scenario.get_provider_config("primary")
        assert primary is not None
        assert primary.behavior == ProviderBehavior.ERROR
        
        # Test primary provider
        primary_provider = scenario.get_primary_provider()
        assert primary_provider.name == "primary"
        assert primary_provider.priority == 1
        
        # Test sorted providers
        sorted_providers = scenario.get_providers_by_priority()
        assert sorted_providers[0].name == "primary"
        assert sorted_providers[1].name == "secondary"

    def test_config_factory_basic(self):
        """Test basic configuration generation."""
        factory = TestConfigFactory()
        
        # Create scenario instead of using removed convenience method
        from framework import Scenario, ProviderConfig, ProviderBehavior, ExpectedBehavior
        scenario = Scenario(
            name="simple_success",
            providers=[ProviderConfig("success_provider", ProviderBehavior.SUCCESS)],
            expected_behavior=ExpectedBehavior.SUCCESS
        )
        config = factory.create_config(scenario, "test-model")
        
        assert "providers" in config
        assert "model_routes" in config
        assert "settings" in config
        
        # Check provider configuration
        providers = config["providers"]
        assert len(providers) == 1
        assert providers[0]["name"] == "success_provider"
        assert providers[0]["type"] == "anthropic"
        assert "localhost:8998" in providers[0]["base_url"]
        
        # Check model routes
        model_routes = config["model_routes"]
        assert "test-model" in model_routes
        assert len(model_routes["test-model"]) == 1
        assert model_routes["test-model"][0]["provider"] == "success_provider"

    def test_config_factory_complex(self):
        """Test complex scenario configuration generation."""
        factory = TestConfigFactory()
        
        scenario = Scenario(
            name="complex_test",
            providers=[
                ProviderConfig("primary_fail", ProviderBehavior.ERROR, priority=1),
                ProviderConfig("secondary_success", ProviderBehavior.SUCCESS, priority=2),
                ProviderConfig("tertiary_timeout", ProviderBehavior.TIMEOUT, priority=3)
            ],
            expected_behavior=ExpectedBehavior.FAILOVER,
            settings_override={
                "log_level": "ERROR",
                "failure_cooldown": 60
            }
        )
        
        config = factory.create_config(scenario, "complex-model")
        
        # Check providers
        providers = config["providers"]
        assert len(providers) == 3
        provider_names = [p["name"] for p in providers]
        assert "primary_fail" in provider_names
        assert "secondary_success" in provider_names
        assert "tertiary_timeout" in provider_names
        
        # Check model routes with priorities
        routes = config["model_routes"]["complex-model"]
        assert len(routes) == 3
        assert routes[0]["priority"] == 1
        assert routes[1]["priority"] == 2
        assert routes[2]["priority"] == 3
        
        # Check settings override
        settings = config["settings"]
        assert settings["log_level"] == "ERROR"
        assert settings["failure_cooldown"] == 60

    def test_test_context_manager(self):
        """Test TestContextManager functionality."""
        # Initially no context
        assert TestContextManager.get_current_context() is None
        assert not TestContextManager.is_context_set()
        
        # Set a scenario
        scenario = Scenario(
            name="context_test",
            providers=[ProviderConfig("test_provider", ProviderBehavior.SUCCESS)]
        )
        
        TestContextManager.set_scenario(scenario)
        
        # Check context is set
        assert TestContextManager.is_context_set()
        current = TestContextManager.get_current_context()
        assert current is not None
        assert current.name == "context_test"
        
        # Clear context
        TestContextManager.clear()
        assert TestContextManager.get_current_context() is None
        assert not TestContextManager.is_context_set()

    @pytest.mark.asyncio
    async def test_test_environment_basic(self):
        """Test basic Environment usage."""
        scenario = Scenario(
            name="env_test",
            providers=[ProviderConfig("env_provider", ProviderBehavior.SUCCESS)],
            model_name="env-test-model"  # Set model name in scenario
        )
        
        # Test context manager
        async with Environment(scenario) as env:
            # Should have set context
            assert TestContextManager.is_context_set()
            current = TestContextManager.get_current_context()
            assert current.name == "env_test"
            
            # Should have effective model name
            assert env.model_name == "env-test-model"
            
            # Should have generated config
            config = env.config
            assert "providers" in config
            assert "model_routes" in config
            
            # Should be able to get provider config
            provider_config = env.get_provider_config("env_provider")
            assert provider_config is not None
            assert provider_config.behavior == ProviderBehavior.SUCCESS
        
        # After exiting, context should be cleared
        assert not TestContextManager.is_context_set()

    @pytest.mark.asyncio
    async def test_test_environment_auto_model_name(self):
        """Test Environment with automatic model name generation."""
        scenario = Scenario(
            name="auto_model_test",
            providers=[ProviderConfig("auto_provider", ProviderBehavior.SUCCESS)]
        )
        
        async with Environment(scenario) as env:
            # Should have generated a model name
            model_name = env.model_name
            assert model_name.startswith("test-")
            assert len(model_name) > 5  # Should have generated suffix
            
            # Config should contain this model name
            config = env.config
            assert model_name in config["model_routes"]

    def test_convenience_configs(self):
        """Test convenience configuration methods."""
        factory = TestConfigFactory()
        
        # Test failover scenario
        from framework import Scenario, ProviderConfig, ProviderBehavior, ExpectedBehavior
        failover_scenario = Scenario(
            name="failover_test", 
            providers=[
                ProviderConfig("primary_fail", ProviderBehavior.ERROR, priority=1),
                ProviderConfig("secondary_success", ProviderBehavior.SUCCESS, priority=2)
            ],
            expected_behavior=ExpectedBehavior.FAILOVER
        )
        failover_config = factory.create_config(failover_scenario, "failover-model")
        providers = failover_config["providers"]
        assert len(providers) == 2
        
        routes = failover_config["model_routes"]["failover-model"]
        assert routes[0]["priority"] == 1
        assert routes[1]["priority"] == 2
        
        # Test duplicate scenario
        duplicate_scenario = Scenario(
            name="duplicate_test",
            providers=[
                ProviderConfig(
                    "duplicate_provider", 
                    ProviderBehavior.DUPLICATE_CACHE,
                    response_data={"content": "cached_response"}
                )
            ],
            expected_behavior=ExpectedBehavior.SUCCESS
        )
        duplicate_config = factory.create_config(duplicate_scenario, "duplicate-model")
        providers = duplicate_config["providers"]
        assert len(providers) == 1
        assert providers[0]["name"] == "duplicate_provider"
        
        # Test all fail scenario
        all_fail_scenario = Scenario(
            name="all_fail",
            providers=[
                ProviderConfig("fail1", ProviderBehavior.ERROR, priority=1),
                ProviderConfig("fail2", ProviderBehavior.ERROR, priority=2)
            ],
            expected_behavior=ExpectedBehavior.ERROR
        )
        all_fail_config = factory.create_config(all_fail_scenario, "fail-model")
        providers = all_fail_config["providers"]
        assert len(providers) == 2
        # Both should be configured for errors
        assert all(["/mock-provider/" in p["base_url"] for p in providers])

    def test_enum_string_conversion(self):
        """Test enum to string conversion works properly."""
        # Test ProviderBehavior
        assert ProviderBehavior.SUCCESS.value == "success"
        assert ProviderBehavior.ERROR.value == "error"
        assert ProviderBehavior.DUPLICATE_CACHE.value == "duplicate_cache"
        
        # Test ExpectedBehavior
        assert ExpectedBehavior.SUCCESS.value == "success"
        assert ExpectedBehavior.FAILOVER.value == "failover"
        assert ExpectedBehavior.ALL_FAIL.value == "all_fail"
        
        # Test string to enum conversion in ProviderConfig
        config = ProviderConfig("test", "success")
        assert config.behavior == ProviderBehavior.SUCCESS
        
        # Test string to enum conversion in Scenario
        scenario = Scenario(
            name="test",
            providers=[config],
            expected_behavior="failover"
        )
        assert scenario.expected_behavior == ExpectedBehavior.FAILOVER