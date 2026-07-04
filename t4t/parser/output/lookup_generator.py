"""
Lookup table generator.

Creates `lkp_<level>.sql` + `lkp_<level>.py` for each level of a hierarchical dimension.
"""

from __future__ import annotations

import pprint
import re
import shutil
from pathlib import Path
from typing import Any

from t4t.cli.utils import load_project_config
from t4t.parser.core.project_parser import ProjectParser


def _safe_level_name(level_name: str) -> str:
    """Convert a human-readable level name into a safe identifier."""
    s = level_name.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "level"


def _lookup_description(
    dim_model_name: str,
    level_name: str,
    parent_level_name: str | None = None,
    role_playing: bool = False,
) -> str:
    """Generate a default table-level description for a lookup model."""
    base = f"Lookup table for the '{level_name}' level derived from `{dim_model_name}`."
    if role_playing:
        base = (
            f"{base} This is a role-playing lookup generated to disambiguate a shared"
            " business level name used across multiple dimensions."
        )
    if parent_level_name:
        return f"{base} Links to parent lookup level '{parent_level_name}'."
    return base


def _selected_lookup_columns(
    dim_schema: list[dict[str, Any]], level_def: dict[str, Any]
) -> list[str]:
    pk = level_def.get("primary_key")
    label_col = level_def.get("column")
    extra_cols = level_def.get("columns") or []
    if not isinstance(extra_cols, list):
        extra_cols = []

    selected: list[str] = []
    for c in [pk, label_col, *extra_cols]:
        if isinstance(c, str) and c.strip() and c not in selected:
            selected.append(c)
    # Ensure they exist in schema when possible.
    schema_names = {c.get("name") for c in dim_schema if isinstance(c, dict)}
    if schema_names:
        selected = [c for c in selected if c in schema_names]
    return selected


def _level_number(level: dict[str, Any]) -> int:
    val = level.get("level_number")
    if isinstance(val, int):
        return val
    if isinstance(val, str):
        try:
            return int(val)
        except ValueError:
            return 0
    return 0


def _clean_generated_dirs(project_path: Path) -> None:
    """Remove all models/**/_generated folders before regeneration."""
    models_root = project_path / "models"
    if not models_root.exists():
        return
    for gen_dir in models_root.rglob("_generated"):
        if gen_dir.is_dir():
            shutil.rmtree(gen_dir, ignore_errors=True)


def _dimension_name_from_model(model_name: str) -> str:
    short_name = model_name.split(".")[-1].lower()
    if short_name.startswith("dim_"):
        return short_name[4:] or short_name
    return short_name


