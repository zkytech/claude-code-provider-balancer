#!/usr/bin/env python3
"""
Unified test file for passthrough functionality in Claude Code Provider Balancer
Combines unit testing with detailed verification and user-friendly output
"""

import pytest
import sys
import os
import argparse
from typing import List, Tuple, Dict, Any

# Add the src directory to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from src.provider_manager import Provider, ProviderManager, ProviderType, AuthType


class PassthroughTester:
    """Unified passthrough functionality tester with both unit test and verification capabilities"""
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.test_results = []
        
    def log(self, message: str, level: str = "INFO"):
        """Log message with optional verbose output"""
        if self.verbose:
            prefix = {"INFO": "ℹ️", "SUCCESS": "✅", "ERROR": "❌", "WARNING": "⚠️"}.get(level, "")
            print(f"{prefix} {message}")
    
    def run_test_case(self, test_name: str, provider: Provider, test_cases: List[Tuple[str, str, str]], manager: ProviderManager) -> bool:
        """Run a test case with multiple input/expected pairs"""
        self.log(f"Running test: {test_name}", "INFO")
        all_passed = True
        
        for input_model, expected, description in test_cases:
            try:
                result = manager.select_model(provider, input_model)
                passed = result == expected
                
                if passed:
                    self.log(f"  {input_model} -> {result} ({description})", "SUCCESS")
                else:
                    self.log(f"  {input_model} -> {result}, expected {expected} ({description})", "ERROR")
                    all_passed = False
                    
                # Store result for pytest compatibility
                self.test_results.append({
                    'test': test_name,
                    'input': input_model,
                    'expected': expected,
                    'actual': result,
                    'passed': passed,
                    'description': description
                })
                
            except Exception as e:
                self.log(f"  {input_model} -> ERROR: {e} ({description})", "ERROR")
                all_passed = False
                
        return all_passed

    def test_passthrough_both_models(self) -> bool:
        """Test both big_model and small_model set to passthrough"""
        provider = Provider(
            name="test_both_passthrough",
            type=ProviderType.ANTHROPIC,
            base_url="https://api.test.com",
            auth_type=AuthType.API_KEY,
            auth_value="test-key",
            big_model="passthrough",
            small_model="passthrough",
            enabled=True
        )
        
        manager = ProviderManager.__new__(ProviderManager)
        manager.providers = [provider]
        manager.settings = {}
        
        test_cases = [
            ("claude-3-5-sonnet-20241022", "claude-3-5-sonnet-20241022", "Sonnet model passthrough"),
            ("claude-3-opus-20240229", "claude-3-opus-20240229", "Opus model passthrough"),
            ("claude-3-5-haiku-20241022", "claude-3-5-haiku-20241022", "Haiku model passthrough"),
            ("custom-model-name", "custom-model-name", "Custom model passthrough"),
            ("gpt-4o", "gpt-4o", "Non-Claude model passthrough")
        ]
        
        return self.run_test_case("Complete Passthrough Mode", provider, test_cases, manager)

    def test_passthrough_big_model_only(self) -> bool:
        """Test big_model set to passthrough, small_model fixed"""
        provider = Provider(
            name="test_big_passthrough",
            type=ProviderType.ANTHROPIC,
            base_url="https://api.test.com",
            auth_type=AuthType.API_KEY,
            auth_value="test-key",
            big_model="passthrough",
            small_model="claude-3-5-haiku-20241022",
            enabled=True
        )
        
        manager = ProviderManager.__new__(ProviderManager)
        manager.providers = [provider]
        manager.settings = {}
        
        test_cases = [
            ("claude-3-5-sonnet-20241022", "claude-3-5-sonnet-20241022", "Big model passthrough"),
            ("claude-3-opus-20240229", "claude-3-opus-20240229", "Big model passthrough"),
            ("claude-3-5-haiku-20241022", "claude-3-5-haiku-20241022", "Small model uses configured value"),
            ("unknown-model", "unknown-model", "Unknown model treated as big model"),
            ("custom-big-model", "custom-big-model", "Custom big model passthrough")
        ]
        
        return self.run_test_case("Big Model Passthrough Only", provider, test_cases, manager)

    def test_passthrough_small_model_only(self) -> bool:
        """Test small_model set to passthrough, big_model fixed"""
        provider = Provider(
            name="test_small_passthrough",
            type=ProviderType.ANTHROPIC,
            base_url="https://api.test.com",
            auth_type=AuthType.API_KEY,
            auth_value="test-key",
            big_model="claude-3-5-sonnet-20241022",
            small_model="passthrough",
            enabled=True
        )
        
        manager = ProviderManager.__new__(ProviderManager)
        manager.providers = [provider]
        manager.settings = {}
        
        test_cases = [
            ("claude-3-5-sonnet-20241022", "claude-3-5-sonnet-20241022", "Big model uses configured value"),
            ("claude-3-opus-20240229", "claude-3-5-sonnet-20241022", "Big model mapped to configured"),
            ("claude-3-5-haiku-20241022", "claude-3-5-haiku-20241022", "Small model passthrough"),
            ("claude-3-haiku-custom", "claude-3-haiku-custom", "Custom small model passthrough")
        ]
        
        return self.run_test_case("Small Model Passthrough Only", provider, test_cases, manager)

    def test_traditional_mode(self) -> bool:
        """Test traditional mode (no passthrough) for comparison"""
        provider = Provider(
            name="test_traditional",
            type=ProviderType.ANTHROPIC,
            base_url="https://api.test.com",
            auth_type=AuthType.API_KEY,
            auth_value="test-key",
            big_model="claude-3-5-sonnet-20241022",
            small_model="claude-3-5-haiku-20241022",
            enabled=True
        )
        
        manager = ProviderManager.__new__(ProviderManager)
        manager.providers = [provider]
        manager.settings = {}
        
        test_cases = [
            ("claude-3-5-sonnet-20241022", "claude-3-5-sonnet-20241022", "Big model exact match"),
            ("claude-3-opus-20240229", "claude-3-5-sonnet-20241022", "Big model mapping"),
            ("claude-3-5-haiku-20241022", "claude-3-5-haiku-20241022", "Small model exact match"),
            ("unknown-model", "claude-3-5-sonnet-20241022", "Default to big model")
        ]
        
        return self.run_test_case("Traditional Mode (No Passthrough)", provider, test_cases, manager)

    def test_openai_provider_passthrough(self) -> bool:
        """Test passthrough functionality with OpenAI-compatible providers"""
        provider = Provider(
            name="test_openai_passthrough",
            type=ProviderType.OPENAI,
            base_url="https://api.openrouter.ai/v1",
            auth_type=AuthType.API_KEY,
            auth_value="test-key",
            big_model="passthrough",
            small_model="passthrough",
            enabled=True
        )
        
        manager = ProviderManager.__new__(ProviderManager)
        manager.providers = [provider]
        manager.settings = {}
        
        test_cases = [
            ("gpt-4o", "gpt-4o", "GPT model passthrough"),
            ("gemini-pro", "gemini-pro", "Gemini model passthrough"),
            ("deepseek-chat", "deepseek-chat", "DeepSeek model passthrough"),
            ("claude-3-5-sonnet-20241022", "claude-3-5-sonnet-20241022", "Claude via OpenAI provider"),
            ("custom-openai-model", "custom-openai-model", "Custom OpenAI model")
        ]
        
        return self.run_test_case("OpenAI Provider Passthrough", provider, test_cases, manager)

    def test_model_classification_logic(self) -> bool:
        """Test the model classification logic (big vs small models)"""
        provider = Provider(
            name="test_classification",
            type=ProviderType.ANTHROPIC,
            base_url="https://api.test.com",
            auth_type=AuthType.API_KEY,
            auth_value="test-key",
            big_model="BIG_MODEL_CONFIG",
            small_model="SMALL_MODEL_CONFIG",
            enabled=True
        )
        
        manager = ProviderManager.__new__(ProviderManager)
        manager.providers = [provider]
        manager.settings = {}
        
        # Test big model classification
        big_model_cases = [
            ("claude-3-5-sonnet-20241022", "BIG_MODEL_CONFIG", "Sonnet classified as big"),
            ("claude-3-opus-20240229", "BIG_MODEL_CONFIG", "Opus classified as big"),
            ("custom-opus-model", "BIG_MODEL_CONFIG", "Custom opus classified as big"),
            ("my-sonnet-variant", "BIG_MODEL_CONFIG", "Custom sonnet classified as big"),
            ("unknown-model", "BIG_MODEL_CONFIG", "Unknown model defaults to big")
        ]
        
        # Test small model classification
        small_model_cases = [
            ("claude-3-5-haiku-20241022", "SMALL_MODEL_CONFIG", "Haiku classified as small"),
            ("claude-3-haiku-20240307", "SMALL_MODEL_CONFIG", "Haiku variant classified as small"),
            ("custom-haiku-model", "SMALL_MODEL_CONFIG", "Custom haiku classified as small")
        ]
        
        all_cases = big_model_cases + small_model_cases
        return self.run_test_case("Model Classification Logic", provider, all_cases, manager)

    def test_edge_cases(self) -> bool:
        """Test edge cases and boundary conditions"""
        provider = Provider(
            name="test_edge_cases",
            type=ProviderType.ANTHROPIC,
            base_url="https://api.test.com",
            auth_type=AuthType.API_KEY,
            auth_value="test-key",
            big_model="passthrough",
            small_model="passthrough",
            enabled=True
        )
        
        manager = ProviderManager.__new__(ProviderManager)
        manager.providers = [provider]
        manager.settings = {}
        
        test_cases = [
            ("", "", "Empty string"),
            ("PASSTHROUGH", "PASSTHROUGH", "Uppercase passthrough"),
            ("passthrough", "passthrough", "Lowercase passthrough as model name"),
            ("模型名称-中文", "模型名称-中文", "Chinese characters"),
            ("model_with_underscores", "model_with_underscores", "Underscores"),
            ("model-with-dashes", "model-with-dashes", "Dashes"),
            ("model.with.dots", "model.with.dots", "Dots"),
            ("model@version:1.0", "model@version:1.0", "Special characters")
        ]
        
        return self.run_test_case("Edge Cases and Boundary Conditions", provider, test_cases, manager)

    def run_all_tests(self) -> bool:
        """Run all tests and return overall success status"""
        if self.verbose:
            print("🎯 Claude Code Provider Balancer - Unified Passthrough Tests")
            print("=" * 70)
        
        tests = [
            self.test_passthrough_both_models,
            self.test_passthrough_big_model_only,
            self.test_passthrough_small_model_only,
            self.test_traditional_mode,
            self.test_openai_provider_passthrough,
            self.test_model_classification_logic,
            self.test_edge_cases
        ]
        
        passed_tests = 0
        total_tests = len(tests)
        
        for test_func in tests:
            if self.verbose:
                print(f"\n📋 {test_func.__doc__}")
                print("-" * 50)
            
            try:
                if test_func():
                    passed_tests += 1
                    if self.verbose:
                        print("✅ Test passed")
                else:
                    if self.verbose:
                        print("❌ Test failed")
            except Exception as e:
                if self.verbose:
                    print(f"💥 Test crashed: {e}")
        
        if self.verbose:
            print("\n" + "=" * 70)
            print(f"📊 Test Results: {passed_tests}/{total_tests} tests passed")
            
            if passed_tests == total_tests:
                print("🎉 All tests passed!")
                print("✅ Passthrough functionality is working correctly")
            else:
                print("❌ Some tests failed")
                print("🔧 Please check the implementation")
            
            print("\n📚 Configuration Guide:")
            print("  • Set big_model='passthrough' to enable big model passthrough")
            print("  • Set small_model='passthrough' to enable small model passthrough")
            print("  • Both can be set to 'passthrough' for complete passthrough")
            print("  • Traditional mapping still works when not using 'passthrough'")
        
        return passed_tests == total_tests


