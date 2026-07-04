"""
CLI command implementations.
"""

from t4t.cli.commands.build import cmd_build
from t4t.cli.commands.compile import cmd_compile
from t4t.cli.commands.debug import cmd_debug
from t4t.cli.commands.docs import cmd_docs
from t4t.cli.commands.generate_lookups import cmd_generate_lookups
from t4t.cli.commands.help import cmd_help
from t4t.cli.commands.import_cmd import cmd_import
from t4t.cli.commands.init import cmd_init
from t4t.cli.commands.run import cmd_run
from t4t.cli.commands.seed import cmd_seed
from t4t.cli.commands.test import cmd_test

__all__ = [
    "cmd_run",
    "cmd_test",
    "cmd_debug",
    "cmd_help",
    "cmd_build",
    "cmd_seed",
    "cmd_init",
    "cmd_compile",
    "cmd_import",
    "cmd_docs",
    "cmd_generate_lookups",
]
