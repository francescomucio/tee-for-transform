"""Structured logging / CLI output for t4t.

See :mod:`t4t.observability.logging_setup` for the format registry
(``text``/``json``) and the handler wired up at CLI startup.
"""

from .logging_setup import (
    CLI_OUTPUT_LOGGER_NAMES,
    DEFAULT_LOG_FORMAT,
    FORMATTERS,
    JSONFormatter,
    TextFormatter,
    configure_logging,
)

__all__ = [
    "CLI_OUTPUT_LOGGER_NAMES",
    "DEFAULT_LOG_FORMAT",
    "FORMATTERS",
    "JSONFormatter",
    "TextFormatter",
    "configure_logging",
]
