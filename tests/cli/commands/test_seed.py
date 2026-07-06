"""
Tests for the seed CLI command.
"""

import contextlib
from unittest.mock import MagicMock, patch

from click.exceptions import Exit as ClickExit

from t4t.cli.commands.seed import cmd_seed


class TestSeedCommand:
    """Tests for the seed CLI command."""

    def test_cmd_seed_no_seeds_folder(self, temp_project_dir):
        """Test seed command when seeds folder doesn't exist."""
        # Create project.toml file (required by CommandContext)
        project_toml = temp_project_dir / "project.toml"
        project_toml.write_text(
            'project_folder = "test"\n[environments.dev.connection]\ntype = "duckdb"\npath = ":memory:"'
        )

        # Should not raise, just print message
        cmd_seed(
            project_folder=str(temp_project_dir),
            vars=None,
            verbose=False,
        )

    def test_cmd_seed_empty_seeds_folder(self, temp_project_dir):
        """Test seed command when seeds folder is empty."""
        # Create project.toml file (required by CommandContext)
        project_toml = temp_project_dir / "project.toml"
        project_toml.write_text(
            'project_folder = "test"\n[environments.dev.connection]\ntype = "duckdb"\npath = ":memory:"'
        )

        seeds_folder = temp_project_dir / "seeds"
        seeds_folder.mkdir()

        # Should not raise, just print message
        cmd_seed(
            project_folder=str(temp_project_dir),
            vars=None,
            verbose=False,
        )

    @patch("t4t.cli.commands.seed.CommandContext")
    @patch("t4t.cli.commands.seed.ExecutionEngine")
    def test_cmd_seed_loads_seeds(self, mock_engine_class, mock_context_class, temp_project_dir):
        """Test seed command loads seeds successfully."""
        seeds_folder = temp_project_dir / "seeds"
        seeds_folder.mkdir()

        # Create a seed file
        csv_file = seeds_folder / "users.csv"
        csv_file.write_text("id,name\n1,Alice\n")

        # Mock the context
        mock_context = MagicMock()
        mock_context.project_path = temp_project_dir
        mock_context.config = {"connection": {"type": "duckdb", "path": ":memory:"}}
        mock_context.vars = {}
        mock_context.handle_error = MagicMock()
        mock_context_class.return_value = mock_context

        # Mock the execution engine
        mock_engine = MagicMock()
        mock_adapter = MagicMock()
        mock_adapter.config.type = "duckdb"
        mock_adapter.get_table_info.return_value = {"row_count": 1}
        mock_engine.adapter = mock_adapter
        mock_engine_class.return_value = mock_engine

        # Should execute without error
        cmd_seed(
            project_folder=str(temp_project_dir),
            vars=None,
            verbose=False,
        )

        # Verify engine was created and connected
        mock_engine_class.assert_called_once()
        mock_engine.connect.assert_called_once()
        mock_engine.disconnect.assert_called_once()

    def test_cmd_seed_handles_errors(self, temp_project_dir):
        """Test seed command handles errors gracefully."""
        # Create project.toml file (required by CommandContext)
        project_toml = temp_project_dir / "project.toml"
        project_toml.write_text(
            'project_folder = "test"\n[environments.dev.connection]\ntype = "duckdb"\npath = ":memory:"'
        )

        seeds_folder = temp_project_dir / "seeds"
        seeds_folder.mkdir()

        # Create a seed file
        csv_file = seeds_folder / "users.csv"
        csv_file.write_text("id,name\n1,Alice\n")

        # Make ExecutionEngine raise an error during initialization
        with patch("t4t.cli.commands.seed.ExecutionEngine") as mock_engine_class:
            mock_engine_class.side_effect = Exception("Connection failed")

            # Should handle error gracefully: CommandContext.handle_error raises
            # typer.Exit(1) which is click.exceptions.Exit
            with contextlib.suppress(SystemExit, ClickExit):
                cmd_seed(
                    project_folder=str(temp_project_dir),
                    vars=None,
                    verbose=False,
                )

    @patch("t4t.cli.commands.seed.SeedLoader")
    @patch("t4t.cli.commands.seed.SeedDiscovery")
    @patch("t4t.cli.commands.seed.CommandContext")
    @patch("t4t.cli.commands.seed.ExecutionEngine")
    def test_cmd_seed_with_schema(
        self,
        mock_engine_class,
        mock_context_class,
        mock_discovery_class,
        mock_loader_class,
        temp_project_dir,
    ):
        """Test seed command with seeds in schema subdirectories."""
        # Create project.toml file
        project_toml = temp_project_dir / "project.toml"
        project_toml.write_text(
            'project_folder = "test"\n[environments.dev.connection]\ntype = "duckdb"\npath = ":memory:"'
        )

        seeds_folder = temp_project_dir / "seeds"
        seeds_folder.mkdir()
        schema_folder = seeds_folder / "my_schema"
        schema_folder.mkdir()

        # Create seed file in schema folder
        csv_file = schema_folder / "orders.csv"
        csv_file.write_text("id,amount\n1,100\n")

        # Mock context
        mock_context = MagicMock()
        mock_context.project_path = temp_project_dir
        mock_context.config = {"connection": {"type": "duckdb", "path": ":memory:"}}
        mock_context.vars = {}
        mock_context_class.return_value = mock_context

        # Mock seed discovery
        mock_discovery = MagicMock()
        seed_files = [(csv_file, "my_schema")]
        mock_discovery.discover_seed_files.return_value = seed_files
        mock_discovery_class.return_value = mock_discovery

        # Mock execution engine
        mock_engine = MagicMock()
        mock_adapter = MagicMock()
        mock_adapter.config.type = "duckdb"
        mock_adapter.get_table_info.return_value = {"row_count": 1}
        mock_engine.adapter = mock_adapter
        mock_engine_class.return_value = mock_engine

        # Mock seed loader
        mock_loader = MagicMock()
        mock_loader.load_all_seeds.return_value = {
            "loaded_tables": ["my_schema.orders"],
            "failed_tables": [],
        }
        mock_loader_class.return_value = mock_loader

        from io import StringIO

        with patch("sys.stdout", new=StringIO()) as fake_out:
            cmd_seed(
                project_folder=str(temp_project_dir),
                vars=None,
                verbose=False,
            )

        output = fake_out.getvalue()
        assert "my_schema.orders" in output

    @patch("t4t.cli.commands.seed.SeedLoader")
    @patch("t4t.cli.commands.seed.SeedDiscovery")
    @patch("t4t.cli.commands.seed.CommandContext")
    @patch("t4t.cli.commands.seed.ExecutionEngine")
    def test_cmd_seed_with_failures(
        self,
        mock_engine_class,
        mock_context_class,
        mock_discovery_class,
        mock_loader_class,
        temp_project_dir,
    ):
        """Test seed command with some failed seeds."""
        # Create project.toml file
        project_toml = temp_project_dir / "project.toml"
        project_toml.write_text(
            'project_folder = "test"\n[environments.dev.connection]\ntype = "duckdb"\npath = ":memory:"'
        )

        seeds_folder = temp_project_dir / "seeds"
        seeds_folder.mkdir()

        csv_file = seeds_folder / "users.csv"
        csv_file.write_text("id,name\n1,Alice\n")

        # Mock context
        mock_context = MagicMock()
        mock_context.project_path = temp_project_dir
        mock_context.config = {"connection": {"type": "duckdb", "path": ":memory:"}}
        mock_context.vars = {}
        mock_context_class.return_value = mock_context

        # Mock seed discovery
        mock_discovery = MagicMock()
        mock_discovery.discover_seed_files.return_value = [(csv_file, None)]
        mock_discovery_class.return_value = mock_discovery

        # Mock execution engine
        mock_engine = MagicMock()
        mock_adapter = MagicMock()
        mock_adapter.config.type = "duckdb"
        mock_engine.adapter = mock_adapter
        mock_engine_class.return_value = mock_engine

        # Mock seed loader with failures
        mock_loader = MagicMock()
        mock_loader.load_all_seeds.return_value = {
            "loaded_tables": ["users"],
            "failed_tables": [{"file": "bad.csv", "error": "Invalid format"}],
        }
        mock_loader_class.return_value = mock_loader

        from io import StringIO

        # Capture both stdout and stderr (typer.echo with err=True writes to stderr)
        with (
            patch("sys.stdout", new=StringIO()) as fake_out,
            patch("sys.stderr", new=StringIO()) as fake_err,
        ):
            cmd_seed(
                project_folder=str(temp_project_dir),
                vars=None,
                verbose=False,
            )

        output = fake_out.getvalue() + fake_err.getvalue()
        assert "Failed to load" in output
        assert "bad.csv" in output

    @patch("t4t.cli.commands.seed.SeedLoader")
    @patch("t4t.cli.commands.seed.SeedDiscovery")
    @patch("t4t.cli.commands.seed.CommandContext")
    @patch("t4t.cli.commands.seed.ExecutionEngine")
    def test_cmd_seed_table_info_exception(
        self,
        mock_engine_class,
        mock_context_class,
        mock_discovery_class,
        mock_loader_class,
        temp_project_dir,
    ):
        """Test seed command when getting table info raises exception."""
        # Create project.toml file
        project_toml = temp_project_dir / "project.toml"
        project_toml.write_text(
            'project_folder = "test"\n[environments.dev.connection]\ntype = "duckdb"\npath = ":memory:"'
        )

        seeds_folder = temp_project_dir / "seeds"
        seeds_folder.mkdir()

        csv_file = seeds_folder / "users.csv"
        csv_file.write_text("id,name\n1,Alice\n")

        # Mock context
        mock_context = MagicMock()
        mock_context.project_path = temp_project_dir
        mock_context.config = {"connection": {"type": "duckdb", "path": ":memory:"}}
        mock_context.vars = {}
        mock_context_class.return_value = mock_context

        # Mock seed discovery
        mock_discovery = MagicMock()
        mock_discovery.discover_seed_files.return_value = [(csv_file, None)]
        mock_discovery_class.return_value = mock_discovery

        # Mock execution engine with adapter that raises on get_table_info
        mock_engine = MagicMock()
        mock_adapter = MagicMock()
        mock_adapter.config.type = "duckdb"
        mock_adapter.get_table_info.side_effect = Exception("Table not found")
        mock_engine.adapter = mock_adapter
        mock_engine_class.return_value = mock_engine

        # Mock seed loader
        mock_loader = MagicMock()
        mock_loader.load_all_seeds.return_value = {"loaded_tables": ["users"], "failed_tables": []}
        mock_loader_class.return_value = mock_loader

        from io import StringIO

        with patch("sys.stdout", new=StringIO()) as fake_out:
            cmd_seed(
                project_folder=str(temp_project_dir),
                vars=None,
                verbose=False,
            )

        output = fake_out.getvalue()
        assert "could not get row count" in output
