#!/usr/bin/env python3
"""
Test runner for incremental materialization tests.

This script provides different test execution modes for incremental tests.
"""

import argparse
import subprocess
import sys
from pathlib import Path


def run_command(cmd, description):
    """Run a command and return the result."""
    print(f"\n{'=' * 60}")
    print(f"Running: {description}")
    print(f"Command: {' '.join(cmd)}")
    print(f"{'=' * 60}")

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.stdout:
        print("STDOUT:")
        print(result.stdout)

    if result.stderr:
        print("STDERR:")
        print(result.stderr)

    print(f"Exit code: {result.returncode}")
    return result.returncode == 0


def run_unit_tests():
    """Run unit tests for incremental executor."""
    cmd = ["uv", "run", "pytest", "tests/engine/incremental/", "-v", "--tb=short"]
    return run_command(cmd, "Unit Tests - Incremental Executor")


def run_adapter_interface_tests():
    """Run adapter interface tests."""
    cmd = [
        "uv",
        "run",
        "pytest",
        "tests/engine/test_incremental_adapter_interface.py",
        "-v",
        "--tb=short",
    ]
    return run_command(cmd, "Adapter Interface Tests")


def run_duckdb_tests():
    """Run DuckDB-specific tests."""
    cmd = ["uv", "run", "pytest", "tests/adapters/duckdb/test_incremental.py", "-v", "--tb=short"]
    return run_command(cmd, "DuckDB Integration Tests")


def run_performance_tests():
    """Run performance tests."""
    cmd = [
        "uv",
        "run",
        "pytest",
        "tests/adapters/duckdb/test_incremental_performance.py",
        "-v",
        "--tb=short",
        "-m",
        "slow",
    ]
    return run_command(cmd, "Performance Tests")


def run_all_tests():
    """Run all incremental tests."""
    cmd = [
        "uv",
        "run",
        "pytest",
        "tests/engine/incremental/",
        "tests/engine/test_incremental_adapter_interface.py",
        "tests/adapters/duckdb/test_incremental.py",
        "-v",
        "--tb=short",
    ]
    return run_command(cmd, "All Incremental Tests")


def run_coverage_tests():
    """Run tests with coverage reporting."""
    cmd = [
        "uv",
        "run",
        "pytest",
        "tests/engine/incremental/",
        "tests/engine/test_incremental_adapter_interface.py",
        "tests/adapters/duckdb/test_incremental.py",
        "--cov=t4t.engine.incremental_executor",
        "--cov=t4t.adapters.duckdb.adapter",
        "--cov-report=html",
        "--cov-report=term-missing",
        "-v",
    ]
    return run_command(cmd, "Coverage Tests")


def run_specific_test(test_path):
    """Run a specific test file or test function."""
    cmd = ["uv", "run", "pytest", test_path, "-v", "--tb=short"]
    return run_command(cmd, f"Specific Test: {test_path}")


def main():
    """Main test runner."""
    parser = argparse.ArgumentParser(description="Run incremental materialization tests")
    parser.add_argument(
        "test_type",
        choices=["unit", "adapter", "duckdb", "performance", "all", "coverage", "specific"],
        help="Type of tests to run",
    )
    parser.add_argument(
        "--test-path", help="Specific test path (required for 'specific' test type)"
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose output")

    args = parser.parse_args()

    # Change to project root directory
    project_root = Path(__file__).parent.parent
    import os

    os.chdir(project_root)

    success = True

    if args.test_type == "unit":
        success = run_unit_tests()
    elif args.test_type == "adapter":
        success = run_adapter_interface_tests()
    elif args.test_type == "duckdb":
        success = run_duckdb_tests()
    elif args.test_type == "performance":
        success = run_performance_tests()
    elif args.test_type == "all":
        success = run_all_tests()
    elif args.test_type == "coverage":
        success = run_coverage_tests()
    elif args.test_type == "specific":
        if not args.test_path:
            print("Error: --test-path is required for 'specific' test type")
            sys.exit(1)
        success = run_specific_test(args.test_path)

    if success:
        print(f"\n{'=' * 60}")
        print("✅ All tests passed!")
        print(f"{'=' * 60}")
        sys.exit(0)
    else:
        print(f"\n{'=' * 60}")
        print("❌ Some tests failed!")
        print(f"{'=' * 60}")
        sys.exit(1)


if __name__ == "__main__":
    main()
