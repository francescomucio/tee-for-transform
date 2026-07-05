"""
Default test injection based on semantic table metadata.

This module generates additional metadata (tests) for models at runtime
without mutating the input metadata dict.
"""

from typing import Any, cast

from t4t.parser.shared.dimension_registry import (
    build_dimension_registry_from_models,
    parse_dimension_field,
    resolve_dimension_target_table,
    resolve_target_pk_column,
)


def _infer_table_type_from_name(table_name: str) -> str | None:
    """Infer table semantic role from the model name prefix."""
    short = table_name.split(".")[-1].lower()
    if short.startswith("dim_"):
        return "dim"
    if short.startswith(("fct_", "fact_")):
        return "fact"
    if short.startswith("lkp_"):
        return "lookup"
    return None


def _resolve_table_type(table_name: str, metadata: dict[str, Any]) -> str | None:
    explicit = metadata.get("table_type")
    if explicit == "dimension":
        return "dim"
    if explicit in ("fact", "dim", "lookup"):
        return cast(str, explicit)
    return _infer_table_type_from_name(table_name)


def _is_pk_candidate(col_name: str) -> bool:
    """
    Heuristic for identifying potential PK columns on flat dimensions/lookups.

    Intentionally conservative: dim tables often have multiple *_id columns due to
    denormalized attributes (e.g., region_id). The rule for inference is strict:
    default PK is injected only when exactly one candidate exists.
    """
    n = col_name.lower()
    return (
        n in {"id", "pk", "surrogate_key"}
        or n.endswith("_sk")
        or n.endswith("_id")
        or n.endswith("_key")
    )


def _heuristic_pk_from_logical(logical: str) -> str:
    """Fallback PK column guess when parsed_models is not available."""
    dim = logical.strip().lower()
    if dim.startswith("dim_"):
        dim = dim[len("dim_") :]
    singular = dim[:-1] if dim.endswith("s") and len(dim) > 1 else dim
    pk_col_candidates: list[str] = []
    for stem in [dim, singular]:
        for suffix in ["_id", "_sk", "_key"]:
            cand = f"{stem}{suffix}"
            if cand not in pk_col_candidates:
                pk_col_candidates.append(cand)
    pk_col_candidates.extend(["id", "pk"])
    return next((c for c in pk_col_candidates if c), "id")


def _resolve_dimension_table_and_pk(
    fact_table_name: str,
    dimension_ref: str,
    fact_column: str,
    dimension_registry: dict[str, str] | None,
    parsed_models: dict[str, Any] | None,
) -> tuple[str, str] | None:
    """
    Resolve (dimension table, pk column) from simplified dimension metadata.

    Uses dimension_registry and optional parsed_models for PK resolution; falls
    back to name heuristics when models are not provided.
    """
    if not dimension_ref.strip():
        return None
    try:
        logical, _lvl = parse_dimension_field(dimension_ref)
    except ValueError:
        return None

    reg = dimension_registry or {}
    model_ids = set(parsed_models.keys()) if isinstance(parsed_models, dict) else None
    dim_table = resolve_dimension_target_table(fact_table_name, dimension_ref, reg, model_ids)

    if isinstance(parsed_models, dict):
        model = parsed_models.get(dim_table)
        if isinstance(model, dict):
            meta = model.get("model_metadata", {}).get("metadata", {}) or {}
            if not isinstance(meta, dict):
                meta = {}
            schema = meta.get("schema")
            schema_list = schema if isinstance(schema, list) else []
            pk = resolve_target_pk_column(meta, fact_column, schema_list)
            if pk:
                return dim_table, pk

    return dim_table, _heuristic_pk_from_logical(logical)


def _extract_test_names(column_tests: list[Any] | None) -> set[str]:
    names: set[str] = set()
    if not column_tests:
        return names
    for t in column_tests:
        if isinstance(t, str):
            names.add(t)
        elif isinstance(t, dict):
            # Supports {"name": "..."} / {"test": "..."} shapes.
            v = t.get("name") or t.get("test")
            if isinstance(v, str):
                names.add(v)
    return names