def generate_lookups(
    project_path: Path,
    vars_dict: dict[str, Any] | None = None,
    auto_resolve_level_conflicts: bool = False,
) -> list[str]:
    """
    Generate lookup tables for each hierarchical dimension level.

    Returns:
        List of created file paths (sql/py pairs flattened).
    """
    project_path = project_path.resolve()
    _clean_generated_dirs(project_path)
    config = load_project_config(str(project_path), vars_dict)

    parser = ProjectParser(
        project_folder=str(project_path),
        connection=config["connection"],
        variables=config.get("vars", {}),
        project_config=config,
    )
    parsed_models = parser.collect_models()

    created_files: list[str] = []

    lookup_candidates: list[dict[str, Any]] = []

    for model_name, model in parsed_models.items():
        metadata = model.get("model_metadata", {}).get("metadata", {}) or {}
        explicit_type = metadata.get("table_type")
        short_name = model_name.split(".")[-1].lower()
        is_dimension = explicit_type == "dim" or short_name.startswith("dim_")
        if not is_dimension:
            continue
        hierarchy = metadata.get("hierarchy")
        if not isinstance(hierarchy, dict):
            continue
        levels = hierarchy.get("levels")
        if not isinstance(levels, list) or not levels:
            continue

        dim_schema = metadata.get("schema") or []
        if not isinstance(dim_schema, list):
            dim_schema = []

        # For SQL models, file_path points to the sibling metadata file (.py).
        file_path = model.get("model_metadata", {}).get("file_path")
        if not isinstance(file_path, str) or not file_path:
            continue
        dim_dir = Path(file_path).resolve().parent

        schema_name = model_name.split(".")[0] if "." in model_name else ""
        ordered_levels = [lvl for lvl in levels if isinstance(lvl, dict)]
        ordered_levels.sort(key=_level_number)
        terminal_generated_idx = len(ordered_levels) - 2

        for idx, level in enumerate(ordered_levels):
            if not isinstance(level, dict):
                continue
            # The leaf hierarchy level is at the same grain as the source dimension,
            # so we do not generate a lookup for it.
            if idx == len(ordered_levels) - 1:
                continue
            level_name = level.get("name")
            pk_col = level.get("primary_key")
            label_col = level.get("column")
            if not isinstance(level_name, str) or not level_name.strip():
                continue
            if not isinstance(pk_col, str) or not pk_col.strip():
                continue
            if not isinstance(label_col, str) or not label_col.strip():
                continue

            lookup_candidates.append(
                {
                    "model_name": model_name,
                    "schema_name": schema_name,
                    "dim_dir": dim_dir,
                    "dim_name_safe": _safe_level_name(_dimension_name_from_model(model_name)),
                    "level_idx": idx,
                    "level": level,
                    "ordered_levels": ordered_levels,
                    "terminal_generated_idx": terminal_generated_idx,
                    "level_name": level_name,
                    "pk_col": pk_col,
                    "label_col": label_col,
                    "safe_level": _safe_level_name(level_name),
                    "resolved_safe_level": _safe_level_name(level_name),
                    "resolved_level_name": level_name,
                    "dim_schema": dim_schema,
                    "lookups_as_table": metadata.get("lookups_as_table", True),
                    "is_role_playing": False,
                }
            )

    by_safe_level: dict[str, list[int]] = {}
    for i, candidate in enumerate(lookup_candidates):
        by_safe_level.setdefault(candidate["safe_level"], []).append(i)

    conflicting = {k: v for k, v in by_safe_level.items() if len(v) > 1}
    if conflicting and not auto_resolve_level_conflicts:
        conflicts_msg = ", ".join(sorted(conflicting.keys()))
        raise ValueError(
            "Lookup level name conflict detected across dimensions: "
            f"{conflicts_msg}. Use unique hierarchy level names or set "
            "auto_resolve_level_conflicts=True (CLI: --auto-resolve-level-conflicts) "
            "to automatically rename conflicting levels as <dimension>_<level>."
        )

    if conflicting and auto_resolve_level_conflicts:
        used_names = {c["resolved_safe_level"] for c in lookup_candidates}
        for conflict_safe, indices in conflicting.items():
            for idx in indices:
                candidate = lookup_candidates[idx]
                base_name = f"{candidate['dim_name_safe']}_{conflict_safe}"
                resolved = base_name
                suffix = 2
                while resolved in used_names and resolved != candidate["resolved_safe_level"]:
                    resolved = f"{base_name}_{suffix}"
                    suffix += 1
                candidate["resolved_safe_level"] = resolved
                candidate["resolved_level_name"] = resolved
                candidate["is_role_playing"] = True
                used_names.add(resolved)

    candidate_by_model_and_level: dict[tuple[str, int], dict[str, Any]] = {
        (c["model_name"], c["level_idx"]): c for c in lookup_candidates
    }

    for candidate in lookup_candidates:
        model_name = candidate["model_name"]
        schema_name = candidate["schema_name"]
        dim_dir = candidate["dim_dir"]
        ordered_levels = candidate["ordered_levels"]
        level = candidate["level"]
        level_name = candidate["level_name"]
        resolved_level_name = candidate["resolved_level_name"]
        pk_col = candidate["pk_col"]
        label_col = candidate["label_col"]
        safe_level = candidate["resolved_safe_level"]
        idx = candidate["level_idx"]
        terminal_generated_idx = candidate["terminal_generated_idx"]
        dim_schema = candidate["dim_schema"]
        lookups_as_table = candidate.get("lookups_as_table", True)
        is_role_playing = bool(candidate.get("is_role_playing"))

        generated_dir = dim_dir / "_generated"
        generated_dir.mkdir(parents=True, exist_ok=True)
        out_sql_path = generated_dir / f"lkp_{safe_level}.sql"
        out_py_path = generated_dir / f"lkp_{safe_level}.py"

        selected_cols = _selected_lookup_columns(dim_schema, level)
        parent_level = ordered_levels[idx - 1] if idx > 0 else None
        parent_pk = parent_level.get("primary_key") if isinstance(parent_level, dict) else None
        parent_level_name = parent_level.get("name") if isinstance(parent_level, dict) else None
        parent_candidate = (
            candidate_by_model_and_level.get((model_name, idx - 1)) if idx > 0 else None
        )
        parent_safe = (
            parent_candidate.get("resolved_safe_level")
            if isinstance(parent_candidate, dict)
            else (
                _safe_level_name(parent_level_name) if isinstance(parent_level_name, str) else None
            )
        )

        # For child levels, include parent PK to support snowflake parent->child links.
        if isinstance(parent_pk, str) and parent_pk.strip() and parent_pk not in selected_cols:
            selected_cols.insert(0, parent_pk)

        # Generate SQL: single SELECT DISTINCT from the full dimension table.
        col_select = ",\n    ".join(selected_cols)
        sql = f"""select distinct
    {col_select}
from {model_name}
"""

        # Generate lookup metadata.
        col_map = {c.get("name"): c for c in dim_schema if isinstance(c, dict) and c.get("name")}
        lookup_schema = []
        for c in selected_cols:
            col_def = col_map.get(c) or {}
            col_meta: dict[str, Any] = {
                "name": c,
                "datatype": col_def.get("datatype", "string"),
                "description": col_def.get("description"),
            }
            # Link child lookups to their parent lookup table.
            if (
                isinstance(parent_pk, str)
                and c == parent_pk
                and isinstance(parent_safe, str)
                and parent_safe
            ):
                parent_table = (
                    f"{schema_name}.lkp_{parent_safe}" if schema_name else f"lkp_{parent_safe}"
                )
                col_meta["fk_to"] = {"table": parent_table, "column": parent_pk}
                if not col_meta["description"]:
                    col_meta["description"] = (
                        f"Foreign key to parent lookup `{parent_table}` ({parent_pk})."
                    )
            # Link lookup PK to the associated source dimension for the
            # terminal generated lookup level (leaf level is not generated).
            elif c == pk_col and idx == terminal_generated_idx:
                col_meta["fk_to"] = {"table": model_name, "column": pk_col}
                if not col_meta["description"]:
                    col_meta["description"] = (
                        f"Lookup primary key for level '{level_name}' from `{model_name}`."
                    )
            elif not col_meta["description"]:
                col_meta["description"] = f"Lookup attribute column '{c}' for level '{level_name}'."

            lookup_schema.append(col_meta)

        lookup_metadata: dict[str, Any] = {
            "materialization": "table" if lookups_as_table is not False else "view",
            "table_type": "lookup",
            "data_model": True,
            "description": _lookup_description(
                model_name,
                resolved_level_name,
                parent_level_name
                if isinstance(parent_level_name, str) and parent_level_name.strip()
                else None,
                role_playing=is_role_playing,
            ),
            "tests": ["row_count_gt_0"],
            "hierarchy": {
                "type": "Single-Level Lookup",
                "levels": [
                    {
                        "level_number": 1,
                        "name": resolved_level_name,
                        "column": label_col,
                        "primary_key": pk_col,
                        "columns": level.get("columns") or [],
                    }
                ],
            },
            "schema": lookup_schema,
        }

        py = (
            "from t4t.typing.metadata import ModelMetadata\n\n"
            f"metadata: ModelMetadata = {pprint.pformat(lookup_metadata, width=120)}\n"
        )

        out_sql_path.write_text(sql, encoding="utf-8")
        out_py_path.write_text(py, encoding="utf-8")
        created_files.extend([str(out_sql_path), str(out_py_path)])

    return created_files
