"""
End-to-end tests for auto_incremental feature.

These tests verify the complete flow including:
- First run (table creation)
- Incremental runs
- ID stability after deletion
- Time filter handling for dimension tables
- Schema change handling
"""

from typing import Any

import pytest

from tee.engine.materialization.incremental_executor import IncrementalExecutor
from tee.engine.materialization.materialization_handler import MaterializationHandler


@pytest.mark.integration
class TestAutoIncrementalE2E:
    """End-to-end tests for auto_incremental feature."""

    @pytest.fixture
    def executor(self, state_manager):
        """Create IncrementalExecutor instance."""
        return IncrementalExecutor(state_manager)

    @pytest.fixture
    def materialization_handler(self, duckdb_adapter, state_manager):
        """Create MaterializationHandler instance."""
        return MaterializationHandler(duckdb_adapter, state_manager, {})

    def _save_model_state(
        self, state_manager, table_name: str, sql_query: str, metadata: dict[str, Any]
    ):
        """Helper to save model state after execution."""
        from datetime import UTC, datetime

        sql_hash = state_manager.compute_sql_hash(sql_query)
        incremental_config = metadata.get("incremental", {}) if metadata else {}
        config_hash = state_manager.compute_config_hash(incremental_config)
        current_time = datetime.now(UTC).isoformat()
        strategy = incremental_config.get("strategy") if incremental_config else None

        state_manager.save_model_state(
            model_name=table_name,
            materialization="incremental",
            sql_hash=sql_hash,
            config_hash=config_hash,
            last_processed_value=current_time,
            strategy=strategy,
        )

    @pytest.fixture
    def source_table(self, duckdb_adapter):
        """Create source table with test data."""
        duckdb_adapter.execute_query(
            """
            CREATE SCHEMA IF NOT EXISTS test_schema
            """
        )
        duckdb_adapter.execute_query(
            """
            CREATE TABLE IF NOT EXISTS test_schema.national_articles (
                article_id INTEGER,
                brand VARCHAR,
                category VARCHAR,
                created_date DATE
            )
            """
        )

        # Insert test data with 20 distinct brands
        # Create brands that will sort alphabetically with SportCap as 13th
        # Use names that sort: Brand A, Brand B, ..., Brand L, SportCap, Brand M, ..., Brand S
        brands = []
        for i in range(20):
            if i < 12:
                brands.append(f"Brand {chr(65 + i)}")  # Brand A to Brand L (12 brands)
            elif i == 12:
                brands.append("SportCap")  # 13th brand alphabetically (between L and M)
            else:
                # Continue with Brand M onwards (but we need to account for SportCap)
                # Actually, let's use simpler names that sort correctly
                pass

        # Create brand names that will sort with SportCap as 13th alphabetically
        # Use: BrandA, BrandB, ..., BrandL (12 brands), then "BrandLA" (13th, comes after L, before M), then BrandM, BrandN, ..., BrandS (7 more)
        # When sorted: BrandA < BrandB < ... < BrandL < BrandLA < BrandM < ... < BrandS
        brand_names = [f"Brand{chr(65 + i)}" for i in range(12)]  # BrandA to BrandL (12 brands)
        brand_names.append(
            "BrandLA"
        )  # Will be 13th when sorted (comes after BrandL, before BrandM)
        brand_names.extend([f"Brand{chr(77 + i)}" for i in range(7)])  # BrandM to BrandS (7 brands)
        # Total: 12 + 1 + 7 = 20 brands
        # We'll use "BrandLA" as our test brand (like SportCap in the user's scenario)

        values = []
        for i, brand in enumerate(brand_names):
            values.append(f"({i + 1}, '{brand}', 'Category {i % 3 + 1}', '2024-01-{i + 1:02d}')")

        duckdb_adapter.execute_query(
            f"""
            INSERT INTO test_schema.national_articles VALUES
            {", ".join(values)}
            """
        )

    @pytest.fixture
    def dim_brand_metadata(self):
        """Metadata for dim_brand dimension table."""
        return {
            "description": "Brand dimension table",
            "materialization": "incremental",
            "incremental": {
                "strategy": "merge",
                "merge": {
                    "unique_key": ["brand_name"],
                    "filter_column": "created_date",
                    "start_value": "auto",
                },
            },
            "schema": [
                {
                    "name": "brand_id",
                    "datatype": "integer",
                    "description": "Unique identifier for the brand",
                    "tests": ["not_null", "unique"],
                    "auto_incremental": True,
                },
                {
                    "name": "brand_name",
                    "datatype": "string",
                    "description": "Name of the brand",
                    "tests": ["not_null", "unique"],
                },
            ],
            "tests": ["row_count_gt_0"],
        }

    def test_first_run_creates_table_with_correct_ids(
        self, materialization_handler, source_table, dim_brand_metadata, state_manager
    ):
        """Test that first run creates table with sequential IDs starting from 1."""
        sql = """
        SELECT DISTINCT brand AS brand_name
        FROM test_schema.national_articles
        WHERE brand IS NOT NULL
        ORDER BY brand_name
        """

        # First run - should create table
        materialization_handler.materialize(
            table_name="test_schema.dim_brand",
            sql_query=sql,
            materialization="incremental",
            metadata=dim_brand_metadata,
        )

        # Save state after first run (normally done by ModelExecutor)
        self._save_model_state(state_manager, "test_schema.dim_brand", sql, dim_brand_metadata)

        # Verify table was created
        assert materialization_handler.adapter.table_exists("test_schema.dim_brand")

        # Check that all 20 brands are present
        result = materialization_handler.adapter.execute_query(
            "SELECT COUNT(*) FROM test_schema.dim_brand"
        )
        assert result[0][0] == 20

        # Check that IDs are sequential starting from 1
        result = materialization_handler.adapter.execute_query(
            "SELECT brand_id, brand_name FROM test_schema.dim_brand ORDER BY brand_id"
        )
        for i, (brand_id, brand_name) in enumerate(result, start=1):
            assert brand_id == i, f"Expected brand_id={i}, got {brand_id} for {brand_name}"

        # Verify BrandLA has ID 13 (13th brand alphabetically)
        result = materialization_handler.adapter.execute_query(
            "SELECT brand_id FROM test_schema.dim_brand WHERE brand_name = 'BrandLA'"
        )
        assert len(result) > 0, "BrandLA should exist"
        assert result[0][0] == 13, f"BrandLA should have ID 13 on first run, got {result[0][0]}"

    def test_id_stability_after_deletion(
        self, materialization_handler, source_table, dim_brand_metadata, state_manager
    ):
        """Test that after deleting a record, re-running assigns MAX(id) + 1."""
        sql = """
        SELECT DISTINCT brand AS brand_name
        FROM test_schema.national_articles
        WHERE brand IS NOT NULL
        ORDER BY brand_name
        """

        # First run - create table
        materialization_handler.materialize(
            table_name="test_schema.dim_brand",
            sql_query=sql,
            materialization="incremental",
            metadata=dim_brand_metadata,
        )

        # Save state after first run (normally done by ModelExecutor)
        self._save_model_state(state_manager, "test_schema.dim_brand", sql, dim_brand_metadata)

        # Verify BrandLA exists with ID 13
        result = materialization_handler.adapter.execute_query(
            "SELECT brand_id FROM test_schema.dim_brand WHERE brand_name = 'BrandLA'"
        )
        assert result[0][0] == 13

        # Get max ID before deletion
        result = materialization_handler.adapter.execute_query(
            "SELECT MAX(brand_id) FROM test_schema.dim_brand"
        )
        max_id_before = result[0][0]
        assert max_id_before == 20

        # Delete BrandLA (like SportCap in user's scenario)
        materialization_handler.adapter.execute_query(
            "DELETE FROM test_schema.dim_brand WHERE brand_name = 'BrandLA'"
        )

        # Verify deletion
        result = materialization_handler.adapter.execute_query(
            "SELECT COUNT(*) FROM test_schema.dim_brand WHERE brand_name = 'BrandLA'"
        )
        assert result[0][0] == 0

        # Verify count decreased
        result = materialization_handler.adapter.execute_query(
            "SELECT COUNT(*) FROM test_schema.dim_brand"
        )
        assert result[0][0] == 19

        # Second run - should add BrandLA back with ID 21 (MAX(id) + 1)
        materialization_handler.materialize(
            table_name="test_schema.dim_brand",
            sql_query=sql,
            materialization="incremental",
            metadata=dim_brand_metadata,
        )

        # Verify BrandLA was added back
        result = materialization_handler.adapter.execute_query(
            "SELECT brand_id, brand_name FROM test_schema.dim_brand WHERE brand_name = 'BrandLA'"
        )
        assert len(result) == 1
        brandla_id = result[0][0]
        assert brandla_id == 21, f"Expected BrandLA to have ID 21, got {brandla_id}"

        # Verify total count is back to 20
        result = materialization_handler.adapter.execute_query(
            "SELECT COUNT(*) FROM test_schema.dim_brand"
        )
        assert result[0][0] == 20

        # Verify max ID is now 21
        result = materialization_handler.adapter.execute_query(
            "SELECT MAX(brand_id) FROM test_schema.dim_brand"
        )
        assert result[0][0] == 21

    def test_incremental_run_only_adds_new_records(
        self, materialization_handler, source_table, dim_brand_metadata, state_manager
    ):
        """Test that incremental runs only add new records, not duplicates."""
        sql = """
        SELECT DISTINCT brand AS brand_name
        FROM test_schema.national_articles
        WHERE brand IS NOT NULL
        ORDER BY brand_name
        """

        # First run
        materialization_handler.materialize(
            table_name="test_schema.dim_brand",
            sql_query=sql,
            materialization="incremental",
            metadata=dim_brand_metadata,
        )

        # Save state after first run
        self._save_model_state(state_manager, "test_schema.dim_brand", sql, dim_brand_metadata)

        # Verify 20 records
        result = materialization_handler.adapter.execute_query(
            "SELECT COUNT(*) FROM test_schema.dim_brand"
        )
        assert result[0][0] == 20

        # Second run with same data - should not add duplicates
        materialization_handler.materialize(
            table_name="test_schema.dim_brand",
            sql_query=sql,
            materialization="incremental",
            metadata=dim_brand_metadata,
        )

        # Verify still 20 records (no duplicates)
        result = materialization_handler.adapter.execute_query(
            "SELECT COUNT(*) FROM test_schema.dim_brand"
        )
        assert result[0][0] == 20

        # Verify all IDs are still sequential
        result = materialization_handler.adapter.execute_query(
            "SELECT brand_id FROM test_schema.dim_brand ORDER BY brand_id"
        )
        ids = [row[0] for row in result]
        assert ids == list(range(1, 21)), "IDs should remain sequential 1-20"

    def test_time_filter_skipped_for_dimension_tables(
        self, materialization_handler, source_table, dim_brand_metadata, state_manager
    ):
        """Test that time filter is skipped when filter_column doesn't exist in target table."""
        sql = """
        SELECT DISTINCT brand AS brand_name
        FROM test_schema.national_articles
        WHERE brand IS NOT NULL
        ORDER BY brand_name
        """

        # This should not fail even though created_date doesn't exist in dim_brand
        # The system should detect this and skip time filtering
        materialization_handler.materialize(
            table_name="test_schema.dim_brand",
            sql_query=sql,
            materialization="incremental",
            metadata=dim_brand_metadata,
        )

        # Save state after first run
        self._save_model_state(state_manager, "test_schema.dim_brand", sql, dim_brand_metadata)

        # Verify table was created successfully
        assert materialization_handler.adapter.table_exists("test_schema.dim_brand")

        # Verify all records are present (time filter was skipped)
        result = materialization_handler.adapter.execute_query(
            "SELECT COUNT(*) FROM test_schema.dim_brand"
        )
        assert result[0][0] == 20

    def test_table_exists_check_with_schema_qualified_name(
        self, materialization_handler, source_table, dim_brand_metadata, state_manager
    ):
        """Test that table_exists correctly handles schema-qualified table names."""
        sql = """
        SELECT DISTINCT brand AS brand_name
        FROM test_schema.national_articles
        WHERE brand IS NOT NULL
        ORDER BY brand_name
        """

        # First run - creates table
        materialization_handler.materialize(
            table_name="test_schema.dim_brand",
            sql_query=sql,
            materialization="incremental",
            metadata=dim_brand_metadata,
        )

        # Save state after first run
        self._save_model_state(state_manager, "test_schema.dim_brand", sql, dim_brand_metadata)

        # Verify table_exists works with schema-qualified name
        assert materialization_handler.adapter.table_exists("test_schema.dim_brand")

        # Second run - should detect table exists and run incrementally
        materialization_handler.materialize(
            materialization="incremental",
            table_name="test_schema.dim_brand",
            sql_query=sql,
            metadata=dim_brand_metadata,
        )

        # Should still have 20 records (no duplicates)
        result = materialization_handler.adapter.execute_query(
            "SELECT COUNT(*) FROM test_schema.dim_brand"
        )
        assert result[0][0] == 20

    def test_append_strategy_with_auto_incremental(
        self, materialization_handler, source_table, state_manager, duckdb_adapter
    ):
        """Test append strategy with auto_incremental column."""
        metadata = {
            "description": "Brand dimension table",
            "materialization": "incremental",
            "incremental": {
                "strategy": "append",
                "append": {
                    "filter_column": "created_date",
                    "start_value": "auto",
                },
            },
            "schema": [
                {
                    "name": "brand_id",
                    "datatype": "integer",
                    "auto_incremental": True,
                },
                {
                    "name": "brand_name",
                    "datatype": "string",
                },
            ],
        }

        sql = """
        SELECT DISTINCT brand AS brand_name
        FROM test_schema.national_articles
        WHERE brand IS NOT NULL
        ORDER BY brand_name
        LIMIT 10
        """

        # First run
        materialization_handler.materialize(
            table_name="test_schema.dim_brand_append",
            sql_query=sql,
            materialization="incremental",
            metadata=metadata,
        )

        # Save state after first run (normally done by ModelExecutor)
        self._save_model_state(state_manager, "test_schema.dim_brand_append", sql, metadata)

        # Verify 10 records with IDs 1-10
        result = materialization_handler.adapter.execute_query(
            "SELECT COUNT(*) FROM test_schema.dim_brand_append"
        )
        assert result[0][0] == 10

        result = materialization_handler.adapter.execute_query(
            "SELECT MAX(brand_id) FROM test_schema.dim_brand_append"
        )
        assert result[0][0] == 10

        # Second run with same query - append strategy will add duplicates
        # Note: Append doesn't exclude duplicates, it just increments IDs
        # So we'll get 10 more records (duplicates) with IDs 11-20
        materialization_handler.materialize(
            table_name="test_schema.dim_brand_append",
            sql_query=sql,
            materialization="incremental",
            metadata=metadata,
        )

        # Should have 20 records total (10 from first run + 10 duplicates from second run)
        result = materialization_handler.adapter.execute_query(
            "SELECT COUNT(*) FROM test_schema.dim_brand_append"
        )
        assert result[0][0] == 20, "Append should add duplicates, not exclude them"

        result = materialization_handler.adapter.execute_query(
            "SELECT MAX(brand_id) FROM test_schema.dim_brand_append"
        )
        assert result[0][0] == 20, "Max ID should be 20 (10 original + 10 duplicates)"

    def test_sql_hash_uses_original_query_not_wrapped(
        self, materialization_handler, source_table, dim_brand_metadata, state_manager
    ):
        """Test that SQL hash computation uses original query, not wrapped query."""
        sql = """
        SELECT DISTINCT brand AS brand_name
        FROM test_schema.national_articles
        WHERE brand IS NOT NULL
        ORDER BY brand_name
        """

        # First run
        materialization_handler.materialize(
            table_name="test_schema.dim_brand",
            sql_query=sql,
            materialization="incremental",
            metadata=dim_brand_metadata,
        )

        # Save state after first run
        self._save_model_state(state_manager, "test_schema.dim_brand", sql, dim_brand_metadata)

        # Get state after first run
        state = state_manager.get_model_state("test_schema.dim_brand")
        first_run_hash = state.sql_hash

        # Second run with same query - should run incrementally
        materialization_handler.materialize(
            materialization="incremental",
            table_name="test_schema.dim_brand",
            sql_query=sql,
            metadata=dim_brand_metadata,
        )

        # Get state after second run
        state = state_manager.get_model_state("test_schema.dim_brand")
        second_run_hash = state.sql_hash

        # Hashes should match (using original query, not wrapped)
        assert first_run_hash == second_run_hash, "SQL hash should remain stable across runs"

        # Verify it ran incrementally (no duplicates)
        result = materialization_handler.adapter.execute_query(
            "SELECT COUNT(*) FROM test_schema.dim_brand"
        )
        assert result[0][0] == 20

    def test_explicit_mode_merge_strategy(
        self, materialization_handler, source_table, dim_brand_metadata, state_manager
    ):
        """Test explicit mode where query includes ROW_NUMBER() for ID column."""
        # Explicit mode: query includes the ID column
        sql = """
        SELECT
            row_number() over (order by brand) as brand_id,
            brand as brand_name
        FROM test_schema.national_articles
        WHERE brand IS NOT NULL
        GROUP BY brand
        """

        # First run - should create table
        materialization_handler.materialize(
            table_name="test_schema.dim_brand_explicit",
            sql_query=sql,
            materialization="incremental",
            metadata=dim_brand_metadata,
        )

        # Save state after first run
        self._save_model_state(
            state_manager, "test_schema.dim_brand_explicit", sql, dim_brand_metadata
        )

        # Verify table was created
        assert materialization_handler.adapter.table_exists("test_schema.dim_brand_explicit")

        # Check that all 20 brands are present
        result = materialization_handler.adapter.execute_query(
            "SELECT COUNT(*) FROM test_schema.dim_brand_explicit"
        )
        assert result[0][0] == 20

        # Check that IDs are sequential starting from 1
        result = materialization_handler.adapter.execute_query(
            "SELECT brand_id, brand_name FROM test_schema.dim_brand_explicit ORDER BY brand_id"
        )
        for i, (brand_id, brand_name) in enumerate(result, start=1):
            assert brand_id == i, f"Expected brand_id={i}, got {brand_id} for {brand_name}"

        # Second run - should not add duplicates (merge strategy)
        materialization_handler.materialize(
            table_name="test_schema.dim_brand_explicit",
            sql_query=sql,
            materialization="incremental",
            metadata=dim_brand_metadata,
        )

        # Verify still 20 records (no duplicates)
        result = materialization_handler.adapter.execute_query(
            "SELECT COUNT(*) FROM test_schema.dim_brand_explicit"
        )
        assert result[0][0] == 20

    def test_explicit_mode_id_stability_after_deletion(
        self, materialization_handler, source_table, dim_brand_metadata, state_manager
    ):
        """Test explicit mode ID stability after deletion."""
        sql = """
        SELECT
            row_number() over (order by brand) as brand_id,
            brand as brand_name
        FROM test_schema.national_articles
        WHERE brand IS NOT NULL
        GROUP BY brand
        """

        # First run
        materialization_handler.materialize(
            table_name="test_schema.dim_brand_explicit2",
            sql_query=sql,
            materialization="incremental",
            metadata=dim_brand_metadata,
        )

        # Save state after first run
        self._save_model_state(
            state_manager, "test_schema.dim_brand_explicit2", sql, dim_brand_metadata
        )

        # Get max ID before deletion
        result = materialization_handler.adapter.execute_query(
            "SELECT MAX(brand_id) FROM test_schema.dim_brand_explicit2"
        )
        max_id_before = result[0][0]
        assert max_id_before == 20

        # Delete BrandLA
        materialization_handler.adapter.execute_query(
            "DELETE FROM test_schema.dim_brand_explicit2 WHERE brand_name = 'BrandLA'"
        )

        # Second run - should add BrandLA back with ID 21 (MAX(id) + 1)
        materialization_handler.materialize(
            table_name="test_schema.dim_brand_explicit2",
            sql_query=sql,
            materialization="incremental",
            metadata=dim_brand_metadata,
        )

        # Verify BrandLA was added back with correct ID
        result = materialization_handler.adapter.execute_query(
            "SELECT brand_id FROM test_schema.dim_brand_explicit2 WHERE brand_name = 'BrandLA'"
        )
        assert len(result) == 1
        assert result[0][0] == 21, f"Expected BrandLA to have ID 21, got {result[0][0]}"

    def test_delete_insert_strategy_with_auto_incremental(
        self, materialization_handler, source_table, state_manager
    ):
        """Test delete+insert strategy with auto_incremental.

        Note: delete+insert requires where_condition, but for dimension tables
        we use a simple condition that works on the target table.
        """
        metadata = {
            "description": "Brand dimension table",
            "materialization": "incremental",
            "incremental": {
                "strategy": "delete_insert",
                "delete_insert": {
                    # where_condition is required for delete+insert
                    # Use a condition that works on target table (brand_name exists)
                    "where_condition": "brand_name IS NOT NULL",
                    "filter_column": "created_date",
                    "start_value": "auto",
                    "unique_key": ["brand_name"],
                },
            },
            "schema": [
                {
                    "name": "brand_id",
                    "datatype": "integer",
                    "auto_incremental": True,
                },
                {
                    "name": "brand_name",
                    "datatype": "string",
                },
            ],
        }

        sql = """
        SELECT DISTINCT brand AS brand_name
        FROM test_schema.national_articles
        WHERE brand IS NOT NULL
        """

        # First run
        materialization_handler.materialize(
            table_name="test_schema.dim_brand_delete_insert",
            sql_query=sql,
            materialization="incremental",
            metadata=metadata,
        )

        # Save state after first run
        self._save_model_state(state_manager, "test_schema.dim_brand_delete_insert", sql, metadata)

        # Verify table was created
        assert materialization_handler.adapter.table_exists("test_schema.dim_brand_delete_insert")

        # Verify 20 records
        result = materialization_handler.adapter.execute_query(
            "SELECT COUNT(*) FROM test_schema.dim_brand_delete_insert"
        )
        assert result[0][0] == 20

        # Get IDs from first run
        first_run_ids = {
            row[1]: row[0]
            for row in materialization_handler.adapter.execute_query(
                "SELECT brand_id, brand_name FROM test_schema.dim_brand_delete_insert ORDER BY brand_id"
            )
        }

        # Second run - should maintain IDs for existing records
        materialization_handler.materialize(
            table_name="test_schema.dim_brand_delete_insert",
            sql_query=sql,
            materialization="incremental",
            metadata=metadata,
        )

        # Verify still 20 records
        result = materialization_handler.adapter.execute_query(
            "SELECT COUNT(*) FROM test_schema.dim_brand_delete_insert"
        )
        assert result[0][0] == 20

        # Verify IDs remain stable
        second_run_ids = {
            row[1]: row[0]
            for row in materialization_handler.adapter.execute_query(
                "SELECT brand_id, brand_name FROM test_schema.dim_brand_delete_insert ORDER BY brand_id"
            )
        }
        assert first_run_ids == second_run_ids, "IDs should remain stable across delete+insert runs"

    def test_empty_source_table(
        self, materialization_handler, dim_brand_metadata, state_manager, duckdb_adapter
    ):
        """Test handling of empty source table."""
        # Create empty source table
        duckdb_adapter.execute_query(
            """
            CREATE SCHEMA IF NOT EXISTS test_schema
            """
        )
        duckdb_adapter.execute_query(
            """
            CREATE TABLE IF NOT EXISTS test_schema.empty_source (
                article_id INTEGER,
                brand VARCHAR,
                created_date DATE
            )
            """
        )

        sql = """
        SELECT DISTINCT brand AS brand_name
        FROM test_schema.empty_source
        WHERE brand IS NOT NULL
        """

        # First run with empty source
        materialization_handler.materialize(
            table_name="test_schema.dim_brand_empty",
            sql_query=sql,
            materialization="incremental",
            metadata=dim_brand_metadata,
        )

        # Table should be created but empty
        assert materialization_handler.adapter.table_exists("test_schema.dim_brand_empty")

        result = materialization_handler.adapter.execute_query(
            "SELECT COUNT(*) FROM test_schema.dim_brand_empty"
        )
        assert result[0][0] == 0

    def test_all_records_already_exist(
        self, materialization_handler, source_table, dim_brand_metadata, state_manager
    ):
        """Test incremental run when all records already exist (no new records)."""
        sql = """
        SELECT DISTINCT brand AS brand_name
        FROM test_schema.national_articles
        WHERE brand IS NOT NULL
        """

        # First run - creates table with all 20 brands
        materialization_handler.materialize(
            table_name="test_schema.dim_brand_all_exist",
            sql_query=sql,
            materialization="incremental",
            metadata=dim_brand_metadata,
        )

        # Save state after first run
        self._save_model_state(
            state_manager, "test_schema.dim_brand_all_exist", sql, dim_brand_metadata
        )

        # Verify 20 records
        result = materialization_handler.adapter.execute_query(
            "SELECT COUNT(*) FROM test_schema.dim_brand_all_exist"
        )
        assert result[0][0] == 20

        # Get IDs from first run
        first_run_ids = {
            row[1]: row[0]
            for row in materialization_handler.adapter.execute_query(
                "SELECT brand_id, brand_name FROM test_schema.dim_brand_all_exist ORDER BY brand_id"
            )
        }

        # Second run - all records already exist, should not add duplicates
        materialization_handler.materialize(
            table_name="test_schema.dim_brand_all_exist",
            sql_query=sql,
            materialization="incremental",
            metadata=dim_brand_metadata,
        )

        # Verify still 20 records (no duplicates)
        result = materialization_handler.adapter.execute_query(
            "SELECT COUNT(*) FROM test_schema.dim_brand_all_exist"
        )
        assert result[0][0] == 20

        # Verify IDs remain stable
        second_run_ids = {
            row[1]: row[0]
            for row in materialization_handler.adapter.execute_query(
                "SELECT brand_id, brand_name FROM test_schema.dim_brand_all_exist ORDER BY brand_id"
            )
        }
        assert first_run_ids == second_run_ids, "IDs should remain stable when no new records"

    def test_multiple_sequential_incremental_runs(
        self, materialization_handler, source_table, dim_brand_metadata, state_manager
    ):
        """Test multiple sequential incremental runs maintain ID stability."""
        sql = """
        SELECT DISTINCT brand AS brand_name
        FROM test_schema.national_articles
        WHERE brand IS NOT NULL
        """

        # First run
        materialization_handler.materialize(
            table_name="test_schema.dim_brand_sequential",
            sql_query=sql,
            materialization="incremental",
            metadata=dim_brand_metadata,
        )
        self._save_model_state(
            state_manager, "test_schema.dim_brand_sequential", sql, dim_brand_metadata
        )

        # Get IDs from first run
        first_run_ids = {
            row[1]: row[0]
            for row in materialization_handler.adapter.execute_query(
                "SELECT brand_id, brand_name FROM test_schema.dim_brand_sequential ORDER BY brand_id"
            )
        }

        # Second run
        materialization_handler.materialize(
            table_name="test_schema.dim_brand_sequential",
            sql_query=sql,
            materialization="incremental",
            metadata=dim_brand_metadata,
        )

        # Third run
        materialization_handler.materialize(
            table_name="test_schema.dim_brand_sequential",
            sql_query=sql,
            materialization="incremental",
            metadata=dim_brand_metadata,
        )

        # Verify still 20 records
        result = materialization_handler.adapter.execute_query(
            "SELECT COUNT(*) FROM test_schema.dim_brand_sequential"
        )
        assert result[0][0] == 20

        # Verify IDs remain stable across multiple runs
        third_run_ids = {
            row[1]: row[0]
            for row in materialization_handler.adapter.execute_query(
                "SELECT brand_id, brand_name FROM test_schema.dim_brand_sequential ORDER BY brand_id"
            )
        }
        assert first_run_ids == third_run_ids, "IDs should remain stable across multiple runs"