def _ensure_column_test(schema: list[dict[str, Any]], column_name: str, test_name: str) -> None:
    """Add a column-level test if it is not already present."""
    for col in schema:
        if col.get("name") != column_name:
            continue
        tests = col.get("tests")
        if not tests:
            col["tests"] = [test_name]
            return
        names = _extract_test_names(cast(list[Any], tests))
        if test_name in names:
            return
        tests.append(test_name)
        return


def _ensure_model_test(tests: list[Any], test_def: dict[str, Any]) -> None:
    """Add a model-level test definition if not present (by name)."""
    test_name = test_def.get("name") or test_def.get("test")
    if not isinstance(test_name, str):
        return
    for existing in tests:
        if isinstance(existing, str) and existing == test_name:
            return
        if (
            isinstance(existing, dict)
            and (existing.get("name") or existing.get("test")) == test_name
        ):
            return
    tests.append(test_def)


def _disabled_default_tests(metadata: dict[str, Any]) -> tuple[bool, set[str]]:
    """
    Returns (disable_all, disabled_names_set).

    disable_default_tests can be:
    - True: disable all default tests
    - [..]: disable by test name
    - absent: enable defaults
    """
    disabled = metadata.get("disable_default_tests")
    if disabled is True:
        return True, set()
    if isinstance(disabled, list):
        return False, {str(x) for x in disabled}
    return False, set()


def _level_attribute_cols(level: dict[str, Any], pk_col: str) -> list[str]:
    """
    Build the attribute columns list for a hierarchy level.

    Includes the level label column plus any explicitly added columns,
    excluding pk_col if it appears.
    """
    cols: list[str] = []
    # The level's label/name column is always part of the attribute tuple.
    label_col = level.get("column")
    if isinstance(label_col, str) and label_col.strip():
        cols.append(label_col)

    extra_cols = level.get("columns") or []
    if isinstance(extra_cols, list):
        for c in extra_cols:
            if isinstance(c, str) and c.strip():
                cols.append(c)

    # Exclude the PK column itself if it appears among attributes.
    return [c for c in cols if c != pk_col]


