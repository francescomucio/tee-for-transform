"""
Testing framework for database adapters.

This module provides utilities for testing database adapters including:
- Connection testing
- SQL dialect conversion testing
- Materialization testing
- Performance benchmarking
"""

import logging
import time
from collections.abc import Callable
from contextlib import contextmanager, suppress
from typing import Any

from .base import DatabaseAdapter


class AdapterTester:
    """Test framework for database adapters."""

    def __init__(self, adapter: DatabaseAdapter) -> None:
        self.adapter = adapter
        self.logger = logging.getLogger(self.__class__.__name__)
        self.test_results = {}

    def run_all_tests(self) -> dict[str, Any]:
        """Run all available tests."""
        self.logger.info(f"Running tests for {self.adapter.__class__.__name__}")

        tests = [
            ("connection", self.test_connection),
            ("dialect_conversion", self.test_dialect_conversion),
            ("materializations", self.test_materializations),
            ("table_operations", self.test_table_operations),
            ("performance", self.test_performance),
        ]

        results = {}
        for test_name, test_func in tests:
            try:
                self.logger.info(f"Running test: {test_name}")
                result = test_func()
                results[test_name] = result
                self.logger.info(
                    f"Test {test_name}: {'PASSED' if result.get('success', False) else 'FAILED'}"
                )
            except Exception as e:
                self.logger.error(f"Test {test_name} failed with exception: {e}")
                results[test_name] = {"success": False, "error": str(e)}

        self.test_results = results
        return results

    def test_connection(self) -> dict[str, Any]:
        """Test database connection."""
        try:
            self.adapter.connect()
            db_info = self.adapter.get_database_info()
            self.adapter.disconnect()

            return {"success": True, "database_info": db_info, "message": "Connection successful"}
        except Exception as e:
            return {"success": False, "error": str(e), "message": "Connection failed"}

    def test_dialect_conversion(self) -> dict[str, Any]:
        """Test SQL dialect conversion."""
        if not self.adapter.config.source_dialect:
            return {
                "success": True,
                "message": "No source dialect configured, skipping conversion test",
            }

        test_queries = [
            "SELECT * FROM users WHERE id = 1",
            "SELECT u.name, p.title FROM users u JOIN posts p ON u.id = p.user_id",
            "SELECT COUNT(*) as total FROM orders WHERE created_at > '2023-01-01'",
        ]

        results = []
        for query in test_queries:
            try:
                converted = self.adapter.convert_sql_dialect(query)
                results.append({"original": query, "converted": converted, "success": True})
            except Exception as e:
                results.append({"original": query, "error": str(e), "success": False})

        success_count = sum(1 for r in results if r["success"])
        return {
            "success": success_count == len(test_queries),
            "results": results,
            "message": f"Converted {success_count}/{len(test_queries)} queries successfully",
        }

    def test_materializations(self) -> dict[str, Any]:
        """Test supported materialization types."""
        try:
            supported = self.adapter.get_supported_materializations()
            return {
                "success": True,
                "supported_materializations": [m.value for m in supported],
                "message": f"Supports {len(supported)} materialization types",
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to get supported materializations",
            }

    def test_table_operations(self) -> dict[str, Any]:
        """Test basic table operations."""
        test_table = "test_table_operations"
        test_query = "SELECT 1 as id, 'test' as name"

        try:
            self.adapter.connect()

            # Test table creation
            self.adapter.create_table(test_table, test_query)

            # Test table exists
            exists = self.adapter.table_exists(test_table)

            # Test table info
            table_info = self.adapter.get_table_info(test_table)

            # Test query execution
            result = self.adapter.execute_query(f"SELECT * FROM {test_table}")

            # Test table drop
            self.adapter.drop_table(test_table)

            return {
                "success": True,
                "table_created": True,
                "table_exists": exists,
                "table_info": table_info,
                "query_result": result,
                "message": "All table operations successful",
            }
        except Exception as e:
            return {"success": False, "error": str(e), "message": "Table operations failed"}
        finally:
            with suppress(Exception):
                self.adapter.disconnect()

    def test_performance(self) -> dict[str, Any]:
        """Test basic performance metrics."""
        test_table = "test_performance"
        test_query = "SELECT 1 as id, 'test' as name"

        try:
            self.adapter.connect()

            # Test connection time
            start_time = time.time()
            self.adapter.connect()
            connection_time = time.time() - start_time

            # Test table creation time
            start_time = time.time()
            self.adapter.create_table(test_table, test_query)
            creation_time = time.time() - start_time

            # Test query execution time
            start_time = time.time()
            self.adapter.execute_query(f"SELECT * FROM {test_table}")
            query_time = time.time() - start_time

            # Cleanup
            self.adapter.drop_table(test_table)

            return {
                "success": True,
                "connection_time": connection_time,
                "creation_time": creation_time,
                "query_time": query_time,
                "message": "Performance test completed",
            }
        except Exception as e:
            return {"success": False, "error": str(e), "message": "Performance test failed"}
        finally:
            with suppress(Exception):
                self.adapter.disconnect()

    @contextmanager
    def test_connection_context(self) -> Any:
        """Context manager for testing with automatic cleanup."""
        try:
            self.adapter.connect()
            yield self.adapter
        finally:
            with suppress(Exception):
                self.adapter.disconnect()


def test_adapter(adapter: DatabaseAdapter) -> dict[str, Any]:
    """
    Convenience function to test an adapter.

    Args:
        adapter: Database adapter to test

    Returns:
        Test results dictionary
    """
    tester = AdapterTester(adapter)
    return tester.run_all_tests()


def benchmark_adapter(
    adapter: DatabaseAdapter, operations: list[Callable], iterations: int = 10
) -> dict[str, Any]:
    """
    Benchmark an adapter with custom operations.

    Args:
        adapter: Database adapter to benchmark
        operations: List of callable operations to benchmark
        iterations: Number of iterations to run

    Returns:
        Benchmark results dictionary
    """
    results = {}

    for i, operation in enumerate(operations):
        times = []
        for _ in range(iterations):
            start_time = time.time()
            try:
                operation(adapter)
                times.append(time.time() - start_time)
            except Exception:
                times.append(float("inf"))

        results[f"operation_{i}"] = {
            "min_time": min(times),
            "max_time": max(times),
            "avg_time": sum(times) / len(times),
            "success_rate": sum(1 for t in times if t != float("inf")) / len(times),
        }

    return results
