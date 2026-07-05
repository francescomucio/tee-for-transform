# Engine API

Execution engine classes, connection handling, materialization, and configuration loading.

## Status

Narrative API reference pages are not written yet. Use the user guides and source modules below.

## Where to look in code

| Area | Python package / module |
|------|-------------------------|
| High-level run orchestration | `t4t/engine/execution_engine.py` (`ExecutionEngine`) |
| Model execution (adapter-aware) | `t4t/engine/executor.py` (`ModelExecutor`), `t4t/engine/executors/model_executor.py` |
| Function deployment / execution | `t4t/engine/executors/function_executor.py` |
| DB connections | `t4t/engine/connection_manager.py` |
| Config from `project.toml` / env | `t4t/engine/config.py` (`DatabaseConfigManager`, `load_database_config`) |
| Incremental state | `t4t/engine/incremental_state.py`, `t4t/engine/state_manager.py`, `t4t/engine/model_state.py` |
| Materialization & schema changes | `t4t/engine/materialization/` |
| Seeds | `t4t/engine/seeds.py` |
| Project-level tags from TOML | `t4t/engine/metadata/metadata_extractor.py` |

## User-facing docs

- [Execution engine](../../user-guide/execution-engine.md)
- [CLI reference](../../user-guide/cli-reference.md)
- [Incremental materialization](../../user-guide/incremental-materialization.md)
