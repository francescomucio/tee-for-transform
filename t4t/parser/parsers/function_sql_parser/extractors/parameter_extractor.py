"""
Parameter extraction from SQLglot AST or parameter strings.
"""

import re

from sqlglot import exp

from t4t.typing.metadata import FunctionParameter


class ParameterExtractor:
    """Extracts function parameters from various sources."""

    @staticmethod
    def extract_from_udf(udf: exp.UserDefinedFunction) -> list[FunctionParameter]:
        """
        Extract parameters from SQLglot UserDefinedFunction.

        Args:
            udf: SQLglot UserDefinedFunction expression

        Returns:
            List of parameter dictionaries
        """
        parameters = []
        if hasattr(udf, "expressions") and udf.expressions:
            for expr in udf.expressions:
                if isinstance(expr, exp.ColumnDef):
                    param: FunctionParameter = {
                        "name": "",
                        "type": "",
                    }

                    # Extract parameter name
                    if hasattr(expr, "this") and expr.this:
                        if isinstance(expr.this, exp.Identifier):
                            param["name"] = (
                                expr.this.name if hasattr(expr.this, "name") else str(expr.this)
                            )
                        else:
                            param["name"] = str(expr.this)

                    # Extract parameter type
                    if hasattr(expr, "kind") and expr.kind:
                        if hasattr(expr.kind, "this"):
                            type_val = expr.kind.this
                            # Handle Type enum
                            if hasattr(type_val, "name"):
                                param["type"] = type_val.name.upper()
                            elif hasattr(type_val, "value"):
                                param["type"] = str(type_val.value).upper()
                            else:
                                param["type"] = str(type_val).upper()
                        else:
                            param["type"] = str(expr.kind).upper()

                    if param["name"]:
                        parameters.append(param)

        return parameters

    @staticmethod
    def extract_from_string(params_str: str) -> list[FunctionParameter]:
        """
        Parse function parameters from parameter string.

        Args:
            params_str: Parameter string (e.g., "x FLOAT, y INTEGER DEFAULT 0")

        Returns:
            List of parameter dictionaries
        """
        if not params_str or not params_str.strip():
            return []

        parameters = []
        # Split by comma, but be careful with nested parentheses
        param_parts = ParameterExtractor._split_parameters(params_str)

        for param_str in param_parts:
            param_str = param_str.strip()
            if not param_str:
                continue

            param: FunctionParameter = {
                "name": "",
                "type": "",
            }

            # Check for mode (IN, OUT, INOUT)
            mode_match = re.match(r"^(IN|OUT|INOUT)\s+", param_str, re.IGNORECASE)
            if mode_match:
                param["mode"] = mode_match.group(1).upper()
                param_str = param_str[len(mode_match.group(0)) :].strip()

            # Split by spaces to get name and type
            parts = param_str.split(None, 2)
            if len(parts) >= 2:
                param["name"] = parts[0]
                param["type"] = parts[1]

                # Check for DEFAULT
                if len(parts) > 2:
                    default_match = re.search(r"DEFAULT\s+(.+)", parts[2], re.IGNORECASE)
                    if default_match:
                        param["default"] = default_match.group(1).strip()

            if param["name"]:
                parameters.append(param)

        return parameters

    @staticmethod
    def _split_parameters(params_str: str) -> list[str]:
        """
        Split parameter string by commas, handling nested parentheses.

        Args:
            params_str: Parameter string

        Returns:
            List of parameter strings
        """
        parts = []
        current = ""
        depth = 0

        for char in params_str:
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            elif char == "," and depth == 0:
                parts.append(current)
                current = ""
                continue
            current += char

        if current:
            parts.append(current)

        return parts
