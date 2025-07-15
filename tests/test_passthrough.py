#!/usr/bin/env python3
"""
Test script for passthrough functionality in Claude Code Provider Balancer
"""

import pytest
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from src.provider_manager import Provider, ProviderManager, ProviderType, AuthType


def test_passthrough_big_model():
    """测试big_model设置为passthrough时的行为"""
    provider = Provider(
        name="test_passthrough",
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
    
    # 测试大模型请求时的透传
    result = manager.select_model(provider, "claude-3-5-sonnet-20241022")
    assert result == "claude-3-5-sonnet-20241022", f"Expected passthrough, got {result}"
    
    result = manager.select_model(provider, "claude-3-opus-20240229")
    assert result == "claude-3-opus-20240229", f"Expected passthrough, got {result}"
    
    # 测试小模型请求时不透传（使用配置的small_model）
    result = manager.select_model(provider, "claude-3-5-haiku-20241022")
    assert result == "claude-3-5-haiku-20241022", f"Expected configured small_model, got {result}"


def test_passthrough_small_model():
    """测试small_model设置为passthrough时的行为"""
    provider = Provider(
        name="test_passthrough",
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
    
    # 测试小模型请求时的透传
    result = manager.select_model(provider, "claude-3-5-haiku-20241022")
    assert result == "claude-3-5-haiku-20241022", f"Expected passthrough, got {result}"
    
    # 测试大模型请求时不透传（使用配置的big_model）
    result = manager.select_model(provider, "claude-3-5-sonnet-20241022")
    assert result == "claude-3-5-sonnet-20241022", f"Expected configured big_model, got {result}"


def test_passthrough_both_models():
    """测试big_model和small_model都设置为passthrough时的行为"""
    provider = Provider(
        name="test_passthrough",
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
    
    # 测试各种模型请求都透传
    test_models = [
        "claude-3-5-sonnet-20241022",
        "claude-3-opus-20240229", 
        "claude-3-5-haiku-20241022",
        "custom-model-name",
        "gpt-4o"
    ]
    
    for model in test_models:
        result = manager.select_model(provider, model)
        assert result == model, f"Expected passthrough of {model}, got {result}"


def test_passthrough_with_custom_model_names():
    """测试透传功能对自定义模型名称的处理"""
    provider = Provider(
        name="test_passthrough",
        type=ProviderType.OPENAI,
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
    
    # 测试各种自定义模型名称
    custom_models = [
        "gpt-4o-mini",
        "gemini-pro",
        "deepseek-chat",
        "claude-instant-v1",
        "my-custom-model-v2"
    ]
    
    for model in custom_models:
        result = manager.select_model(provider, model)
        assert result == model, f"Expected passthrough of {model}, got {result}"


def test_normal_model_selection_still_works():
    """测试正常的模型选择逻辑仍然正常工作"""
    provider = Provider(
        name="test_normal",
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
    
    # 测试大模型选择
    result = manager.select_model(provider, "claude-3-5-sonnet-20241022")
    assert result == "claude-3-5-sonnet-20241022"
    
    result = manager.select_model(provider, "claude-3-opus-20240229")
    assert result == "claude-3-5-sonnet-20241022"
    
    # 测试小模型选择
    result = manager.select_model(provider, "claude-3-5-haiku-20241022")
    assert result == "claude-3-5-haiku-20241022"
    
    # 测试默认选择（大模型）
    result = manager.select_model(provider, "unknown-model")
    assert result == "claude-3-5-sonnet-20241022"


def test_mixed_passthrough_and_normal():
    """测试透传和正常模式混合使用的场景"""
    provider = Provider(
        name="test_mixed",
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
    
    # 大模型请求透传
    result = manager.select_model(provider, "claude-3-5-sonnet-20241022")
    assert result == "claude-3-5-sonnet-20241022"
    
    result = manager.select_model(provider, "custom-big-model")
    assert result == "custom-big-model"
    
    # 小模型请求使用配置值
    result = manager.select_model(provider, "claude-3-5-haiku-20241022")
    assert result == "claude-3-5-haiku-20241022"


if __name__ == "__main__":
    # 运行所有测试
    test_passthrough_big_model()
    test_passthrough_small_model() 
    test_passthrough_both_models()
    test_passthrough_with_custom_model_names()
    test_normal_model_selection_still_works()
    test_mixed_passthrough_and_normal()
    
    print("所有测试通过！透传功能工作正常。")