def inject_default_tests(
    table_name: str,
    metadata: dict[str, Any],
    *,
    dimension_registry: dict[str, str] | None = None,
    parsed_models: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """
    Return a copy of metadata with auto-generated tests merged in.

    When ``dimension_registry`` is omitted but ``parsed_models`` is provided, the
    registry is built automatically from dimension models (same as the parser).

    Returns:
      (metadata_copy, warnings)
    """
    disable_all, disabled_names = _disabled_default_tests(metadata)
    if disable_all:
        return dict(metadata), []

    table_type = _resolve_table_type(table_name, metadata)
    effective_dim_registry = dimension_registry
    if effective_dim_registry is None and isinstance(parsed_models, dict) and parsed_models:
        try:
            effective_dim_registry = build_dimension_registry_from_models(parsed_models)
        except ValueError:
            effective_dim_registry = {}

    schema_in = metadata.get("schema") or []
    schema: list[dict[str, Any]] = []
    for c in schema_in:
        if not isinstance(c, dict):
            continue
        col_copy = dict(c)
        # Avoid mutating the caller's lists when we append default tests.
        if isinstance(col_copy.get("tests"), list):
            col_copy["tests"] = list(col_copy["tests"])
        if isinstance(col_copy.get("fk_to"), dict):
            col_copy["fk_to"] = dict(col_copy["fk_to"])
        schema.append(col_copy)
    model_tests: list[Any] = list(metadata.get("tests") or [])
    warnings: list[str] = []

    # DIM / LOOKUP defaults
    if table_type in ("dim", "lookup"):
        hierarchy = metadata.get("hierarchy")
        if hierarchy and isinstance(hierarchy, dict):
            levels = hierarchy.get("levels") or []
            if isinstance(levels, list):
                # Level-scoped PKs + model-level hierarchy tests
                for level in levels:
                    if not isinstance(level, dict):
                        continue
                    pk_col = level.get("primary_key")
                    if not isinstance(pk_col, str) or not pk_col.strip():
                        warnings.append(
                            f"{table_type} '{table_name}' hierarchy level missing primary_key"
                        )
                        continue

                    if "primary_key" not in disabled_names:
                        # Add PK test unless already implied by not_null+unique or primary_key exists.
                        # We detect existing constraints from the column's explicit tests list.
                        existing = next((c for c in schema if c.get("name") == pk_col), None)
                        if existing:
                            names = _extract_test_names(existing.get("tests"))
                            if "primary_key" not in names and not (
                                "not_null" in names and "unique" in names
                            ):
                                _ensure_column_test(schema, pk_col, "primary_key")

                    if "level_uniqueness" not in disabled_names:
                        attribute_cols = _level_attribute_cols(level, pk_col)
                        _ensure_model_test(
                            model_tests,
                            {
                                "name": "level_uniqueness",
                                "pk_col": pk_col,
                                "attribute_cols": attribute_cols,
                            },
                        )

                # Adjacent level mapping constraints
                for i in range(len(levels) - 1):
                    child_level = levels[i]
                    parent_level = levels[i + 1]
                    if not isinstance(child_level, dict) or not isinstance(parent_level, dict):
                        continue
                    child_pk = child_level.get("primary_key")
                    parent_pk = parent_level.get("primary_key")
                    if not isinstance(child_pk, str) or not isinstance(parent_pk, str):
                        continue
                    if "hierarchy_no_split" in disabled_names:
                        continue
                    _ensure_model_test(
                        model_tests,
                        {
                            "name": "hierarchy_no_split",
                            "child_col": child_pk,
                            "parent_col": parent_pk,
                        },
                    )
        else:
            # Flat dim: infer PK by exactly-one-match heuristic.
            pk_candidates = [
                c.get("name")
                for c in schema
                if isinstance(c.get("name"), str) and _is_pk_candidate(c["name"])
            ]
            pk_candidates = [n for n in pk_candidates if isinstance(n, str)]

            if len(pk_candidates) == 1:
                pk_col = pk_candidates[0]
                if "primary_key" not in disabled_names:
                    existing = next((c for c in schema if c.get("name") == pk_col), None)
                    if existing:
                        names = _extract_test_names(existing.get("tests"))
                        if "primary_key" not in names and not (
                            "not_null" in names and "unique" in names
                        ):
                            _ensure_column_test(schema, pk_col, "primary_key")
            else:
                warnings.append(
                    f"dim/lookup '{table_name}' has {len(pk_candidates)} primary key candidates; "
                    f"declare a single PK explicitly via column tests: ['primary_key'] "
                    f"(or disable defaults with disable_default_tests)."
                )

    # FACT defaults
    if table_type == "fact" and "schema" in metadata and isinstance(metadata["schema"], list):
        for col in schema:
            if not isinstance(col, dict):
                continue
            fk_to = col.get("fk_to")
            target_table = None
            target_col = None

            # Verbose mode.
            if isinstance(fk_to, dict):
                tt = fk_to.get("table")
                tc = fk_to.get("column")
                if isinstance(tt, str) and isinstance(tc, str):
                    target_table = tt
                    target_col = tc
            # Simplified mode.
            if (not target_table) and isinstance(col.get("dimension"), str):
                fc = col.get("name")
                fact_col = fc.strip() if isinstance(fc, str) else ""
                resolved = _resolve_dimension_table_and_pk(
                    table_name,
                    col["dimension"],
                    fact_col,
                    effective_dim_registry,
                    parsed_models,
                )
                if resolved:
                    target_table, target_col = resolved

            if not isinstance(target_table, str) or not isinstance(target_col, str):
                continue

            if "relationships" in disabled_names or "relationships" in _extract_test_names(
                col.get("tests")
            ):
                continue

            # Replace the placeholder approach above with a correct param-aware test insert:
            col_tests = col.get("tests") or []
            if not isinstance(col_tests, list):
                col_tests = []
            # Avoid duplicates by name.
            existing_names = _extract_test_names(col_tests)
            if "relationships" not in existing_names:
                col_tests.append({"name": "relationships", "to": target_table, "field": target_col})
            col["tests"] = col_tests

    # Preserve any other metadata keys
    out = dict(metadata)
    out["schema"] = schema
    out["tests"] = model_tests
    return out, warnings
