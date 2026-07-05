"""
Dimension shorthand resolution: auto-built registry + logical[.level] syntax.

The registry is derived from parsed models: ``table_type`` of ``dim`` / ``dimension``,
or a model short name starting with ``dim_``. Keys are lowercased logical names
(strip ``dim_`` when present) and ``{logical}.{level_slug}`` for each hierarchy
level name.
"""

from typing import Any, Mapping


def _model_metadata_dict(model: Any) -> dict[str, Any]:
    if not isinstance(model, dict):
        return {}
    mm = model.get("model_metadata", {})
    if not isinstance(mm, dict):
        return {}
    meta = mm.get("metadata", {})
    return meta if isinstance(meta, dict) else {}


def is_dimension_model(model_name: str, metadata: dict[str, Any]) -> bool:
    """True when metadata or naming marks the model as a dimension table."""
    tt = metadata.get("table_type")
    if tt in ("dim", "dimension"):
        return True
    short = model_name.split(".")[-1].lower()
    return short.startswith("dim_")


def logical_base_key(model_name: str) -> str:
    """Stable logical key: ``dim_x`` -> ``x``, else unqualified table name lowercased."""
    short = model_name.split(".")[-1].lower()
    if short.startswith("dim_"):
        return short[4:]
    return short


def hierarchy_level_slugs(metadata: dict[str, Any]) -> list[str]:
    """Ordered unique slugs from hierarchy level ``name`` fields."""
    hierarchy = metadata.get("hierarchy")
    levels = hierarchy.get("levels") if isinstance(hierarchy, dict) else None
    if not isinstance(levels, list):
        return []
    seen: list[str] = []
    for lvl in levels:
        if not isinstance(lvl, dict):
            continue
        name = lvl.get("name")
        if isinstance(name, str) and name.strip():
            slug = name.strip().lower().replace(" ", "_")
            if slug not in seen:
                seen.append(slug)
    return seen


def _registry_put(registry: dict[str, str], key: str, fq_table: str) -> None:
    key_l = key.strip().lower()
    existing = registry.get(key_l)
    if existing is not None and existing != fq_table:
        raise ValueError(
            f"Ambiguous dimension registry key {key_l!r}: maps to both {existing!r} and {fq_table!r}"
        )
    registry[key_l] = fq_table


def _normalize_logical_part(part: str) -> str:
    p = part.strip().lower()
    if p.startswith("dim_"):
        p = p[4:]
    return p


def build_dimension_registry_from_models(parsed_models: dict[str, Any]) -> dict[str, str]:
    """
    Build logical name → fully qualified dimension table from parsed models.

    Includes:
    - ``{logical}`` for each dimension model
    - ``{logical}.{level_slug}`` for each hierarchy level name on that model
    - **Override:** models with ``conformed_dimension: {logical, level}`` register
      ``{logical}.{level}`` → this table (e.g. ``dim_month`` as the physical table for
      ``date.month`` when it belongs to the ``date`` conformed dimension)

    Raises:
        ValueError: duplicate keys pointing at different tables (strict pass only)
    """
    registry: dict[str, str] = {}
    for fq_name in sorted(parsed_models.keys()):
        model = parsed_models[fq_name]
        meta = _model_metadata_dict(model)
        if not is_dimension_model(fq_name, meta):
            continue
        logical = logical_base_key(fq_name)
        _registry_put(registry, logical, fq_name)
        for slug in hierarchy_level_slugs(meta):
            _registry_put(registry, f"{logical}.{slug}", fq_name)

    for fq_name in sorted(parsed_models.keys()):
        model = parsed_models[fq_name]
        meta = _model_metadata_dict(model)
        if not is_dimension_model(fq_name, meta):
            continue
        cd = meta.get("conformed_dimension")
        if not isinstance(cd, dict):
            continue
        log_raw = cd.get("logical")
        lev_raw = cd.get("level")
        if not isinstance(log_raw, str) or not isinstance(lev_raw, str):
            continue
        parent_logical = _normalize_logical_part(log_raw)
        level_slug = lev_raw.strip().lower().replace(" ", "_")
        if not parent_logical or not level_slug:
            continue
        registry[f"{parent_logical}.{level_slug}"] = fq_name

    return registry


def parse_dimension_field(dim_ref: str) -> tuple[str, str | None]:
    """
    Parse ``dimension`` metadata into (logical_key, level_slug).

    - ``date`` -> (``date``, None)
    - ``date.month`` / ``date.Month`` -> (``date``, ``month``)
    Logical part strips a leading ``dim_`` prefix (case-insensitive).
    Level is lowercased; spaces become underscores.
    """
    s = dim_ref.strip()
    if not s:
        raise ValueError("empty dimension reference")
    if "." in s:
        left, right = s.split(".", 1)
        logical = _normalize_logical_part(left)
        level_part = right.strip()
        if not logical or not level_part:
            raise ValueError(f"invalid dimension reference: {dim_ref!r}")
        level_slug = level_part.lower().replace(" ", "_")
        return logical, level_slug
    return _normalize_logical_part(s), None


