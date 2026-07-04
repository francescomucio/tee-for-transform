"""
Input parsers for external formats (OTS modules, etc.)
"""

from .ots_converter import OTSConverter, OTSConverterError
from .ots_integration import (
    load_ots_modules,
    merge_ots_with_parsed_functions,
    merge_ots_with_parsed_models,
)
from .ots_reader import OTSModuleReader, OTSModuleReaderError
from .ots_validator import OTSValidationError, validate_ots_module_location

__all__ = [
    "OTSModuleReader",
    "OTSModuleReaderError",
    "OTSConverter",
    "OTSConverterError",
    "load_ots_modules",
    "merge_ots_with_parsed_models",
    "merge_ots_with_parsed_functions",
    "validate_ots_module_location",
    "OTSValidationError",
]
