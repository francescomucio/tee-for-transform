"""
Unit tests for CLI help behavior when commands are called without required arguments.
"""

import subprocess
import sys
from pathlib import Path


class TestCLIHelpBehavior:
    """Test that commands show help when called without required arguments."""

    def test_t4t_without_command_shows_help(self):
        """Test that 't4t' without any command shows help."""
        exit_code, stdout, stderr = self._run_command([])

        assert exit_code == 0
        output = stdout + stderr
        # Should show main help with all commands listed
        assert "Usage: t4t" in output or "t4t" in output
        assert "COMMAND" in output or "Commands" in output
        assert "build" in output.lower()
        assert "compile" in output.lower()
        assert "run" in output.lower()
        assert "test" in output.lower()

    def _run_command(self, command: list) -> tuple[int, str, str]:
        """Run a CLI command and return exit code, stdout, stderr."""
        try:
            result = subprocess.run(
                [sys.executable, "-m", "tee.cli.main"] + command,
                capture_output=True,
                text=True,
                cwd=Path(__file__).parent.parent.parent,
            )
            return result.returncode, result.stdout, result.stderr
        except Exception as e:
            return 1, "", str(e)

    def test_run_without_argument_shows_help(self):
        """Test that 't4t run' without argument shows help."""
        exit_code, stdout, stderr = self._run_command(["run"])

        assert exit_code == 0
        # Check for help content (command name and description)
        output = stdout + stderr
        assert "run" in output.lower()
        assert "PROJECT_FOLDER" in output or "project_folder" in output
        assert "Parse and execute SQL models" in output

    def test_test_without_argument_shows_help(self):
        """Test that 't4t test' without argument shows help."""
        exit_code, stdout, stderr = self._run_command(["test"])

        assert exit_code == 0
        output = stdout + stderr
        assert "test" in output.lower()
        assert "PROJECT_FOLDER" in output or "project_folder" in output

    def test_build_without_argument_shows_help(self):
        """Test that 't4t build' without argument shows help."""
        exit_code, stdout, stderr = self._run_command(["build"])

        assert exit_code == 0
        output = stdout + stderr
        assert "build" in output.lower()
        assert "PROJECT_FOLDER" in output or "project_folder" in output

    def test_seed_without_argument_shows_help(self):
        """Test that 't4t seed' without argument shows help."""
        exit_code, stdout, stderr = self._run_command(["seed"])

        assert exit_code == 0
        output = stdout + stderr
        assert "seed" in output.lower()
        assert "PROJECT_FOLDER" in output or "project_folder" in output

    def test_debug_without_argument_shows_help(self):
        """Test that 't4t debug' without argument shows help."""
        exit_code, stdout, stderr = self._run_command(["debug"])

        assert exit_code == 0
        output = stdout + stderr
        assert "debug" in output.lower()
        assert "PROJECT_FOLDER" in output or "project_folder" in output

    def test_compile_without_argument_shows_help(self):
        """Test that 't4t compile' without argument shows help."""
        exit_code, stdout, stderr = self._run_command(["compile"])

        assert exit_code == 0
        output = stdout + stderr
        assert "compile" in output.lower()
        assert "PROJECT_FOLDER" in output or "project_folder" in output

    def test_init_without_argument_shows_help(self):
        """Test that 't4t init' without argument shows help."""
        exit_code, stdout, stderr = self._run_command(["init"])

        assert exit_code == 0
        output = stdout + stderr
        assert "init" in output.lower()
        assert "project_name" in output or "PROJECT_NAME" in output

    def test_ots_without_subcommand_shows_help(self):
        """Test that 't4t ots' without subcommand shows help."""
        exit_code, stdout, stderr = self._run_command(["ots"])

        assert exit_code == 0
        output = stdout + stderr
        assert "ots" in output.lower()
        assert "run" in output.lower()
        assert "validate" in output.lower()

    def test_ots_run_without_argument_shows_help(self):
        """Test that 't4t ots run' without argument shows help."""
        exit_code, stdout, stderr = self._run_command(["ots", "run"])

        assert exit_code == 0
        output = stdout + stderr
        assert "run" in output.lower()
        assert "ots_path" in output.lower() or "OTS_PATH" in output

    def test_ots_validate_without_argument_shows_help(self):
        """Test that 't4t ots validate' without argument shows help."""
        exit_code, stdout, stderr = self._run_command(["ots", "validate"])

        assert exit_code == 0
        output = stdout + stderr
        assert "validate" in output.lower()
        assert "ots_path" in output.lower() or "OTS_PATH" in output

    def test_run_with_argument_does_not_show_help(self):
        """Test that 't4t run' with argument doesn't show help (fails with different error)."""
        # Use a non-existent project to trigger an error, but not a missing argument error
        exit_code, stdout, stderr = self._run_command(["run", "/nonexistent/project"])

        # Should not show help (exit code should not be 0 from help)
        # It should fail with a different error (project not found, etc.)
        assert exit_code != 0
        output = stdout + stderr
        # Should not be a "Missing argument" error
        assert "Missing argument" not in output
        # Should not show help usage
        assert "Usage:" not in output or "project_folder" not in output.lower()