# Pytest-compatible test functions
def test_passthrough_both_models():
    """Pytest compatible test for both models passthrough"""
    tester = PassthroughTester(verbose=False)
    assert tester.test_passthrough_both_models(), "Both models passthrough test failed"


def test_passthrough_big_model_only():
    """Pytest compatible test for big model passthrough only"""
    tester = PassthroughTester(verbose=False)
    assert tester.test_passthrough_big_model_only(), "Big model passthrough test failed"


def test_passthrough_small_model_only():
    """Pytest compatible test for small model passthrough only"""
    tester = PassthroughTester(verbose=False)
    assert tester.test_passthrough_small_model_only(), "Small model passthrough test failed"


def test_traditional_mode():
    """Pytest compatible test for traditional mode"""
    tester = PassthroughTester(verbose=False)
    assert tester.test_traditional_mode(), "Traditional mode test failed"


def test_openai_provider_passthrough():
    """Pytest compatible test for OpenAI provider passthrough"""
    tester = PassthroughTester(verbose=False)
    assert tester.test_openai_provider_passthrough(), "OpenAI provider passthrough test failed"


def test_model_classification_logic():
    """Pytest compatible test for model classification"""
    tester = PassthroughTester(verbose=False)
    assert tester.test_model_classification_logic(), "Model classification test failed"


