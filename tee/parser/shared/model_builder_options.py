"""
Three streamlined options for model building - just import and define metadata.

OPTION 1: Auto-executing class (cleanest, recommended)
    from tee.parser.shared.model_builder_options import ModelBuilder
    from tee.typing import ModelMetadata

    metadata: ModelMetadata = {...}
    ModelBuilder()  # Auto-executes when script is run as main

OPTION 2: Decorator pattern
    from tee.parser.shared.model_builder_options import model
    from tee.typing import ModelMetadata

    @model
    metadata: ModelMetadata = {...}

OPTION 3: Import hook (most automatic)
    from tee.parser.shared.model_builder_options import *
    from tee.typing import ModelMetadata

    metadata: ModelMetadata = {...}
    # Automatically executes via import hook
"""

import atexit
import os

from tee.typing import Model, ModelMetadata

from .model_builder import build_and_print_model

# ============================================================================
# OPTION 1: Auto-executing class (RECOMMENDED)
# ============================================================================
# Usage:
#   from tee.parser.shared.model_builder_options import ModelBuilder
#   from tee.typing import ModelMetadata
#
#   metadata: ModelMetadata = {...}
#   ModelBuilder()  # That's it!


class ModelBuilder:
    """
    Auto-executing class that builds model from 'metadata' variable.

    Simply instantiate this class at module level and it will automatically
    find the 'metadata' variable and build the model when script is run as main.

    Usage:
        from tee.parser.shared.model_builder_options import ModelBuilder
        from tee.typing import ModelMetadata

        metadata: ModelMetadata = {...}
        ModelBuilder()  # Auto-executes
    """

    def __init__(self, metadata: ModelMetadata | None = None):
        """
        Initialize ModelBuilder.

        Args:
            metadata: Optional metadata dict. If not provided, looks for 'metadata' in caller's namespace.
        """
        import inspect

        frame = inspect.currentframe()
        if not frame or not frame.f_back:
            return

        caller_globals = frame.f_back.f_globals
        caller_name = caller_globals.get("__name__")

        # Only execute if we're in __main__ context
        if caller_name != "__main__":
            return

        # Use provided metadata or look for it in caller's namespace
        if metadata is None:
            if "metadata" not in caller_globals:
                return
            metadata = caller_globals["metadata"]

        if not isinstance(metadata, dict):
            return

        file_path = caller_globals.get("__file__")
        if not file_path:
            return

        build_and_print_model(metadata, file_path=os.path.abspath(file_path))


# ============================================================================
# OPTION 2: Function call pattern (simplest)
# ============================================================================
# Usage:
#   from tee.parser.shared.model_builder_options import build
#   from tee.typing import ModelMetadata
#
#   metadata: ModelMetadata = {...}
#   build()  # Finds metadata automatically


def build() -> Model | None:
    """
    Automatically find 'metadata' variable and build model.

    Simply call build() after defining metadata - it will find it automatically.

    Usage:
        from tee.parser.shared.model_builder_options import build
        from tee.typing import ModelMetadata

        metadata: ModelMetadata = {...}
        build()  # Finds metadata automatically
    """
    import inspect

    frame = inspect.currentframe()
    if not frame or not frame.f_back:
        return None

    caller_globals = frame.f_back.f_globals
    caller_name = caller_globals.get("__name__")

    # Only execute if we're in __main__ context
    if caller_name != "__main__":
        return None

    # Look for metadata in caller's namespace
    if "metadata" not in caller_globals:
        return None

    metadata = caller_globals["metadata"]
    if not isinstance(metadata, dict):
        return None

    file_path = caller_globals.get("__file__")
    if not file_path:
        return None

    return build_and_print_model(metadata, file_path=os.path.abspath(file_path))


# ============================================================================
# OPTION 3: Import hook with delayed execution
# ============================================================================
# Usage:
#   from tee.parser.shared.model_builder_options import setup_auto_build
#   setup_auto_build()
#   from tee.typing import ModelMetadata
#
#   metadata: ModelMetadata = {...}
#   # Automatically executes at module end


def setup_auto_build() -> None:
    """
    Set up automatic model building that executes at module end.

    Call this at the top of your file, then just define metadata.
    The model will be built automatically when the module finishes loading.

    Usage:
        from tee.parser.shared.model_builder_options import setup_auto_build
        setup_auto_build()
        from tee.typing import ModelMetadata

        metadata: ModelMetadata = {...}
        # Auto-executes
    """
    import inspect

    frame = inspect.currentframe()
    if not frame or not frame.f_back:
        return

    caller_globals = frame.f_back.f_globals
    caller_name = caller_globals.get("__name__")

    # Only execute if we're in __main__ context
    if caller_name != "__main__":
        return

    # Register a function to execute after module loads
    def _build_at_end():
        if "metadata" in caller_globals:
            metadata = caller_globals["metadata"]
            if isinstance(metadata, dict):
                file_path = caller_globals.get("__file__")
                if file_path:
                    build_and_print_model(metadata, file_path=os.path.abspath(file_path))

    # Use atexit to run after module execution
    atexit.register(_build_at_end)

    # Also try to execute immediately if metadata already exists
    # (in case setup_auto_build is called after metadata definition)
    if "metadata" in caller_globals:
        _build_at_end()
