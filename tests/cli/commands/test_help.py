"""
Tests for the help CLI command.
"""

from io import StringIO
from unittest.mock import Mock, patch


from t4t.cli.commands.help import cmd_help


class TestHelpCommand:
    """Tests for the help CLI command."""

    def test_cmd_help(self):
        """Test help command shows same output as --help."""
        # Create a mock context with parent context
        mock_parent_ctx = Mock()
        mock_parent_ctx.get_help.return_value = """Usage: t4t [OPTIONS] COMMAND [ARGS]...

t4t - T(ee) for Transform (and t-shirts!)

╭─ Commands ────────────────────────────────────────────────────────────────────╮
│ build     Build models with tests (stops on test failure).                   │
│ compile   Compile t4t project to OTS modules.                                │
│ help      Show help information.                                             │
╰──────────────────────────────────────────────────────────────────────────────╯"""

        mock_ctx = Mock()
        mock_ctx.parent = mock_parent_ctx

        # Capture stdout
        with patch("sys.stdout", new=StringIO()) as fake_out:
            cmd_help(mock_ctx)

        output = fake_out.getvalue()
        # Verify it shows the help output (same as --help)
        assert "Usage: t4t [OPTIONS] COMMAND [ARGS]..." in output
        assert "t4t - T(ee) for Transform (and t-shirts!)" in output
        assert "Commands" in output
        assert "build" in output
        assert "compile" in output
        assert "help" in output
        # Verify parent context's get_help was called
        mock_parent_ctx.get_help.assert_called_once()
