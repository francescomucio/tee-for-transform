## Chef Bianco's Review — Issue #27: First-Class Environments

*Buongiorno.* I've tasted every line. The pasta is *al dente*, but there are a few burnt edges that need trimming before this goes to the pass.

---

### ✅ What's Done Well

1. **Clean separation of concerns** — `DatabaseConfigManager` in `config.py` vs `load_project_config` in `utils.py` is the right split. The manager handles raw TOML/env resolution; the utility handles project-level config merging. Good.

2. **Legacy compatibility** — `[connection]` still works when no `--env` is passed. The tests prove it. This is *critical* for a smooth migration. *Bravissimo.*

3. **Error messages with available environments** — When a user types `--env=staging` and only `dev,prod` exist, they get told what's available. This is the kind of hospitality I expect in my kitchen.

4. **CLI vars override env vars** — `test_environment_variables_cli_wins` proves the precedence chain is correct. CLI > env-level > defaults. Correct.

5. **15 tests, all green** — Coverage on the new code is excellent. The fixture-based approach with `tempfile.TemporaryDirectory` is clean and hermetic.

---

### 🚩 Issues to Fix

#### 1. `t4t/cli/main.py:108-133` — `--env` CLI option is NOT wired to any command

The `CommandContext` class accepts `env`, and `load_project_config` accepts `env_name`, but **none of the CLI commands expose `--env` to the user**. The `run`, `build`, `test`, `debug`, `seed`, `compile`, `docs`, and `generate-lookups` commands all create `CommandContext(...)` without passing `env`.

This means the entire feature is *inaccessible from the CLI*. A user cannot do `t4t run . --env=prod` — the option simply doesn't exist.

**Fix:** Add `--env` as a `typer.Option` to every command that creates a `CommandContext`, and pass it through. Example for `run`:

```python
def cmd_run(
    project_folder: str,
    vars: str | None = None,
    verbose: bool = False,
    select: list[str] | None = None,
    exclude: list[str] | None = None,
    retry: bool = False,
    auto_resolve_level_conflicts: bool = True,
    env: str | None = None,  # <-- ADD THIS
) -> None:
    ctx = CommandContext(
        project_folder=project_folder,
        vars=vars,
        verbose=verbose,
        select=select,
        exclude=exclude,
        env=env,  # <-- PASS IT
    )
```

And in `main.py`, add the option definition and pass it through each command call.

#### 2. `t4t/engine/config.py:84-114` — `_load_toml_config` returns early when `env_name` is set, skipping legacy fallback

When `env_name` is provided, the method returns immediately after loading the environment section (line 114). This means:
- It **never checks** `[tool.t4t.database]`, `[tool.t4t.databases]`, or legacy `[connection]` as fallbacks.
- If an environment section has an incomplete connection (e.g., missing `type`), the error message will be "No database configuration found" rather than something more helpful like "Environment 'dev' connection is missing required field 'type'".

**Fix:** Either validate the environment connection fields before returning, or merge the environment connection on top of a base config loaded from legacy sections. The current design assumes environments are fully self-contained, which is fine — but then the validation should be more explicit.

#### 3. `t4t/engine/config.py:108-109` — `_env_variables` key is stored but never used

The `_env_variables` key is written to the config dict (line 109) but is never read by `_create_adapter_config` or any downstream consumer. The `AdapterConfig` dataclass has no `variables` field. This is dead data.

**Fix:** Either:
- Remove `_env_variables` entirely (it's handled by `load_project_config` in `utils.py`), or
- Add a `variables` field to `AdapterConfig` and populate it.

#### 4. `t4t/engine/config.py:112` — `_protected` key is stored but never used

Same issue as `_env_variables`. The `protected` flag from `[environments.prod]` is stored in the config dict but never checked anywhere. No command refuses to run against a protected environment.

**Fix:** Either implement the protection (e.g., require `--force` to run against a protected env) or remove it for now. Half-implemented safety features are worse than none — they give a false sense of security.

#### 5. `t4t/cli/utils.py:70-98` — `load_project_config` duplicates environment resolution logic from `DatabaseConfigManager`

The environment lookup logic (checking `environments` dict, building error messages, extracting connection/variables) is duplicated almost verbatim between `config.py:84-114` and `utils.py:70-98`. This is a maintenance risk — if the TOML structure changes, both must be updated.

**Fix:** Extract the common logic into a shared helper, e.g.:

```python
def _resolve_environment(
    data: dict, env_name: str
) -> tuple[dict, dict, bool]:
    ...
```

Then call it from both `DatabaseConfigManager._load_toml_config` and `load_project_config`.

#### 6. `t4t/cli/context.py:44` — `self.env` is stored but never used after construction

The `env` parameter is stored as `self.env` but is never referenced again in the class. It's only used to pass to `load_project_config`. Either remove it or document it as a future-use field.

#### 7. `tests/test_environments.py:21` — Fixture uses `default_environment` key that is never read by the code

The fixture `project_toml_with_environments` includes `default_environment = "dev"` (line 21), but **no code reads this key**. If the intent is to support a `default_environment` setting that auto-selects when no `--env` is given, it's not implemented.

**Fix:** Either implement `default_environment` support in `load_project_config` and `DatabaseConfigManager`, or remove it from the fixture to avoid confusion.

---

### 📋 Summary

| # | Severity | File | Issue |
|---|----------|------|-------|
| 1 | 🔴 **HIGH** | `t4t/cli/main.py` | `--env` option not wired to any CLI command — feature is inaccessible |
| 2 | 🟡 **MEDIUM** | `t4t/engine/config.py:84-114` | Early return skips legacy fallback; weak validation on env connections |
| 3 | 🟢 **LOW** | `t4t/engine/config.py:109` | `_env_variables` stored but never consumed |
| 4 | 🟢 **LOW** | `t4t/engine/config.py:112` | `_protected` stored but never enforced |
| 5 | 🟡 **MEDIUM** | `t4t/cli/utils.py:70-98` | Duplicated environment resolution logic |
| 6 | 🟢 **LOW** | `t4t/cli/context.py:44` | `self.env` stored but unused after construction |
| 7 | 🟢 **LOW** | `tests/test_environments.py:21` | `default_environment` in fixture but never implemented |

---

### Verdict

The **design is correct** — the `[environments.*]` TOML structure, the precedence chain, and the legacy compatibility are all well thought out. The tests are thorough and pass.

However, **issue #1 is a blocker**: the feature cannot be used from the CLI. Fix that, address the duplication (issue #5), and decide what to do with the half-implemented `protected` flag (issue #4), and this will be ready to merge.

*La cucina è semplice, ma non è facile.* — The kitchen is simple, but it's not easy.

— Chef Bianco
