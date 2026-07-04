"""
Unit tests for incremental state manager.
"""

from pathlib import Path

from t4t.engine.incremental_state import IncrementalState, IncrementalStateManager


def test_state_manager_round_trip_and_list_delete(tmp_path: Path) -> None:
    db_path = tmp_path / "state.db"
    manager = IncrementalStateManager(str(db_path))

    initial = IncrementalState(
        model_name="fct_sales",
        strategy="merge",
        last_processed_value="2024-01-01",
        sqlglot_hash="sql-hash-1",
        config_hash="cfg-hash-1",
    )
    manager.save_state(initial)

    loaded = manager.get_state("fct_sales")
    assert loaded is not None
    assert loaded.model_name == "fct_sales"
    assert loaded.strategy == "merge"
    assert loaded.last_processed_value == "2024-01-01"
    assert loaded.created_at is not None
    assert loaded.updated_at is not None

    manager.update_processed_value("fct_sales", "2024-01-02")
    loaded_after_update = manager.get_state("fct_sales")
    assert loaded_after_update is not None
    assert loaded_after_update.last_processed_value == "2024-01-02"
    assert loaded_after_update.last_run_timestamp is not None

    assert manager.list_models() == ["fct_sales"]
    manager.delete_state("fct_sales")
    assert manager.get_state("fct_sales") is None
    assert manager.list_models() == []
    manager.close()


def test_state_manager_incremental_decision_paths(tmp_path: Path) -> None:
    manager = IncrementalStateManager(str(tmp_path / "state.db"))
    model_name = "fct_returns"

    # No state -> full load
    assert manager.should_run_incremental(model_name, "sql1", "cfg1") is False
    assert manager.has_model_changed(model_name, "sql1", "cfg1") is True

    manager.save_state(
        IncrementalState(
            model_name=model_name,
            strategy="append",
            last_processed_value="10",
            sqlglot_hash="sql1",
            config_hash="cfg1",
        )
    )

    # Same hashes + processed value -> incremental
    assert manager.has_model_changed(model_name, "sql1", "cfg1") is False
    assert manager.should_run_incremental(model_name, "sql1", "cfg1") is True

    # SQL hash changed -> full load
    assert manager.has_model_changed(model_name, "sql2", "cfg1") is True
    assert manager.should_run_incremental(model_name, "sql2", "cfg1") is False

    # No processed value -> full load
    manager.save_state(
        IncrementalState(
            model_name=model_name,
            strategy="append",
            last_processed_value=None,
            sqlglot_hash="sql1",
            config_hash="cfg1",
        )
    )
    assert manager.should_run_incremental(model_name, "sql1", "cfg1") is False
    manager.close()


def test_hash_helpers_are_stable() -> None:
    manager = IncrementalStateManager(":memory:")
    assert manager.compute_sql_hash("select 1") == manager.compute_sql_hash("select 1")
    assert manager.compute_sql_hash("select 1") != manager.compute_sql_hash("select 2")

    cfg_a = {"b": 2, "a": 1}
    cfg_b = {"a": 1, "b": 2}
    cfg_c = {"a": 1, "b": 3}
    assert manager.compute_config_hash(cfg_a) == manager.compute_config_hash(cfg_b)
    assert manager.compute_config_hash(cfg_a) != manager.compute_config_hash(cfg_c)
    manager.close()
