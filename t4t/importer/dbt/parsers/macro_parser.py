"""
Macro parser for dbt projects.

Discovers and parses dbt macros from the macros/ directory.
"""

import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class MacroParser:
    """Parses dbt macros from macro files."""

    def __init__(self, verbose: bool = False) -> None:
        """
        Initialize macro parser.

        Args:
            verbose: Enable verbose logging
        """
        self.verbose = verbose

    def discover_macros(
        self, project_path: Path, macro_paths: list[str] | None = None
    ) -> dict[str, Path]:
        """
        Discover all macro files in the dbt project.

        Args:
            project_path: Path to the dbt project root
            macro_paths: List of macro paths from dbt_project.yml (default: ["macros"])

        Returns:
            Dictionary mapping macro file paths (relative to project) to full Path objects
        """
        macro_paths = macro_paths or ["macros"]
        macro_files = {}

        for macro_path_str in macro_paths:
            macro_path = project_path / macro_path_str

            if not macro_path.exists():
                if self.verbose:
                    logger.debug(f"Macro path does not exist: {macro_path}")
                continue

            # Recursively find all .sql files
            for sql_file in macro_path.rglob("*.sql"):
                # Skip files in test directories or other special directories
                if self._should_skip_file(sql_file):
                    continue

                # Get relative path from project root
                rel_path = sql_file.relative_to(project_path)
                macro_files[str(rel_path)] = sql_file

        logger.info(f"Discovered {len(macro_files)} macro files")
        return macro_files

    def parse_macro_file(self, macro_file: Path) -> list[dict[str, Any]]:
        """
        Parse a macro file and extract macro definitions.

        Args:
            macro_file: Path to the macro file

        Returns:
            List of macro definitions, each containing:
            - name: Macro name
            - parameters: List of parameter names
            - body: Macro body (SQL/Jinja)
            - adapter_specific: True if this is an adapter-specific macro (e.g., postgres__macro_name)
            - adapter: Adapter name if adapter-specific (e.g., "postgres")
        """
        content = macro_file.read_text(encoding="utf-8")
        macros = []

        # Pattern to match macro definitions
        # {% macro macro_name(param1, param2) -%} ... {%- endmacro %}
        # Handle both {%- endmacro %} and {% endmacro %}
        # Also handle {%- macro ... -%} syntax
        macro_pattern = r"\{\%\s*[-]?\s*macro\s+(\w+)\s*\(([^)]*)\)\s*[-]?\s*\%\}(.*?)\{\%\s*[-]?\s*endmacro\s*[-]?\s*\%\}"
        matches = re.finditer(macro_pattern, content, re.DOTALL | re.IGNORECASE)

        for match in matches:
            macro_name = match.group(1)
            params_str = match.group(2).strip()
            macro_body = match.group(3).strip()

            # Parse parameters
            parameters = []
            if params_str:
                # Split by comma and clean up
                for param in params_str.split(","):
                    param = param.strip()
                    # Remove default values if present
                    if "=" in param:
                        param = param.split("=")[0].strip()
                    parameters.append(param)

            # Check if this is an adapter-specific macro
            adapter_specific = False
            adapter = None
            if "__" in macro_name:
                parts = macro_name.split("__", 1)
                if len(parts) == 2:
                    adapter = parts[0]
                    adapter_specific = True
                    # The actual macro name is the second part
                    base_macro_name = parts[1]
                else:
                    base_macro_name = macro_name
            else:
                base_macro_name = macro_name

            macros.append(
                {
                    "name": macro_name,
                    "base_name": base_macro_name,
                    "parameters": parameters,
                    "body": macro_body,
                    "adapter_specific": adapter_specific,
                    "adapter": adapter,
                    "file": str(macro_file),
                }
            )

            if self.verbose:
                logger.debug(
                    f"Parsed macro {macro_name} from {macro_file} "
                    f"(adapter: {adapter}, params: {parameters})"
                )

        return macros

    def parse_all_macros(self, macro_files: dict[str, Path]) -> dict[str, list[dict[str, Any]]]:
        """
        Parse all macro files and return a dictionary of macro definitions.

        Args:
            macro_files: Dictionary mapping relative paths to macro files

        Returns:
            Dictionary mapping macro names to lists of macro definitions
            (multiple definitions for adapter-specific versions)
        """
        all_macros: dict[str, list[dict[str, Any]]] = {}

        for rel_path, macro_file in macro_files.items():
            try:
                macros = self.parse_macro_file(macro_file)
                for macro in macros:
                    macro_name = macro["name"]
                    if macro_name not in all_macros:
                        all_macros[macro_name] = []
                    all_macros[macro_name].append(macro)
            except Exception as e:
                logger.warning(f"Error parsing macro file {rel_path}: {e}")

        logger.info(f"Parsed {sum(len(m) for m in all_macros.values())} macro definitions")
        return all_macros

    def _should_skip_file(self, file_path: Path) -> bool:
        """
        Determine if a file should be skipped.

        Args:
            file_path: Path to the file

        Returns:
            True if file should be skipped
        """
        # Skip files in common test/exclude directories
        skip_dirs = {"__pycache__", ".git", "target", "dbt_packages", ".dbt"}
        parts = file_path.parts

        return any(part in skip_dirs for part in parts)
