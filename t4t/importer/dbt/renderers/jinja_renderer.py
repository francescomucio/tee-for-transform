"""
Jinja2 renderer for dbt models with macro support.

Loads macros from packages and project, and renders SQL models through Jinja2.
"""

import logging
from pathlib import Path
from typing import Any

import sqlglot
from jinja2 import Environment, FileSystemLoader
from jinja2.ext import Extension
from jinja2.nodes import CallBlock

from t4t.importer.dbt.parsers import MacroParser


class DoExtension(Extension):
    """Jinja2 extension to support dbt's {% do %} statement."""

    tags = {"do"}

    def parse(self, parser):
        """Parse {% do %} statement - execute without output."""
        lineno = next(parser.stream).lineno
        # Parse the expression (method call like fields.append(...))
        expr = parser.parse_expression()
        # Create a call block that executes but returns empty string
        return CallBlock(
            self.call_method("_do_statement", [expr], lineno=lineno),
            [],  # No body
            [],  # No scoped variables
            [],  # No required variables
            lineno=lineno,
        )

    def _do_statement(self, expr, caller):  # noqa: ARG002
        """Execute expression without output."""
        # Evaluate the expression in the current context
        # The expression is already evaluated by Jinja2, we just don't output it
        # Note: expr and caller are required by Jinja2's CallBlock interface
        return ""


logger = logging.getLogger(__name__)


class MacroNamespace:
    """Namespace object that supports both dict-like and attribute access for macros."""

    def __init__(self) -> None:
        """Initialize empty namespace."""
        self._macros: dict[str, Any] = {}

    def __getitem__(self, key: str) -> Any:
        """Support dict-like access: namespace['macro_name']."""
        return self._macros[key]

    def __setitem__(self, key: str, value: Any) -> None:
        """Support dict-like assignment: namespace['macro_name'] = func."""
        self._macros[key] = value

    def __getattr__(self, name: str) -> Any:
        """Support attribute access: namespace.macro_name."""
        if name.startswith("_"):
            return super().__getattribute__(name)
        if name in self._macros:
            return self._macros[name]
        raise AttributeError(f"Macro '{name}' not found in namespace")

    def __contains__(self, key: str) -> bool:
        """Support 'in' operator."""
        return key in self._macros

    def __iter__(self):
        """Support iteration."""
        return iter(self._macros)

    def keys(self):
        """Return macro names."""
        return self._macros.keys()

    def values(self):
        """Return macro functions."""
        return self._macros.values()

    def items(self):
        """Return (name, function) pairs."""
        return self._macros.items()


