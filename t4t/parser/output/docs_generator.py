"""
Documentation site generator for t4t projects.
"""

import json
import re
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from t4t.parser.shared.dimension_registry import (
    parse_dimension_field,
    resolve_dimension_target_table,
    resolve_target_pk_column,
)
from t4t.parser.shared.exceptions import OutputGenerationError
from t4t.parser.shared.types import DependencyGraph, DimensionalGraph, ParsedModel


class DocsGenerator:
    """Generates static HTML documentation site with dependency graph."""

    def __init__(
        self,
        project_path: Path,
        output_path: Path,
        parsed_models: dict[str, ParsedModel],
        parsed_functions: dict[str, Any],
        dependency_graph: DependencyGraph,
        dimensional_graph: DimensionalGraph | None = None,
        dimension_registry: dict[str, str] | None = None,
    ) -> None:
        """
        Initialize the documentation generator.

        Args:
            project_path: Path to the project root
            output_path: Path where documentation will be generated
            parsed_models: Dictionary of parsed models
            parsed_functions: Dictionary of parsed functions
            dependency_graph: Dependency graph structure
            dimensional_graph: Optional dimensional relationship graph
            dimension_registry: Optional logical name → qualified table (auto-built from dimension models)
        """
        self.project_path = project_path
        self.output_path = output_path
        self.parsed_models = parsed_models
        self.dimension_registry = dimension_registry or {}
        self.parsed_functions = parsed_functions
        self.dependency_graph = dependency_graph
        self.dimensional_graph = dimensional_graph or {
            "facts": [],
            "dimensions": [],
            "relationships": [],
            "grain": {},
            "diagnostics": {},
        }
        # Set up Jinja2 template environment
        templates_dir = Path(__file__).parent / "templates"
        self.env = Environment(
            loader=FileSystemLoader(str(templates_dir)),
            autoescape=False,  # We're generating HTML, not user content
        )

    def _dimension_pk_candidates(self, logical: str) -> list[str]:
        dim = logical.strip().lower()
        if dim.startswith("dim_"):
            dim = dim[4:]
        singular = dim[:-1] if dim.endswith("s") and len(dim) > 1 else dim
        candidates: list[str] = []
        for stem in [dim, singular]:
            for suffix in ["_id", "_sk", "_key"]:
                cand = f"{stem}{suffix}"
                if cand not in candidates:
                    candidates.append(cand)
        candidates.extend(["id", "pk"])
        return candidates

    def _resolve_dimension_target(
        self, fact_model_name: str, dim_ref: str
    ) -> tuple[str, str] | None:
        if not dim_ref.strip():
            return None
        try:
            logical, _level = parse_dimension_field(dim_ref)
        except ValueError:
            return None
        model_ids = frozenset(self.parsed_models.keys())
        dim_table = resolve_dimension_target_table(
            fact_model_name, dim_ref, self.dimension_registry, model_ids
        )
        dim_model = self.parsed_models.get(dim_table)
        if not isinstance(dim_model, dict):
            return dim_table, f"{logical}_id"

        dim_meta = dim_model.get("model_metadata", {}).get("metadata", {}) or {}
        if not isinstance(dim_meta, dict):
            dim_meta = {}
        schema = dim_meta.get("schema")
        schema_list = schema if isinstance(schema, list) else []
        pk = resolve_target_pk_column(dim_meta, "", schema_list)
        if pk:
            return dim_table, pk

        schema_names = {
            c.get("name")
            for c in schema_list
            if isinstance(c, dict) and isinstance(c.get("name"), str)
        }
        for cand in self._dimension_pk_candidates(logical):
            if cand in schema_names:
                return dim_table, cand

        return dim_table, f"{logical}_id"

    def generate(self) -> None:
        """Generate the complete documentation site."""
        try:
            # Create output directory
            self.output_path.mkdir(parents=True, exist_ok=True)

            # Generate index page
            self._generate_index_page()

            # Generate model detail pages
            for model_name, model in self.parsed_models.items():
                self._generate_model_page(model_name, model)

            # Generate test detail pages
            self._generate_test_pages()

            # Generate graph data JSON for interactive features
            self._generate_graph_data()

        except Exception as e:
            raise OutputGenerationError(f"Failed to generate documentation: {e}") from e

    def _format_sql_for_docs(self, sql: str) -> str:
        """Format SQL for readable multiline docs output."""
        if not isinstance(sql, str):
            return ""
        text = sql.strip()
        if not text:
            return ""

        text = text.replace("\\r\\n", "\n").replace("\\n", "\n")

        try:
            import sqlglot

            parsed = sqlglot.parse(text)
            pretty_statements = [stmt.sql(pretty=True) for stmt in parsed]
            if pretty_statements:
                return ";\n\n".join(pretty_statements)
        except Exception:
            pass

        text = re.sub(r"\s+", " ", text).strip()
        text = re.sub(r",\s+", ",\n    ", text)
        for kw in [
            " FROM ",
            " LEFT JOIN ",
            " RIGHT JOIN ",
            " INNER JOIN ",
            " FULL JOIN ",
            " CROSS JOIN ",
            " WHERE ",
            " GROUP BY ",
            " HAVING ",
            " ORDER BY ",
            " LIMIT ",
            " UNION ",
            " UNION ALL ",
            " ON ",
        ]:
            text = text.replace(kw, f"\n{kw.strip()} ")
        return text

    def _generate_index_page(self) -> None:
        """Generate the main interactive index page with graph."""
        template = self.env.get_template("interactive_index.html")
        relationships = self.dimensional_graph.get("relationships", [])
        rel_by_fact_col: dict[tuple[str, str], dict[str, Any]] = {}
        for rel in relationships:
            if not isinstance(rel, dict):
                continue
            fact = rel.get("source_fact")
            col = rel.get("fact_column")
            if not isinstance(fact, str) or not isinstance(col, str):
                continue
            rel_by_fact_col[(fact, col)] = rel

        def infer_table_type(model_name: str, metadata: dict[str, Any]) -> str | None:
            explicit = metadata.get("table_type")
            if explicit in ("fact", "dim", "lookup"):
                return explicit
            short = model_name.split(".")[-1].lower()
            if short.startswith("dim_"):
                return "dim"
            if short.startswith(("fct_", "fact_")):
                return "fact"
            if short.startswith("lkp_"):
                return "lookup"
            return None

        # Prepare models data as a dict for easy JS access
        models_dict = {}
        for model_name in self.parsed_models:
            model = self.parsed_models[model_name]
            metadata = model.get("model_metadata", {}).get("metadata", {})
            schema = metadata.get("schema", [])
            table_type = infer_table_type(model_name, metadata)
            hierarchy = metadata.get("hierarchy")
            hierarchy_levels = hierarchy.get("levels") if isinstance(hierarchy, dict) else None
            hierarchy_pks: set[str] = set()
            if isinstance(hierarchy_levels, list):
                for lvl in hierarchy_levels:
                    if isinstance(lvl, dict):
                        pk = lvl.get("primary_key")
                        if isinstance(pk, str) and pk.strip():
                            hierarchy_pks.add(pk.strip())
            columns = []
            if isinstance(schema, list):
                for col in schema:
                    if isinstance(col, dict):
                        col_name = col.get("name", "")
                        fk_to = col.get("fk_to")
                        dim_ref = col.get("dimension")
                        col_tests = col.get("tests", [])
                        has_primary_key_test = False
                        if isinstance(col_tests, list):
                            has_primary_key_test = any(
                                (isinstance(t, str) and t == "primary_key")
                                or (isinstance(t, dict) and t.get("name") == "primary_key")
                                or (isinstance(t, dict) and t.get("test") == "primary_key")
                                for t in col_tests
                            )

                        col_type = "col"

                        # If simplified dimension metadata is provided, resolve fk_to for the D3 FK edges.
                        if (not fk_to) and isinstance(dim_ref, str) and dim_ref.strip():
                            resolved = self._resolve_dimension_target(model_name, dim_ref)
                            if resolved:
                                dim_table, pk_col = resolved
                                fk_to = {"table": dim_table, "column": pk_col}
                        if fk_to:
                            col_type = "fk"
                        elif table_type in {"dim", "lookup"} and (
                            col_name in hierarchy_pks or has_primary_key_test
                        ):
                            col_type = "pk"

                        # Surface inferred relationships in docs/UI payload even when
                        # the source metadata does not declare fk_to.
                        rel_match = rel_by_fact_col.get((model_name, col_name))
                        if (not fk_to) and isinstance(rel_match, dict):
                            target_table = rel_match.get("target_table")
                            target_column = rel_match.get("target_column")
                            if isinstance(target_table, str) and isinstance(target_column, str):
                                fk_to = {"table": target_table, "column": target_column}
                                col_type = "fk"

                        columns.append(
                            {
                                "name": col_name,
                                "type": col_type,
                                "fk_to": fk_to,
                            }
                        )

            models_dict[model_name] = {
                "name": model_name,
                "safe_name": self._safe_filename(model_name),
                "description": metadata.get("description", "No description"),
                "materialization": metadata.get("materialization", "table"),
                "columns": columns,
                "table_type": table_type,
                "data_model": metadata.get("data_model", False),
                "hierarchy": metadata.get("hierarchy"),
            }

        # Prepare functions data
        functions_dict = {}
        for func_name in self.parsed_functions:
            func = self.parsed_functions[func_name]
            func_metadata = func.get("function_metadata", {}).get("metadata", {})
            functions_dict[func_name] = {
                "name": func_name,
                "type": func_metadata.get("type", "scalar"),
            }

        # Add dimensional edges (dim/lookup -> fact) so Star view can render them
        # even when they were inferred and not present in SQL-derived lineage.
        graph_edges = list(self.dependency_graph["edges"])
        existing_pairs = {
            tuple(e) if isinstance(e, (list, tuple)) else (e.get("source"), e.get("target"))
            for e in graph_edges
            if isinstance(e, (list, tuple)) or isinstance(e, dict)
        }
        for rel in relationships:
            if not isinstance(rel, dict):
                continue
            src = rel.get("target_table")
            tgt = rel.get("source_fact")
            if not isinstance(src, str) or not isinstance(tgt, str):
                continue
            pair = (src, tgt)
            if pair in existing_pairs:
                continue
            graph_edges.append(pair)
            existing_pairs.add(pair)

        # Prepare graph data JSON
        graph_data_json = json.dumps(
            {
                "nodes": self.dependency_graph["nodes"],
                "edges": graph_edges,
                "sql_edges": self.dependency_graph.get("sql_edges", self.dependency_graph["edges"]),
                "dependencies": self.dependency_graph["dependencies"],
                "dependents": self.dependency_graph["dependents"],
                "execution_order": self.dependency_graph.get("execution_order", []),
                "cycles": self.dependency_graph.get("cycles", []),
                "functions": functions_dict,
                "dimensional_relationships": relationships,
            }
        )

        models_data_json = json.dumps(models_dict)

        html = template.render(
            models_count=len(self.parsed_models),
            nodes_count=len(self.dependency_graph["nodes"]),
            edges_count=len(self.dependency_graph["edges"]),
            graph_data_json=graph_data_json,
            models_data_json=models_data_json,
        )

        index_path = self.output_path / "index.html"
        with open(index_path, "w", encoding="utf-8") as f:
            f.write(html)

    def _generate_model_page(self, model_name: str, model: ParsedModel) -> None:
        """Generate a detail page for a specific model."""
        template = self.env.get_template("model.html")

        metadata = model.get("model_metadata", {}).get("metadata", {})
        description = metadata.get("description", "No description provided.")
        schema = metadata.get("schema", [])
        materialization = metadata.get("materialization", "table")
        tests = metadata.get("tests", [])
        incremental = metadata.get("incremental")
        hierarchy = metadata.get("hierarchy")
        table_type = metadata.get("table_type")
        file_path = model.get("model_metadata", {}).get("file_path", "Unknown")

        def infer_table_type(name: str, meta: dict[str, Any]) -> str | None:
            explicit = meta.get("table_type")
            if explicit in ("fact", "dim", "lookup"):
                return explicit
            short = name.split(".")[-1].lower()
            if short.startswith("dim_"):
                return "dim"
            if short.startswith(("fct_", "fact_")):
                return "fact"
            if short.startswith("lkp_"):
                return "lookup"
            return None

        def resolve_dimension_link(col: dict[str, Any]) -> tuple[str, str] | None:
            fk_to = col.get("fk_to")
            if isinstance(fk_to, dict):
                table = fk_to.get("table")
                column = fk_to.get("column")
                if isinstance(table, str) and isinstance(column, str):
                    return table, column
            dim_ref = col.get("dimension")
            if isinstance(dim_ref, str) and dim_ref.strip():
                resolved = self._resolve_dimension_target(model_name, dim_ref)
                if resolved:
                    return resolved
            return None

        def dimension_level_label(dim_table: str, pk_col: str) -> tuple[str | None, str | None]:
            dim_model = self.parsed_models.get(dim_table)
            if not isinstance(dim_model, dict):
                return None, None
            dim_meta = dim_model.get("model_metadata", {}).get("metadata", {}) or {}
            dim_short = dim_table.split(".")[-1]
            if dim_short.startswith("dim_"):
                dim_short = dim_short[4:]
            dim_h = dim_meta.get("hierarchy")
            levels = dim_h.get("levels") if isinstance(dim_h, dict) else None
            if not isinstance(levels, list):
                # Fallback: infer a likely grain label when hierarchy metadata is absent.
                pk = pk_col.lower().strip()
                if pk in {"date_id", "day_id", "calendar_date"}:
                    return dim_short, "Day"
                return None, None
            for level in levels:
                if not isinstance(level, dict):
                    continue
                if level.get("primary_key") == pk_col:
                    return dim_short, str(level.get("name", "")).strip() or None
            return None, None

        # Get dependencies and dependents
        dependencies = self.dependency_graph.get("dependencies", {}).get(model_name, [])
        dependents = self.dependency_graph.get("dependents", {}).get(model_name, [])

        rel_by_column: dict[str, dict[str, Any]] = {}
        for rel in self.dimensional_graph.get("relationships", []):
            if not isinstance(rel, dict):
                continue
            if rel.get("source_fact") != model_name:
                continue
            col = rel.get("fact_column")
            if isinstance(col, str):
                rel_by_column[col] = rel

        # Prepare schema data
        schema_data = []
        fact_granularity: list[dict[str, str]] = []
        for col in schema:
            col_tests = col.get("tests", [])
            dim_level = None
            dim_link = resolve_dimension_link(col if isinstance(col, dict) else {})
            if dim_link:
                dim_table, dim_pk = dim_link
                dim_name, level_name = dimension_level_label(dim_table, dim_pk)
                if dim_name and level_name:
                    dim_level = f"{dim_name}.{level_name}"
                    if infer_table_type(model_name, metadata) == "fact":
                        fact_granularity.append(
                            {
                                "column": col.get("name", ""),
                                "dimension_level": dim_level,
                            }
                        )
            # Fallback to dimensional graph relationships (covers inferred links).
            col_name = col.get("name", "") if isinstance(col, dict) else ""
            rel = rel_by_column.get(col_name)
            if not dim_level and isinstance(rel, dict):
                semantic_level = rel.get("semantic_level")
                if isinstance(semantic_level, str) and semantic_level:
                    dim_level = semantic_level
                elif isinstance(rel.get("dimension_name"), str) and isinstance(
                    rel.get("dimension_level"), str
                ):
                    dim_level = f"{rel['dimension_name']}.{rel['dimension_level']}"
                if dim_level and infer_table_type(model_name, metadata) == "fact":
                    fact_granularity.append(
                        {
                            "column": col_name,
                            "dimension_level": dim_level,
                        }
                    )
            schema_data.append(
                {
                    "name": col.get("name", ""),
                    "datatype": col.get("datatype", ""),
                    "description": col.get("description"),
                    "tests": col_tests if isinstance(col_tests, list) else [],
                    "fk_to": col.get("fk_to"),
                    "dimension_level": dim_level,
                }
            )

        # Deduplicate while preserving order
        seen_grain = set()
        dedup_granularity: list[dict[str, str]] = []
        for g in fact_granularity:
            key = (g["column"], g["dimension_level"])
            if key in seen_grain:
                continue
            seen_grain.add(key)
            dedup_granularity.append(g)

        # Prepare dependencies data
        deps_data = []
        for dep in dependencies:
            is_test = isinstance(dep, str) and dep.startswith("test:")
            deps_data.append(
                {
                    "name": dep,
                    "safe_name": self._safe_filename(dep),
                    "is_model": dep in self.parsed_models,
                    "is_test": is_test,
                }
            )

        # Prepare dependents data
        dependents_data = []
        for dep in dependents:
            is_test = isinstance(dep, str) and dep.startswith("test:")
            dependents_data.append(
                {
                    "name": dep,
                    "safe_name": self._safe_filename(dep),
                    "is_model": dep in self.parsed_models,
                    "is_test": is_test,
                }
            )

        # Prepare tests data
        tests_data = []
        for test in tests:
            if isinstance(test, dict):
                test_name = test.get("name") or test.get("test", "unknown")
                test_params = test.get("params", {})
                test_severity = test.get("severity", "error")
                test_node = f"test:{model_name}.{test_name}"
                tests_data.append(
                    {
                        "name": test_name,
                        "node_name": test_node,
                        "safe_name": self._safe_filename(test_node),
                        "params": test_params,
                        "params_json": json.dumps(test_params) if test_params else "",
                        "severity": test_severity,
                    }
                )
            else:
                test_name = str(test)
                test_node = f"test:{model_name}.{test_name}"
                tests_data.append(
                    {
                        "name": test_name,
                        "node_name": test_node,
                        "safe_name": self._safe_filename(test_node),
                        "params": {},
                        "params_json": "",
                        "severity": "error",
                    }
                )

        # Prepare incremental data
        incremental_data = None
        if incremental:
            incremental_data = {
                "strategy": incremental.get("strategy", "unknown"),
                "unique_key": incremental.get("unique_key", []),
                "merge_key": incremental.get("merge_key", []),
            }

        # Get code data (original and resolved SQL)
        code_data = model.get("code", {})
        original_sql = ""
        resolved_sql = ""
        if code_data and "sql" in code_data:
            sql_data = code_data["sql"]
            original_sql = sql_data.get("original_sql", "")
            resolved_sql = sql_data.get("resolved_sql", original_sql)
            original_sql = self._format_sql_for_docs(original_sql)
            resolved_sql = self._format_sql_for_docs(resolved_sql)

        html = template.render(
            model_name=model_name,
            description=description,
            schema=schema_data,
            materialization=materialization,
            file_path=file_path,
            dependencies=deps_data,
            dependents=dependents_data,
            tests=tests_data,
            incremental=incremental_data,
            hierarchy=hierarchy,
            table_type=table_type,
            inferred_table_type=infer_table_type(model_name, metadata),
            fact_granularity=dedup_granularity,
            original_sql=original_sql,
            resolved_sql=resolved_sql,
        )

        # Create safe filename
        safe_name = self._safe_filename(model_name)
        model_path = self.output_path / f"model_{safe_name}.html"
        with open(model_path, "w", encoding="utf-8") as f:
            f.write(html)

    def _generate_test_pages(self) -> None:
        """Generate detail pages for test nodes."""
        template = self.env.get_template("test.html")

        for model_name, model in self.parsed_models.items():
            metadata = model.get("model_metadata", {}).get("metadata", {}) or {}
            schema = metadata.get("schema", []) or []

            # Model-level tests
            for t in metadata.get("tests", []) or []:
                test_name, params, severity = self._extract_test_def(t)
                if not test_name:
                    continue
                test_node = f"test:{model_name}.{test_name}"
                sql = self._build_test_sql(
                    test_name=test_name,
                    model_name=model_name,
                    column_name=None,
                    params=params,
                )
                self._write_test_page(
                    template=template,
                    test_node=test_node,
                    model_name=model_name,
                    test_name=test_name,
                    column_name=None,
                    params=params,
                    severity=severity,
                    sql=self._format_sql_for_docs(sql),
                )

            # Column-level tests
            for col in schema:
                if not isinstance(col, dict):
                    continue
                column_name = col.get("name")
                if not isinstance(column_name, str) or not column_name:
                    continue
                for t in col.get("tests", []) or []:
                    test_name, params, severity = self._extract_test_def(t)
                    if not test_name:
                        continue
                    test_node = f"test:{model_name}.{column_name}.{test_name}"
                    sql = self._build_test_sql(
                        test_name=test_name,
                        model_name=model_name,
                        column_name=column_name,
                        params=params,
                    )
                    self._write_test_page(
                        template=template,
                        test_node=test_node,
                        model_name=model_name,
                        test_name=test_name,
                        column_name=column_name,
                        params=params,
                        severity=severity,
                        sql=self._format_sql_for_docs(sql),
                    )

    def _extract_test_def(self, test_def: Any) -> tuple[str | None, dict[str, Any], str]:
        """Return (test_name, params, severity) from a test definition."""
        if isinstance(test_def, str):
            return test_def, {}, "error"
        if isinstance(test_def, dict):
            test_name = test_def.get("name") or test_def.get("test")
            if not isinstance(test_name, str) or not test_name:
                return None, {}, "error"
            params = test_def.get("params", {})
            if not isinstance(params, dict):
                params = {}
            severity = test_def.get("severity", "error")
            if not isinstance(severity, str):
                severity = "error"
            return test_name, params, severity
        return None, {}, "error"

    def _write_test_page(
        self,
        template,
        test_node: str,
        model_name: str,
        test_name: str,
        column_name: str | None,
        params: dict[str, Any],
        severity: str,
        sql: str,
    ) -> None:
        html = template.render(
            test_node=test_node,
            model_name=model_name,
            model_safe_name=self._safe_filename(model_name),
            test_name=test_name,
            column_name=column_name,
            severity=severity,
            params_json=json.dumps(params, indent=2) if params else "",
            generated_sql=sql,
        )
        test_path = self.output_path / f"test_{self._safe_filename(test_node)}.html"
        with open(test_path, "w", encoding="utf-8") as f:
            f.write(html)

    def _build_test_sql(
        self,
        test_name: str,
        model_name: str,
        column_name: str | None,
        params: dict[str, Any] | None = None,
    ) -> str:
        """Build SQL for common tests; fallback to template stub."""
        params = params or {}
        t = test_name.strip().lower()
        table = model_name

        if t == "row_count_gt_0":
            return f"SELECT COUNT(*) AS row_count\nFROM {table}\nHAVING COUNT(*) = 0;"

        if t == "not_null":
            col = column_name or params.get("column")
            if isinstance(col, str) and col:
                return f"SELECT *\nFROM {table}\nWHERE {col} IS NULL;"

        if t == "unique":
            cols = params.get("columns")
            if isinstance(cols, list) and cols and all(isinstance(c, str) and c for c in cols):
                cols_sql = ", ".join(cols)
                return (
                    f"SELECT {cols_sql}, COUNT(*) AS duplicate_count\n"
                    f"FROM {table}\nGROUP BY {cols_sql}\nHAVING COUNT(*) > 1;"
                )
            if column_name:
                return (
                    f"SELECT {column_name}, COUNT(*) AS duplicate_count\n"
                    f"FROM {table}\nGROUP BY {column_name}\nHAVING COUNT(*) > 1;"
                )

        if t == "primary_key":
            col = column_name or params.get("column")
            if isinstance(col, str) and col:
                return (
                    f"SELECT {col}, COUNT(*) AS duplicate_count\n"
                    f"FROM {table}\nWHERE {col} IS NULL\n"
                    f"   OR {col} IN (\n"
                    f"       SELECT {col}\n"
                    f"       FROM {table}\n"
                    f"       GROUP BY {col}\n"
                    f"       HAVING COUNT(*) > 1\n"
                    f"   );"
                )

        if t == "accepted_values":
            col = column_name or params.get("column")
            values = params.get("values")
            if isinstance(col, str) and col and isinstance(values, list) and values:
                literals: list[str] = []
                for v in values:
                    if isinstance(v, str):
                        literals.append("'" + v.replace("'", "''") + "'")
                    else:
                        literals.append(str(v))
                values_sql = ", ".join(literals)
                return (
                    f"SELECT *\nFROM {table}\nWHERE {col} NOT IN ({values_sql}) OR {col} IS NULL;"
                )

        if t == "relationships":
            to_table = params.get("to")
            field = params.get("field")
            if isinstance(to_table, str) and to_table and isinstance(field, str) and field:
                source_col = column_name or params.get("source_field") or field
                if isinstance(source_col, str) and source_col:
                    return (
                        f"SELECT src.{source_col}\n"
                        f"FROM {table} src\n"
                        f"LEFT JOIN {to_table} tgt\n"
                        f"  ON src.{source_col} = tgt.{field}\n"
                        f"WHERE src.{source_col} IS NOT NULL\n"
                        f"  AND tgt.{field} IS NULL;"
                    )

        # Fallback stub for custom/unsupported tests
        placeholder_col = column_name or "<column_name>"
        return (
            "-- SQL template for this test is not directly available in docs generation.\n"
            f"-- test_name: {test_name}\n"
            f"-- model: {model_name}\n"
            f"-- column: {placeholder_col}\n"
            "-- params: " + json.dumps(params) + "\n\n"
            "SELECT *\n"
            f"FROM {model_name}\n"
            "-- Add your test condition here\n"
            "LIMIT 100;"
        )

    def _generate_graph_data(self) -> None:
        """Generate JSON file with graph data for interactive features."""
        graph_data = {
            "nodes": self.dependency_graph["nodes"],
            "edges": self.dependency_graph["edges"],
            "dependencies": self.dependency_graph["dependencies"],
            "dependents": self.dependency_graph["dependents"],
            "execution_order": self.dependency_graph.get("execution_order", []),
            "cycles": self.dependency_graph.get("cycles", []),
            "dimensional_relationships": self.dimensional_graph.get("relationships", []),
        }

        graph_path = self.output_path / "graph_data.json"
        with open(graph_path, "w", encoding="utf-8") as f:
            json.dump(graph_data, f, indent=2)

    def _safe_filename(self, name: str) -> str:
        """Convert model name to safe filename."""
        # Replace special characters
        safe = name.replace(".", "_")
        safe = safe.replace("/", "_")
        safe = safe.replace("\\", "_")
        safe = safe.replace(":", "_")
        safe = safe.replace("*", "_")
        safe = safe.replace("?", "_")
        safe = safe.replace('"', "_")
        safe = safe.replace("<", "_")
        safe = safe.replace(">", "_")
        safe = safe.replace("|", "_")
        return safe

    def _infer_column_type(self, col_name: str) -> str:
        """Deprecated: kept for backward compatibility in downstream imports."""
        _ = col_name
        return "col"