def test_edge_cases():
    """Pytest compatible test for edge cases"""
    tester = PassthroughTester(verbose=False)
    assert tester.test_edge_cases(), "Edge cases test failed"


def main():
    """Main function with argument parsing"""
    parser = argparse.ArgumentParser(description="Unified Passthrough Functionality Tester")
    parser.add_argument("-v", "--verbose", action="store_true", 
                       help="Enable verbose output with detailed test results")
    parser.add_argument("--pytest", action="store_true",
                       help="Run in pytest mode (quiet output)")
    
    args = parser.parse_args()
    
    if args.pytest:
        # Run pytest-style tests
        test_functions = [
            test_passthrough_both_models,
            test_passthrough_big_model_only,
            test_passthrough_small_model_only,
            test_traditional_mode,
            test_openai_provider_passthrough,
            test_model_classification_logic,
            test_edge_cases
        ]
        
        failed = 0
        for test_func in test_functions:
            try:
                test_func()
                print(f"✅ {test_func.__name__}")
            except AssertionError as e:
                print(f"❌ {test_func.__name__}: {e}")
                failed += 1
            except Exception as e:
                print(f"💥 {test_func.__name__}: {e}")
                failed += 1
        
        print(f"\nResults: {len(test_functions) - failed}/{len(test_functions)} tests passed")
        return 0 if failed == 0 else 1
    else:
        # Run verification-style tests
        tester = PassthroughTester(verbose=args.verbose or True)
        success = tester.run_all_tests()
        return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())