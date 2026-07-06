"""
Compact examples showing two approaches to detect metadata-only Python files.
"""

import ast
from pathlib import Path

# ============================================================================
# OPTION A: Execute first, then check what was registered
# ============================================================================


def detect_metadata_only_option_a(file_path: Path, content: str) -> bool:
    """
    Execute file, check if models were registered.
    If no models registered but metadata exists → metadata-only
    """
    namespace = {}
    models_registered = []

    # Track model registrations
    def track_model(*args, **kwargs):
        models_registered.append(True)
        return lambda f: f

    namespace["model"] = track_model
    namespace["create_model"] = lambda *args, **kwargs: models_registered.append(True)

    # Execute the file
    exec(content, namespace)

    # Check: no models registered but metadata exists
    has_metadata = "metadata" in namespace
    no_models = len(models_registered) == 0

    return has_metadata and no_models


# ============================================================================
# OPTION B: AST detection before execution
# ============================================================================


def detect_metadata_only_option_b(content: str) -> bool:
    """
    Use AST to detect: has metadata variable but no @model or create_model()
    """
    tree = ast.parse(content)

    has_metadata_var = False
    has_model_decorator = False
    has_create_model_call = False

    for node in ast.walk(tree):
        # Check for metadata variable
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "metadata":
                    has_metadata_var = True

        # Check for @model decorator
        if isinstance(node, ast.FunctionDef):
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Name) and decorator.id == "model":
                    has_model_decorator = True
                elif isinstance(decorator, ast.Call):
                    if isinstance(decorator.func, ast.Name) and decorator.func.id == "model":
                        has_model_decorator = True

        # Check for create_model() calls
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "create_model":
                has_create_model_call = True

    # Metadata-only: has metadata but no models
    return has_metadata_var and not has_model_decorator and not has_create_model_call


# ============================================================================
# EXAMPLE FILES
# ============================================================================

# Example 1: Metadata-only file (should be detected)
metadata_only_file = """
metadata = {
    "description": "My table",
    "schema": []
}
"""

# Example 2: File with @model (should NOT be detected as metadata-only)
model_file = """
def model(*args, **kwargs):
    return lambda f: f

@model(table_name="my_table")
def create_my_table():
    return "SELECT * FROM source"
"""

# Example 3: File with create_model (should NOT be detected as metadata-only)
create_model_file = """
def create_model(*args, **kwargs):
    pass

create_model(
    table_name="my_table",
    sql="SELECT * FROM source"
)
"""

# Test
if __name__ == "__main__":
    print("Option A (execute first):")
    print(f"  metadata_only: {detect_metadata_only_option_a(Path('test.py'), metadata_only_file)}")
    print(f"  model_file: {detect_metadata_only_option_a(Path('test.py'), model_file)}")
    print(
        f"  create_model_file: {detect_metadata_only_option_a(Path('test.py'), create_model_file)}"
    )

    print("\nOption B (AST first):")
    print(f"  metadata_only: {detect_metadata_only_option_b(metadata_only_file)}")
    print(f"  model_file: {detect_metadata_only_option_b(model_file)}")
    print(f"  create_model_file: {detect_metadata_only_option_b(create_model_file)}")
