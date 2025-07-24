"""
Debug script to check if test configuration is being loaded correctly.
"""

import sys
from pathlib import Path

# Add src to Python path
current_dir = Path(__file__).parent
src_dir = current_dir / "src"
sys.path.insert(0, str(src_dir))

print("=== Testing Configuration Loading ===")

# Test 1: Load test config directly
print("\n1. Loading config-test.yaml directly:")
test_config_path = current_dir / "config-test.yaml"
print(f"Test config path: {test_config_path}")
print(f"Test config exists: {test_config_path.exists()}")

if test_config_path.exists():
    import yaml
    with open(test_config_path, 'r', encoding='utf-8') as f:
        test_config = yaml.safe_load(f)
    
    providers = test_config.get('providers', [])
    print(f"Test config providers: {[p['name'] for p in providers]}")
    
    model_routes = test_config.get('model_routes', {})
    sonnet_routes = model_routes.get('*sonnet*', [])
    print(f"*sonnet* routes: {[r['provider'] for r in sonnet_routes]}")

# Test 2: Create ProviderManager with test config
print("\n2. Testing ProviderManager with test config:")
from core.provider_manager import ProviderManager

test_manager = ProviderManager(config_path=str(test_config_path))
print(f"Test manager providers: {[p.name for p in test_manager.providers]}")

# Test 3: Test model routing
print("\n3. Testing model routing:")
model = "claude-3-5-sonnet-20241022"
options = test_manager.select_model_and_provider_options(model)
if options:
    print(f"Options for {model}: {[(opt[0], opt[1].name) for opt in options]}")
    first_provider = options[0][1]
    print(f"First provider: {first_provider.name}")
    print(f"First provider base_url: {first_provider.base_url}")
else:
    print(f"No options found for {model}")

# Test 4: Check if main module is using the right config
print("\n4. Checking main module provider_manager:")
try:
    import main
    if hasattr(main, 'provider_manager') and main.provider_manager:
        print(f"Main module providers: {[p.name for p in main.provider_manager.providers]}")
        options = main.provider_manager.select_model_and_provider_options(model)
        if options:
            print(f"Main module options for {model}: {[(opt[0], opt[1].name) for opt in options]}")
            first_provider = options[0][1]
            print(f"Main module first provider base_url: {first_provider.base_url}")
    else:
        print("Main module provider_manager not found or None")
except Exception as e:
    print(f"Error checking main module: {e}")