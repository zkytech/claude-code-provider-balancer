"""Test runner script to run all tests with proper configuration."""

import sys
import subprocess
from pathlib import Path

def run_tests():
    """Run all tests using pytest."""
    
    # Get the project root directory
    project_root = Path(__file__).parent.parent
    tests_dir = project_root / "tests"
    
    # Ensure we're in the correct directory
    if not tests_dir.exists():
        print("Error: tests directory not found")
        return 1
    
    # Run pytest with proper configuration
    cmd = [
        sys.executable, "-m", "pytest",
        str(tests_dir),
        "-v",  # Verbose output
        "--tb=short",  # Short traceback format
        "--strict-markers",  # Strict marker handling
        "--asyncio-mode=auto",  # Auto asyncio mode
        "-x",  # Stop on first failure
        "--disable-warnings"  # Disable warnings for cleaner output
    ]
    
    print("Running Claude Provider Balancer tests...")
    print(f"Command: {' '.join(cmd)}")
    print("-" * 60)
    
    try:
        result = subprocess.run(cmd, cwd=project_root, check=False)
        return result.returncode
    except KeyboardInterrupt:
        print("\nTests interrupted by user")
        return 1
    except Exception as e:
        print(f"Error running tests: {e}")
        return 1

if __name__ == "__main__":
    exit_code = run_tests()
    sys.exit(exit_code)