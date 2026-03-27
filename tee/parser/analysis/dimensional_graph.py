"""
Dimensional relationship graph construction.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from tee.parser.shared.dimension_registry import (
    resolve_dimension_target_table,
    resolve_target_pk_column,
)
from tee.parser.shared.exceptions import DimensionalGraphError
from tee.parser.shared.types import DimensionalGraph, ParsedModel


class DimensionalRelationshipGraphBuilder:
    """Builds fact -> dimension/lookup semantic relationships from model metadata."""

    def __init__(
        self,
        *,
        include_lookup: bool = True,
        infer_from_column_names: bool = False,
    ) -> None:
        self.include_lookup = include_lookup
        self.infer_from_column_names = infer_from_column_names

    def build_graph(
        self,
        parsed_models: dict[str, ParsedModel],
        *,
        infer_from_column_names: bool | None = None,
        dimension_registry: dict[str, str] | None = None,
    ) -> DimensionalGraph:
        """
        Build dimensional relationship graph from parsed model metadata.

        Args:
            parsed_models: Parsed models keyed by fully-qualified model name
            infer_from_column_names: Optional override for automatic inference

        Returns:
            Dict with facts, dimensions, relationships, grain, diagnostics.
        """
        infer_names = (
            self.infer_from_column_names
            if infer_from_column_names is None
            else bool(infer_from_column_names)
        )

        reg = dimension_registry if dimension_registry is not None else {}

        table_roles: dict[str, str | None] = {
            model_name: self._infer_table_type(model_name, self._model_metadata(model))
            for model_name, model in parsed_models.items()
        }

        facts = sorted([name for name, role in table_roles.items() if role == "fact"])
        dims = sorted([name for name, role in table_roles.items() if role == "dim"])
        lookups = sorted([name for name, role in table_roles.items() if role == "lookup"])
        dimensional_tables = set(dims)
        if self.include_lookup:
            dimensional_tables |= set(lookups)

        pk_index = self._build_pk_index(parsed_models, dimensional_tables)
        relationships: list[dict[str, Any]] = []
        diag_unresolved: list[dict[str, Any]] = []
        diag_ambiguous: list[dict[str, Any]] = []

        for fact_name in facts:
            fact_meta = self._model_metadata(parsed_models[fact_name])
            schema = fact_meta.get("schema")
            if not isinstance(schema, list):
                continue

            for col in schema:
                if not isinstance(col, dict):
                    continue
                col_name = col.get("name")
                if not isinstance(col_name, str) or not col_name.strip():
                    continue
                col_name = col_name.strip()

                rel = self._relationship_from_declared_fk(
                    fact_name, col_name, col, parsed_models, table_roles
                )
                if rel:
                    relationships.append(rel)
                    continue

                rel = self._relationship_from_declared_dimension(
                    fact_name, col_name, col, parsed_models, table_roles, reg
                )
                if rel:
                    relationships.append(rel)
                    continue

                if not infer_names:
                    continue

                inferred = self._relationship_from_column_name(
                    fact_name, col_name, pk_index, table_roles, parsed_models
                )
                if inferred["status"] == "ok":
                    relationships.append(inferred["relationship"])
                elif inferred["status"] == "ambiguous":
                    diag_ambiguous.append(inferred["detail"])
                elif inferred["status"] == "unresolved":
                    diag_unresolved.append(inferred["detail"])

        if diag_ambiguous:
            details = "; ".join(
                f"{d['fact']}.{d['column']} -> {', '.join(d['candidates'])}" for d in diag_ambiguous
            )
            raise DimensionalGraphError(
                "Ambiguous dimensional inference detected; expected a single dimensional table "
                f"per inferred key. Details: {details}"
            )

        relationships = self._dedupe_relationships(relationships)
        grain = self._build_fact_grain(relationships)

        return {
            "facts": facts,
            "dimensions": sorted(dimensional_tables),
            "relationships": relationships,
            "grain": grain,
            "diagnostics": {
                "inference_enabled": infer_names,
                "unresolved_inferences": diag_unresolved,
            },
        }

    def _model_metadata(self, model: ParsedModel) -> dict[str, Any]:
        model_meta = model.get("model_metadata", {})
        metadata = model_meta.get("metadata", {})
        return metadata if isinstance(metadata, dict) else {}

    def _infer_table_type(self, model_name: str, metadata: dict[str, Any]) -> str | None:
        explicit = metadata.get("table_type")
        if explicit in ("fact", "dim", "lookup", "dimension"):
            return "dim" if explicit == "dimension" else explicit
        short = model_name.split(".")[-1].lower()
        if short.startswith(("fct_", "fact_")):
            return "fact"
        if short.startswith("dim_"):
            return "dim"
        if short.startswith("lkp_"):
            return "lookup"
        return None

    def _column_is_pk(self, col: dict[str, Any], hierarchy_pks: set[str]) -> bool:
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

    def _extract_hierarchy_info(
        self, metadata: dict[str, Any], table_name: str
    ) -> tuple[set[str], dict[str, tuple[str, str]]]:
        hierarchy_pks: set[str] = set()
        level_by_pk: dict[str, tuple[str, str]] = {}
        hierarchy = metadata.get("hierarchy")
        levels = hierarchy.get("levels") if isinstance(hierarchy, dict) else None
        if not isinstance(levels, list):
            return hierarchy_pks, level_by_pk

        dim_name = table_name.split(".")[-1]
        if dim_name.startswith(("dim_", "lkp_")):
            dim_name = dim_name[4:]
        dim_name = dim_name.strip()
        dim_label = dim_name.replace("_", " ").title().replace(" ", "")

        for lvl in levels:
            if not isinstance(lvl, dict):
                continue
            pk = lvl.get("primary_key")
            level_name = lvl.get("name")
            if not isinstance(pk, str) or not pk.strip():
                continue
            hierarchy_pks.add(pk.strip())
            if isinstance(level_name, str) and level_name.strip():
                level_clean = level_name.strip()
                level_by_pk[pk.strip()] = (dim_label, level_clean)
        return hierarchy_pks, level_by_pk

    def _build_pk_index(
        self, parsed_models: dict[str, ParsedModel], dimensional_tables: set[str]
    ) -> dict[str, list[dict[str, str]]]:
        pk_index: dict[str, list[dict[str, str]]] = defaultdict(list)
        for table_name in sorted(dimensional_tables):
            model = parsed_models.get(table_name)
            if not isinstance(model, dict):
                continue
            metadata = self._model_metadata(model)
            schema = metadata.get("schema")
            if not isinstance(schema, list):
                continue
            hierarchy_pks, level_by_pk = self._extract_hierarchy_info(metadata, table_name)
            for col in schema:
                if not isinstance(col, dict):
                    continue
                col_name = col.get("name")
                if not isinstance(col_name, str) or not col_name.strip():
                    continue
                col_name = col_name.strip()
                if not self._column_is_pk(col, hierarchy_pks):
                    continue
                dim_label, level_label = level_by_pk.get(
                    col_name, (self._dimension_label_from_table(table_name), None)
                )
                pk_index[col_name.lower()].append(
                    {
                        "table": table_name,
                        "column": col_name,
                        "dimension_name": dim_label,
                        "dimension_level": level_label,
                    }
                )
        return pk_index

    def _dimension_label_from_table(self, table_name: str) -> str:
        short = table_name.split(".")[-1]
        if short.startswith(("dim_", "lkp_")):
            short = short[4:]
        return short.replace("_", " ").title().replace(" ", "")

    def _semantic_level(self, dimension_name: str, dimension_level: str | None) -> str | None:
        if not dimension_name:
            return None
        if not dimension_level:
            return None
        return f"{dimension_name}.{dimension_level}"

    def _relationship_from_declared_fk(
        self,
        fact_name: str,
        col_name: str,
        col: dict[str, Any],
        parsed_models: dict[str, ParsedModel],
        table_roles: dict[str, str | None],
    ) -> dict[str, Any] | None:
        fk_to = col.get("fk_to")
        if not isinstance(fk_to, dict):
            return None
        target_table = fk_to.get("table")
        target_col = fk_to.get("column")
        if not isinstance(target_table, str) or not target_table.strip():
            return None
        if not isinstance(target_col, str) or not target_col.strip():
            return None
        role = table_roles.get(target_table)
        if role not in ("dim", "lookup"):
            return None
        dim_name, level = self._dimension_and_level_for_target(
            target_table, target_col, parsed_models
        )
        return {
            "source_fact": fact_name,
            "target_table": target_table,
            "target_table_type": role,
            "fact_column": col_name,
            "target_column": target_col,
            "dimension_name": dim_name,
            "dimension_level": level,
            "semantic_level": self._semantic_level(dim_name, level),
            "origin": "declared_fk",
            "confidence": "high",
        }

    def _resolve_dimension_join_column(
        self, target_table: str, fact_col: str, parsed_models: dict[str, ParsedModel]
    ) -> str:
        model = parsed_models.get(target_table)
        if not isinstance(model, dict):
            raise DimensionalGraphError(
                f"Dimensional target {target_table!r} is missing from parsed models."
            )
        metadata = self._model_metadata(model)
        schema = metadata.get("schema")
        schema_list = schema if isinstance(schema, list) else []
        pk = resolve_target_pk_column(metadata, fact_col, schema_list)
        if not pk:
            raise DimensionalGraphError(
                "Invalid dimensional relationship metadata: "
                f"{target_table} has no resolvable primary key column for link from fact column "
                f"{fact_col!r}. Use explicit fk_to or declare hierarchy primary_key / column "
                "primary_key tests."
            )
        return pk

    def _relationship_from_declared_dimension(
        self,
        fact_name: str,
        col_name: str,
        col: dict[str, Any],
        parsed_models: dict[str, ParsedModel],
        table_roles: dict[str, str | None],
        dimension_registry: dict[str, str],
    ) -> dict[str, Any] | None:
        dim_ref = col.get("dimension")
        if not isinstance(dim_ref, str) or not dim_ref.strip():
            return None
        model_ids = frozenset(parsed_models.keys())
        target_dim = resolve_dimension_target_table(
            fact_name, dim_ref, dimension_registry, model_ids
        )
        target_role = table_roles.get(target_dim)
        if target_role not in ("dim", "lookup"):
            return None

        target_col = self._resolve_dimension_join_column(target_dim, col_name, parsed_models)
        dim_name, level = self._dimension_and_level_for_target(
            target_dim, target_col, parsed_models
        )

        explicit_level = "." in dim_ref.strip()
        if self.include_lookup and target_role == "dim" and level and not explicit_level:
            lookup_target = self._lookup_for_level(
                fact_name=fact_name, level_name=level, table_roles=table_roles
            )
            if lookup_target and lookup_target != target_dim:
                lookup_col = (
                    self._lookup_pk_for_level(lookup_target, level, parsed_models) or target_col
                )
                return {
                    "source_fact": fact_name,
                    "target_table": lookup_target,
                    "target_table_type": "lookup",
                    "fact_column": col_name,
                    "target_column": lookup_col,
                    "dimension_name": dim_name,
                    "dimension_level": level,
                    "semantic_level": self._semantic_level(dim_name, level),
                    "origin": "declared_dimension",
                    "confidence": "high",
                }

        return {
            "source_fact": fact_name,
            "target_table": target_dim,
            "target_table_type": target_role,
            "fact_column": col_name,
            "target_column": target_col,
            "dimension_name": dim_name,
            "dimension_level": level,
            "semantic_level": self._semantic_level(dim_name, level),
            "origin": "declared_dimension",
            "confidence": "high",
        }

    def _relationship_from_column_name(
        self,
        fact_name: str,
        col_name: str,
        pk_index: dict[str, list[dict[str, str]]],
        table_roles: dict[str, str | None],
        parsed_models: dict[str, ParsedModel],
    ) -> dict[str, Any]:
        key = col_name.lower()
        candidates = pk_index.get(key, [])
        if not candidates:
            return {
                "status": "unresolved",
                "detail": {
                    "fact": fact_name,
                    "column": col_name,
                    "reason": "no_dimensional_pk_match",
                },
            }
        if len(candidates) > 1:
            return {
                "status": "ambiguous",
                "detail": {
                    "fact": fact_name,
                    "column": col_name,
                    "candidates": [f"{c['table']}.{c['column']}" for c in candidates],
                },
            }
        c = candidates[0]
        role = table_roles.get(c["table"])
        dim_name = c.get("dimension_name") or self._dimension_label_from_table(c["table"])
        level = c.get("dimension_level")

        target_table = c["table"]
        target_col = c["column"]
        if self.include_lookup and level and role == "dim":
            lookup_target = self._lookup_for_level(
                fact_name=fact_name, level_name=level, table_roles=table_roles
            )
            if lookup_target:
                lookup_col = self._lookup_pk_for_level(lookup_target, level, parsed_models)
                if lookup_col:
                    target_table = lookup_target
                    target_col = lookup_col
                    role = "lookup"

        return {
            "status": "ok",
            "relationship": {
                "source_fact": fact_name,
                "target_table": target_table,
                "target_table_type": role,
                "fact_column": col_name,
                "target_column": target_col,
                "dimension_name": dim_name,
                "dimension_level": level,
                "semantic_level": self._semantic_level(dim_name, level),
                "origin": "inferred_column_name",
                "confidence": "medium",
            },
        }

    def _is_dimension_pk(
        self, table_name: str, column_name: str, parsed_models: dict[str, ParsedModel]
    ) -> bool:
        model = parsed_models.get(table_name)
        if not isinstance(model, dict):
            return False
        metadata = self._model_metadata(model)
        schema = metadata.get("schema")
        if not isinstance(schema, list):
            return False
        hierarchy_pks, _ = self._extract_hierarchy_info(metadata, table_name)
        for col in schema:
            if not isinstance(col, dict):
                continue
            name = col.get("name")
            if not isinstance(name, str):
                continue
            if name == column_name and self._column_is_pk(col, hierarchy_pks):
                return True
        return False

    def _lookup_for_level(
        self, fact_name: str, level_name: str, table_roles: dict[str, str | None]
    ) -> str | None:
        if not level_name:
            return None
        safe = level_name.strip().lower().replace(" ", "_")
        if not safe:
            return None
        fact_schema = fact_name.split(".")[0] if "." in fact_name else ""
        candidates = []
        if fact_schema:
            candidates.append(f"{fact_schema}.lkp_{safe}")
        candidates.append(f"lkp_{safe}")
        for cand in candidates:
            if table_roles.get(cand) == "lookup":
                return cand
        return None

    def _lookup_pk_for_level(
        self, lookup_table: str, level_name: str, parsed_models: dict[str, ParsedModel]
    ) -> str | None:
        model = parsed_models.get(lookup_table)
        if not isinstance(model, dict):
            return None
        metadata = self._model_metadata(model)
        _, by_pk = self._extract_hierarchy_info(metadata, lookup_table)
        level_lower = level_name.strip().lower()
        for pk_col, (_, lvl_name) in by_pk.items():
            if lvl_name.strip().lower() == level_lower:
                return pk_col
        schema = metadata.get("schema")
        if isinstance(schema, list):
            hierarchy_pks, _ = self._extract_hierarchy_info(metadata, lookup_table)
            for col in schema:
                if isinstance(col, dict) and self._column_is_pk(col, hierarchy_pks):
                    name = col.get("name")
                    if isinstance(name, str):
                        return name
        return None

    def _dimension_and_level_for_target(
        self, target_table: str, target_col: str, parsed_models: dict[str, ParsedModel]
    ) -> tuple[str, str | None]:
        model = parsed_models.get(target_table)
        default_dim_name = self._dimension_label_from_table(target_table)
        if not isinstance(model, dict):
            return default_dim_name, None
        metadata = self._model_metadata(model)
        _, by_pk = self._extract_hierarchy_info(metadata, target_table)
        dim_name, level = by_pk.get(target_col, (default_dim_name, None))
        return dim_name, level

    def _dedupe_relationships(self, rels: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen = set()
        out = []
        for rel in rels:
            key = (
                rel.get("source_fact"),
                rel.get("target_table"),
                rel.get("fact_column"),
                rel.get("target_column"),
            )
            if key in seen:
                continue
            seen.add(key)
            out.append(rel)
        return out

    def _build_fact_grain(self, relationships: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        grain_map: dict[str, dict[str, Any]] = {}
        by_fact: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for rel in relationships:
            by_fact[rel["source_fact"]].append(rel)

        for fact, rels in by_fact.items():
            semantic_levels = []
            for rel in rels:
                semantic = rel.get("semantic_level")
                if isinstance(semantic, str) and semantic:
                    semantic_levels.append(semantic)
            seen = set()
            ordered_levels = []
            for level in semantic_levels:
                if level in seen:
                    continue
                seen.add(level)
                ordered_levels.append(level)
            grain_map[fact] = {
                "semantic_levels": ordered_levels,
                "relationship_count": len(rels),
            }
        return grain_map
