import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import shared_helper  # noqa: E402


@model(table_name="py_model_1")  # noqa: F821
def py_model_1():
    return f"SELECT '{shared_helper.GREETING}' AS greeting"