class JinjaRenderer:
    """Renders dbt SQL models through Jinja2 with macro support."""

    def __init__(
        self,
        project_path: Path,
        macro_paths: list[str] | None = None,
        package_paths: dict[str, Path] | None = None,
        model_name_map: dict[str, str] | None = None,
        source_map: dict[str, dict[str, str]] | None = None,
        variables: dict[str, Any] | None = None,
        adapter_type: str = "duckdb",
        verbose: bool = False,
    ) -> None:
        """
        Initialize Jinja2 renderer.

        Args:
            project_path: Path to dbt project root
            macro_paths: List of macro paths from dbt_project.yml (default: ["macros"])
            package_paths: Dictionary mapping package names to their paths
            model_name_map: Mapping of dbt model names to final table names
            source_map: Mapping of source names to schema.table format
            variables: Dictionary of variables to use in rendering
            adapter_type: Database adapter type for macro dispatch (default: "duckdb")
                          Used to select adapter-specific macros (e.g., duckdb__ vs postgres__)
            verbose: Enable verbose logging
        """
        self.project_path = project_path
        self.macro_paths = macro_paths or ["macros"]
        self.package_paths = package_paths or {}
        self.model_name_map = model_name_map or {}
        self.source_map = source_map or {}
        self.variables = variables or {}
        self.adapter_type = adapter_type  # e.g., "duckdb", "postgres", "snowflake"
        self.verbose = verbose

        # Map adapter_type to SQLglot dialect name for final SQL conversion
        self._adapter_to_dialect = {
            "duckdb": "duckdb",
            "postgres": "postgres",
            "postgresql": "postgres",
            "snowflake": "snowflake",
            "bigquery": "bigquery",
            "redshift": "redshift",
            "spark": "spark",
            "trino": "trino",
        }

        # Build list of search paths for macros
        search_paths: list[Path] = []

        # Add project macro paths
        for macro_path_str in self.macro_paths:
            macro_path = project_path / macro_path_str
            if macro_path.exists():
                search_paths.append(macro_path)

        # Add package macro paths
        for pkg_name, pkg_path in self.package_paths.items():
            macros_dir = pkg_path / "macros"
            if macros_dir.exists():
                search_paths.append(macros_dir)
                if self.verbose:
                    logger.info(f"Added macro path from package {pkg_name}: {macros_dir}")

        # Create Jinja2 environment with FileSystemLoader
        # Add extensions to support dbt-specific Jinja tags
        self.env = Environment(
            loader=FileSystemLoader([str(p) for p in search_paths]),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
            extensions=[DoExtension],
        )

        # Add dbt functions to the environment
        self._add_dbt_functions()

        # Load macros into the environment
        self._load_macros()

    def _add_dbt_functions(self) -> None:
        """Add dbt-specific functions and objects to Jinja2 environment."""
        model_name_map = self.model_name_map
        source_map = self.source_map
        variables = self.variables

        def ref(model_name: str) -> str:
            """dbt ref() function - returns fully qualified table name."""
            if model_name in model_name_map:
                return model_name_map[model_name]
            # Fallback to model name if not found
            logger.warning(f"Model '{model_name}' not found in model_name_map, using name as-is")
            return model_name

        def source(source_name: str, table_name: str) -> str:
            """dbt source() function - returns schema.table format."""
            if source_name in source_map and table_name in source_map[source_name]:
                return source_map[source_name][table_name]
            # Fallback to source_name.table_name
            schema_table = f"{source_name}.{table_name}"
            logger.warning(
                f"Source '{source_name}.{table_name}' not found in source_map, using '{schema_table}'"
            )
            return schema_table

        def var(var_name: str, default: Any = None) -> Any:
            """dbt var() function - returns variable value or default."""
            return variables.get(var_name, default)

        def env_var(var_name: str, default: Any = None) -> Any:
            """dbt env_var() function - returns environment variable value or default."""
            import os  # noqa: PLC0415

            return os.environ.get(var_name, default)

        def config(**kwargs: Any) -> dict[str, Any]:
            """dbt config() function - captures model config blocks."""
            # In dbt, config() is used to set model configuration
            # For rendering purposes, we just return the config dict
            return kwargs

        # Add functions to global namespace
        self.env.globals["ref"] = ref
        self.env.globals["source"] = source
        self.env.globals["var"] = var
        self.env.globals["env_var"] = env_var
        self.env.globals["config"] = config

        # Add dbt-specific objects that macros might use
        # Create an adapter dispatcher that selects adapter-specific macros
        # Capture env and adapter_type in closure
        env = self.env
        adapter_type = self.adapter_type

        class AdapterDispatcher:
            """
            Adapter dispatcher for dbt macros.

            Selects the right macro implementation based on adapter type:
            - duckdb__macro_name (if adapter_type == "duckdb")
            - postgres__macro_name (if adapter_type == "postgres")
            - default__macro_name (fallback)
            """

            def dispatch(self, macro_name: str, package: str = None):
                """
                Dispatch to adapter-specific or default implementation of a macro.

                Follows dbt's dispatch precedence:
                1. Project macros (highest)
                2. Adapter-specific macros (duckdb__, postgres__, etc.)
                3. Default macros (default__)
                4. Package macros (lowest)
                """

                # Return a function that looks up the right macro
                def dispatch_func(*args, **kwargs):
                    # Try adapter-specific first (e.g., duckdb__cents_to_dollars)
                    adapter_macro_name = f"{adapter_type}__{macro_name}"
                    default_macro_name = f"default__{macro_name}"

                    # First, check project macros (global namespace - highest precedence)
                    # Try adapter-specific, then default
                    for macro_name_to_try in [adapter_macro_name, default_macro_name]:
                        if macro_name_to_try in env.globals:
                            return env.globals[macro_name_to_try](*args, **kwargs)

                    # Then check package namespaces (lower precedence)
                    # If package is specified, check that package first
                    if package and package in env.globals:
                        namespace = env.globals[package]
                        if isinstance(namespace, MacroNamespace):
                            for macro_name_to_try in [adapter_macro_name, default_macro_name]:
                                if macro_name_to_try in namespace:
                                    return namespace[macro_name_to_try](*args, **kwargs)

                    # Check all package namespaces
                    for _key, value in env.globals.items():
                        if isinstance(value, MacroNamespace):
                            for macro_name_to_try in [adapter_macro_name, default_macro_name]:
                                if macro_name_to_try in value:
                                    return value[macro_name_to_try](*args, **kwargs)

                    # Fallback: return empty string
                    logger.warning(
                        f"Macro {macro_name} not found for adapter {adapter_type} "
                        f"(tried {adapter_macro_name}, {default_macro_name}), returning empty string"
                    )
                    return ""

                return dispatch_func

        # Create dbt utility functions object
        # These return standard SQL - dialect conversion happens at the end via SQLglot
        class DbtUtils:
            """
            dbt cross-database utility functions.

            Returns standard SQL expressions. The final rendered SQL will be converted
            to the target dialect using SQLglot in the render() method.
            See: https://docs.getdbt.com/reference/dbt-jinja-functions/cross-database-macros
            """

            # Data type functions
            def type_string(self) -> str:
                """Return string type for casting."""
                return "TEXT"

            def type_timestamp(self) -> str:
                """Return timestamp type for casting."""
                return "TIMESTAMP"

            def type_int(self) -> str:
                """Return integer type for casting."""
                return "INT"

            def type_bigint(self) -> str:
                """Return bigint type for casting."""
                return "BIGINT"

            def type_numeric(self) -> str:
                """Return numeric type for casting."""
                return "NUMERIC(28,6)"

            def type_boolean(self) -> str:
                """Return boolean type for casting."""
                return "BOOLEAN"

            def type_float(self) -> str:
                """Return float type for casting."""
                return "FLOAT"

            # String functions
            def concat(self, *fields) -> str:
                """Concatenate strings using || operator."""
                if fields and isinstance(fields[0], list):
                    fields = fields[0]
                return " || ".join(str(f) for f in fields)

            def hash(self, value: str) -> str:
                """Return hash function call."""
                return f"MD5({value})"

            # String literal functions
            def string_literal(self, value: str) -> str:
                """Return properly quoted string literal."""
                escaped = str(value).replace("'", "''")
                return f"'{escaped}'"

            def escape_single_quotes(self, value: str) -> str:
                """Escape single quotes in string."""
                return str(value).replace("'", "''")

            # Cast functions
            def safe_cast(self, expr: str, target_type: str) -> str:
                """Safe cast that returns NULL on error."""
                # Use TRY_CAST if available, fallback to CAST
                return f"TRY_CAST({expr} AS {target_type})"

            def cast(self, expr: str, target_type: str) -> str:
                """Cast expression to target type."""
                return f"CAST({expr} AS {target_type})"

            # Date and time functions
            def date_trunc(self, datepart: str, date_expr: str) -> str:
                """Truncate date to specified part."""
                return f"DATE_TRUNC('{datepart}', {date_expr})"

            def dateadd(
                self, datepart: str, interval: int | str, from_date_or_timestamp: str
            ) -> str:
                """Add interval to date."""
                if isinstance(interval, str):
                    # SQL expression - use directly
                    return f"{from_date_or_timestamp} + INTERVAL '{interval}' {datepart}"
                else:
                    # Numeric interval - need + or - operator
                    sign = "+" if interval >= 0 else "-"
                    abs_interval = abs(interval)
                    return f"{from_date_or_timestamp} {sign} INTERVAL '{abs_interval}' {datepart}"

            def datediff(self, first_date: str, second_date: str, datepart: str) -> str:
                """Calculate difference between dates."""
                return f"DATEDIFF({datepart}, {first_date}, {second_date})"

            def date(self, year: int, month: int, day: int) -> str:
                """Create date from year, month, day."""
                date_str = f"{year:04d}-{month:02d}-{day:02d}"
                return f"TO_DATE('{date_str}', 'YYYY-MM-DD')"

            def current_timestamp(self) -> str:
                """Return current timestamp function."""
                return "CURRENT_TIMESTAMP"

            def now(self) -> str:
                """Alias for current_timestamp."""
                return "CURRENT_TIMESTAMP"

            # Set functions
            def except_(self) -> str:
                """Return EXCEPT operator."""
                return "EXCEPT"

            def intersect(self) -> str:
                """Return INTERSECT operator."""
                return "INTERSECT"

        self.env.globals["adapter"] = AdapterDispatcher()
        self.env.globals["dbt"] = DbtUtils()

        # Add this and target objects (dbt context objects)
        class This:
            """dbt this object - provides context about current model."""

            def __init__(self, schema: str | None = None, name: str | None = None):
                self.schema = schema
                self.name = name
                # Add other common attributes
                self.identifier = name
                self.table = name

        class Target:
            """dbt target object - provides context about target environment."""

            def __init__(self, name: str = "dev", schema: str | None = None, **kwargs: Any):
                self.name = name
                self.schema = schema
                # Add any additional target config
                for key, value in kwargs.items():
                    setattr(self, key, value)

        # Create this and target objects (can be customized per model if needed)
        # For now, use defaults
        self.env.globals["this"] = This()
        self.env.globals["target"] = Target()

        # Note: return() is handled specially in macro_func - it captures the return value
        # We still add it to globals for reference, but the actual implementation
        # is in the macro_func closure where it can capture the return value
        def return_func(value: Any) -> str:
            """Return function for dbt macros (fallback - actual handling is in macro_func)."""
            # This is a fallback - the real implementation is in macro_func
            # where it can capture the return value properly
            return str(value) if value is not None else ""

        self.env.globals["return"] = return_func

        # Add load_result function for {% call statement(...) %} blocks
        # In dbt, this loads results from executed statements
        # For rendering, we return a mock structure
        # Store results per statement name to allow multiple statements (instance-level)
        self._statement_results: dict[str, dict[str, Any]] = {}

        def load_result(name: str) -> dict[str, Any]:
            """
            Load result from a {% call statement(...) %} block.

            In dbt, this returns the results of executed SQL.
            For rendering purposes, we return a mock structure.
            """
            # Return a mock result structure that macros expect
            # The structure should have 'data' as a list of lists
            # Most macros do: value_list['data'] | map(attribute=0) | list
            if name not in self._statement_results:
                # Default: return a reasonable interval count (e.g., 3650 for 10 years of days)
                self._statement_results[name] = {
                    "data": [[3650]],  # Mock data: reasonable default for date intervals
                    "columns": ["result"],
                }
            return self._statement_results[name]

        self.env.globals["load_result"] = load_result

        # Add statement function for {% call statement(...) %} blocks
        # In Jinja2, {% call func() %} calls func() and passes the body as 'caller' keyword arg
        # So statement() must accept 'caller' as a keyword argument
        def statement(name: str, fetch_result: bool = False, caller=None):  # noqa: ARG001
            """
            Statement function for {% call statement(...) %} blocks.

            In dbt, this executes SQL silently and stores results for load_result().
            IMPORTANT: {% call statement(...) %} blocks should NOT output SQL - they execute silently.
            For rendering, we execute caller but return empty string (no output).

            Args:
                name: Statement name (unused in rendering, kept for API compatibility)
                fetch_result: Whether to fetch results (unused in rendering, kept for API compatibility)
                caller: The SQL body from {% call %} tag
            """
            # Execute the caller (SQL body) but don't output it
            # In real dbt, this would execute SQL against the database and store results
            # For rendering, we execute it to process any nested macros, but return empty
            if caller:
                # Execute caller to process any nested Jinja, but don't output the result
                caller()
                # Return empty string - statement blocks don't output anything
                return ""
            return ""

        self.env.globals["statement"] = statement

    def _load_macros(self) -> None:
        """
        Load macros from project and packages into Jinja2 environment.

        Follows dbt's dispatch/override precedence:
        1. Project macros (highest precedence - can override package macros)
        2. Dispatch target package (if configured - not yet implemented)
        3. Original package (lowest precedence)

        This is achieved by loading project macros first, then packages.
        """
        macro_parser = MacroParser(verbose=self.verbose)

        # Load macros from project FIRST (highest precedence)
        # Project macros can override package macros
        project_macro_files = macro_parser.discover_macros(self.project_path, self.macro_paths)
        if project_macro_files:
            project_macros = macro_parser.parse_all_macros(project_macro_files)
            self._register_macros(project_macros, None, "project")
            if self.verbose:
                logger.info(f"Loaded {len(project_macros)} project macros (highest precedence)")

        # Load macros from packages (with package namespace)
        # These have lower precedence than project macros
        for pkg_name, pkg_path in self.package_paths.items():
            if self.verbose:
                logger.info(f"Loading macros from package {pkg_name} at {pkg_path}")
            pkg_macro_files = macro_parser.discover_macros(pkg_path, ["macros"])
            if self.verbose:
                logger.info(f"Found {len(pkg_macro_files)} macro files in package {pkg_name}")
            if pkg_macro_files:
                pkg_macros = macro_parser.parse_all_macros(pkg_macro_files)
                if self.verbose:
                    logger.info(
                        f"Parsed {len(pkg_macros)} unique macros from package {pkg_name}: {list(pkg_macros.keys())[:10]}"
                    )
                # Register macros under package namespace (e.g., dbt_utils.generate_surrogate_key)
                self._register_macros(pkg_macros, pkg_name, f"package:{pkg_name}")

    def _register_macros(
        self,
        macros: dict[str, list[dict[str, Any]]],
        namespace: str | None,
        source: str,
    ) -> None:
        """
        Register macros in Jinja2 environment.

        Args:
            macros: Dictionary mapping macro names to lists of macro definitions
            namespace: Package namespace (e.g., "dbt_utils") or None for project macros
            source: Source identifier (e.g., "project" or "package:name")
        """
        # Create namespace object if needed
        if namespace:
            if namespace not in self.env.globals:
                # Create a namespace object that supports both dict and attribute access
                namespace_obj = MacroNamespace()
                self.env.globals[namespace] = namespace_obj
            else:
                namespace_obj = self.env.globals[namespace]
                # Ensure it's a MacroNamespace (in case it was created as a dict before)
                if not isinstance(namespace_obj, MacroNamespace):
                    # Convert existing dict to MacroNamespace
                    new_namespace = MacroNamespace()
                    for key, value in namespace_obj.items():
                        new_namespace[key] = value
                    self.env.globals[namespace] = new_namespace
                    namespace_obj = new_namespace
        else:
            namespace_obj = self.env.globals  # Register directly in globals

        for macro_name, macro_defs in macros.items():
            # Use the first non-adapter-specific macro, or first one if all are adapter-specific
            # In a real dbt environment, adapter-specific macros are selected based on the adapter
            # For now, we'll use the first definition
            macro_def = macro_defs[0]
            macro_body = macro_def["body"]
            parameters = macro_def["parameters"]

            # Create a callable that renders the macro body
            # Use a factory function to properly capture variables in closure
            def create_macro_func(m_name: str, m_body: str, m_params: list[str]) -> Any:
                def macro_func(*args: Any, **kwargs: Any) -> Any:  # noqa: B023
                    # Create a special return handler that captures the return value
                    # In dbt, return() in a macro returns the value for use in other macros, not for output
                    # We use an exception to stop rendering and return the value immediately
                    class MacroReturn(Exception):
                        """Exception used to return a value from a macro."""

                        def __init__(self, value: Any):
                            self.value = value
                            super().__init__()

                    def return_func(value: Any) -> None:
                        """Return function that raises an exception to stop rendering and return the value."""
                        # Convert value to appropriate type (int, float, bool, or keep as-is)
                        if isinstance(value, str) and value.strip().isdigit():
                            return_value = int(value.strip())
                        elif isinstance(value, str) and value.strip().replace(".", "", 1).isdigit():
                            return_value = float(value.strip())
                        else:
                            return_value = value
                        # Raise exception to stop rendering and return the value
                        if self.verbose:
                            logger.debug(
                                f"Macro {m_name} calling return() with {return_value} (type: {type(return_value)})"
                            )
                        raise MacroReturn(return_value)

                    # Build context: start with all globals, then override with macro args and special handlers
                    context = dict(self.env.globals)
                    # Override with macro arguments (only zip matching pairs - args may be fewer than params)
                    # This handles cases where macros have default values or are called with fewer positional args
                    context.update(dict(zip(m_params, args, strict=False)))
                    context.update(kwargs)
                    # Override with special return handler (must come after globals to take precedence)
                    context["return"] = return_func

                    # Render the macro body with the context
                    macro_template = self.env.from_string(m_body)
                    try:
                        rendered_output = macro_template.render(**context)
                        # If no return() was called, return the rendered output (normal macro behavior)
                        if self.verbose:
                            logger.debug(
                                f"Macro {m_name} rendered output (no return()): {repr(rendered_output[:50])}"
                            )
                        return rendered_output
                    except MacroReturn as e:
                        # return() was called - return the captured value instead of rendered output
                        if self.verbose:
                            logger.debug(
                                f"Macro {m_name} return() caught: {e.value} (type: {type(e.value)})"
                            )
                        return e.value
                    except Exception as e:
                        # Re-raise other exceptions, but log them
                        if self.verbose:
                            logger.debug(
                                f"Macro {m_name} raised exception: {type(e).__name__}: {e}"
                            )
                        raise

                return macro_func  # noqa: B023

            # Register the macro in the namespace
            macro_func = create_macro_func(macro_name, macro_body, parameters)
            namespace_obj[macro_name] = macro_func

            if self.verbose:
                full_name = f"{namespace}.{macro_name}" if namespace else macro_name
                logger.info(f"Registered macro {full_name} from {source}")
                if namespace:
                    logger.debug(
                        f"Namespace {namespace} now contains: {list(namespace_obj.keys())}"
                    )

    def render(self, sql_content: str, model_name: str | None = None) -> str:
        """
        Render SQL content through Jinja2 and convert to target dialect.

        Args:
            sql_content: SQL content with Jinja2 templates
            model_name: Name of the model (for context in error messages)

        Returns:
            Rendered SQL content converted to target dialect
        """
        try:
            # Create a template from the SQL content
            template = self.env.from_string(sql_content)

            # Render with context (this expands all macros)
            rendered = template.render()

            if self.verbose and model_name:
                logger.debug(f"Rendered model {model_name} through Jinja2")

            # Convert to target dialect using SQLglot (only if different from postgres)
            target_dialect_name = self._adapter_to_dialect.get(self.adapter_type, "postgres")
            if target_dialect_name == "postgres":
                # Already in target dialect, no conversion needed
                return rendered

            try:
                # Try parse_one first (faster for single statements)
                parsed = sqlglot.parse_one(rendered, read="postgres")
                converted = parsed.sql(dialect=target_dialect_name)
                if self.verbose:
                    logger.debug(
                        f"Converted SQL from postgres to {target_dialect_name} for model {model_name or 'unknown'}"
                    )
                return converted
            except Exception:
                # If parse_one fails, try parse() for multiple statements
                try:
                    parsed_statements = sqlglot.parse(rendered, read="postgres")
                    if parsed_statements:
                        converted = ";\n".join(
                            stmt.sql(dialect=target_dialect_name) for stmt in parsed_statements
                        )
                        if self.verbose:
                            logger.debug(
                                f"Converted {len(parsed_statements)} SQL statements to {target_dialect_name}"
                            )
                        return converted
                except Exception as e:
                    # If all conversion attempts fail, log warning and return original
                    logger.warning(
                        f"Failed to convert SQL to {target_dialect_name} for model {model_name or 'unknown'}: {e}. "
                        f"Returning original SQL."
                    )
                return rendered

        except Exception as e:
            error_msg = f"Error rendering Jinja2 template for model {model_name or 'unknown'}: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e