def registry_lookup_table(
    logical: str, level: str | None, registry: Mapping[str, str] | None
) -> tuple[str | None, str | None]:
    """
    Return (table, matched_key) from registry.

    When ``level`` is set, only the composite key ``logical.level`` is used.
    When ``level`` is None, only ``logical`` is used.
    """
    if not registry:
        return None, None
    if level:
        key = f"{logical}.{level}"
        hit = registry.get(key)
        if hit:
            return hit, key
        return None, None
    hit = registry.get(logical)
    if hit:
        return hit, logical
    return None, None


def resolve_dimension_target_table(
    fact_name: str,
    dim_ref: str,
    registry: Mapping[str, str] | None,
    parsed_model_ids: set[str] | frozenset[str] | None = None,
) -> str:
    """
    Resolve target dim/lookup table FQN from fact + dimension metadata.

    Order:
    1. Auto-built registry (from dimension models): composite key if level present, else logical
    2. Heuristic: with level — existing ``lkp_{level}`` then ``dim_{level}`` in fact schema
    3. Heuristic: ``{fact_schema}.dim_{logical}`` (or unqualified)

    When ``parsed_model_ids`` is set, heuristics prefer candidates that exist in the project.
    """
    logical, level = parse_dimension_field(dim_ref)
    ids = parsed_model_ids

    reg_table, _ = registry_lookup_table(logical, level, registry or {})
    if reg_table:
        return reg_table

    fact_schema = fact_name.split(".")[0] if "." in fact_name else ""

    if level:
        candidates: list[str] = []
        for short in (f"lkp_{level}", f"dim_{level}"):
            fq = f"{fact_schema}.{short}" if fact_schema else short
            candidates.append(fq)
        if ids is not None:
            for fq in candidates:
                if fq in ids:
                    return fq
        return candidates[0]

    short = f"dim_{logical}"
    return f"{fact_schema}.{short}" if fact_schema else short


def finest_hierarchy_pk(metadata: dict[str, Any]) -> str | None:
    """Return primary_key column for the highest level_number in hierarchy, if any."""
    hierarchy = metadata.get("hierarchy")
    levels = hierarchy.get("levels") if isinstance(hierarchy, dict) else None
    if not isinstance(levels, list) or not levels:
        return None
    best_pk: str | None = None
    best_num = -1
    for lvl in levels:
        if not isinstance(lvl, dict):
            continue
        pk = lvl.get("primary_key")
        if not isinstance(pk, str) or not pk.strip():
            continue
        try:
            num = int(lvl.get("level_number", 0) or 0)
        except (TypeError, ValueError):
            num = 0
        if num >= best_num:
            best_num = num
            best_pk = pk.strip()
    return best_pk


def column_is_declared_pk(col: dict[str, Any], hierarchy_pks: set[str]) -> bool:
    """True if column is a PK via hierarchy or primary_key test."""
    col_name = col.get("name")
    if not isinstance(col_name, str):
        return False
    if col_name in hierarchy_pks:
        return True
    tests = col.get("tests", [])
    if not isinstance(tests, list):
        return False
    return any(
        (isinstance(t, str) and t == "primary_key")
        or (isinstance(t, dict) and t.get("name") == "primary_key")
        or (isinstance(t, dict) and t.get("test") == "primary_key")
        for t in tests
    )


def extract_hierarchy_pk_set(metadata: dict[str, Any]) -> set[str]:
    hierarchy = metadata.get("hierarchy")
    levels = hierarchy.get("levels") if isinstance(hierarchy, dict) else None
    if not isinstance(levels, list):
        return set()
    pks: set[str] = set()
    for lvl in levels:
        if not isinstance(lvl, dict):
            continue
        pk = lvl.get("primary_key")
        if isinstance(pk, str) and pk.strip():
            pks.add(pk.strip())
    return pks


def resolve_target_pk_column(
    dim_metadata: dict[str, Any], fact_column: str, schema: list[dict[str, Any]] | None
) -> str | None:
    """
    Pick join key column on the dimension/lookup for documentation/tests.

    Prefer ``fact_column`` when it is a declared PK on the target; else finest
    hierarchy PK; else the sole schema PK column if unambiguous.
    """
    if not isinstance(schema, list):
        schema = []
    hierarchy_pks = extract_hierarchy_pk_set(dim_metadata)

    for col in schema:
        if not isinstance(col, dict):
            continue
        name = col.get("name")
        if name == fact_column and column_is_declared_pk(col, hierarchy_pks):
            return fact_column

    leaf = finest_hierarchy_pk(dim_metadata)
    if leaf:
        for col in schema:
            if (
                isinstance(col, dict)
                and col.get("name") == leaf
                and column_is_declared_pk(col, hierarchy_pks)
            ):
                return leaf

    pk_cols = [
        c.get("name")
        for c in schema
        if isinstance(c, dict)
        and isinstance(c.get("name"), str)
        and column_is_declared_pk(c, hierarchy_pks)
    ]
    pk_cols = [n for n in pk_cols if isinstance(n, str)]
    if len(pk_cols) == 1:
        return pk_cols[0]

    return leaf
