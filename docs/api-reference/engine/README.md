# Engine API

Execution engine classes, connection handling, materialization, and configuration loading.

## Status

Narrative API reference pages are not written yet. Use the user guides and source modules below.

## Where to look in code

| Area | Python package / module |
|------|-------------------------|
| High-level run orchestration | `tee/engine/execution_engine.py` (`ExecutionEngine`) |
| Model execution (adapter-aware) | `tee/engine/executor.py` (`ModelExecutor`), `tee/engine/executors/model_executor.py` |
| Function deployment / execution | `tee/engine/executors/function_executor.py` |
| DB connections | `tee/engine/connection_manager.py` |
| Config from `project.toml` / env | `tee/engine/config.py` (`DatabaseConfigManager`, `load_database_config`) |
| Incremental state | `tee/engine/incremental_state.py`, `tee/engine/state_manager.py`, `tee/engine/model_state.py` |
| Materialization & schema changes | `tee/engine/materialization/` |
| Seeds | `tee/engine/seeds.py` |
| Project-level tags from TOML | `tee/engine/metadata/metadata_extractor.py` |

## User-facing docs

- [Execution engine](../../user-guide/execution-engine.md)
- [CLI reference](../../user-guide/cli-reference.md)
- [Incremental materialization](../../user-guide/incremental-materialization.md)
