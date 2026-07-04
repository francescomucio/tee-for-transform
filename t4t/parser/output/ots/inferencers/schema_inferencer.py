"""Schema inference from SQL using sqlglot."""

import logging
from typing import Any

from t4t.parser.shared.types import ParsedModel

logger = logging.getLogger(__name__)


class SchemaInferencer:
    """Infers schema from SQL queries using sqlglot."""

    def infer_from_sql(self, model_data: ParsedModel) -> dict[str, Any] | None:
        """
        Infer schema from SQL query using sqlglot.

        Args:
            model_data: Parsed model data

        Returns:
            Schema structure with inferred columns, or None if inference fails
        """
        try:
            import sqlglot

            # Get SQL from code structure
            code_data = model_data.get("code", {})
            if not code_data or "sql" not in code_data:
                return None

            sql_content = code_data["sql"].get("original_sql")
            if not sql_content:
                return None

            # Parse the SQL to extract column definitions
            expr = sqlglot.parse_one(sql_content)

            # Extract SELECT columns
            columns = []
            if hasattr(expr, "expressions"):
                for col_expr in expr.expressions:
                    if hasattr(col_expr, "alias"):
                        col_name = col_expr.alias
                    elif hasattr(col_expr, "this"):
                        col_name = (
                            col_expr.this.name
                            if hasattr(col_expr.this, "name")
                            else str(col_expr.this)
                        )
                    else:
                        col_name = str(col_expr)

                    # Try to infer datatype from column expression
                    datatype = self.infer_datatype(col_expr)

                    if col_name and col_name != "*":
                        columns.append(
                            {"name": col_name, "datatype": datatype, "description": None}
                        )

            if columns:
                return {"columns": columns, "partitioning": []}
        except Exception as e:
            logger.debug(f"Failed to infer schema from SQL: {e}")

        return None

    def infer_datatype(self, col_expr) -> str:
        """
        Infer OTS datatype from SQL column expression.

        Args:
            col_expr: SQLGlot column expression

        Returns:
            OTS datatype string
        """
        # Check for obvious type hints in the expression
        if hasattr(col_expr, "this"):
            sql_type = str(col_expr.this)

            # Simple heuristic based on SQL type
            if any(word in sql_type.upper() for word in ["TEXT", "VARCHAR", "CHAR", "STRING"]):
                return "string"
            elif any(
                word in sql_type.upper() for word in ["INT", "BIGINT", "SMALLINT", "INTEGER"]
            ) or any(
                word in sql_type.upper() for word in ["FLOAT", "DOUBLE", "DECIMAL", "NUMERIC"]
            ):
                return "number"
            elif any(word in sql_type.upper() for word in ["DATE", "TIMESTAMP", "TIME"]):
                return "date"
            elif any(word in sql_type.upper() for word in ["BOOLEAN", "BOOL"]):
                return "boolean"

        # Default to string if can't infer
        return "string"
