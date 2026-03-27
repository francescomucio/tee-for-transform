"""
CLI command implementations.
"""

from tee.cli.commands.build import cmd_build
from tee.cli.commands.compile import cmd_compile
from tee.cli.commands.debug import cmd_debug
from tee.cli.commands.docs import cmd_docs
from tee.cli.commands.generate_lookups import cmd_generate_lookups
from tee.cli.commands.help import cmd_help
from tee.cli.commands.import_cmd import cmd_import
from tee.cli.commands.init import cmd_init
from tee.cli.commands.run import cmd_run
from tee.cli.commands.seed import cmd_seed
from tee.cli.commands.test import cmd_test

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
