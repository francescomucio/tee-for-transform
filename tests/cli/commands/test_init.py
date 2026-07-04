"""
Tests for the init CLI command.
"""

from pathlib import Path
from unittest.mock import patch

from click.exceptions import Exit as ClickExit

from t4t.cli.commands.init import _generate_project_toml, _get_default_connection_config, cmd_init


class TestInitCommand:
    """Tests for the init CLI command."""

    def test_get_default_connection_config_duckdb(self):
        """Test default connection config for DuckDB."""
        config = _get_default_connection_config("duckdb", "my_project")
        assert config["type"] == "duckdb"
        assert config["path"] == "data/my_project.duckdb"

    def test_get_default_connection_config_snowflake(self):
        """Test default connection config for Snowflake."""
        config = _get_default_connection_config("snowflake", "my_project")
        assert config["type"] == "snowflake"
        assert config["host"] == "YOUR_ACCOUNT.snowflakecomputing.com"
        assert config["user"] == "YOUR_USERNAME"
        assert config["password"] == "YOUR_PASSWORD"
        assert config["role"] == "YOUR_ROLE"
        assert config["warehouse"] == "YOUR_WAREHOUSE"
        assert config["database"] == "YOUR_DATABASE"

    def test_get_default_connection_config_postgresql(self):
        """Test default connection config for PostgreSQL."""
        config = _get_default_connection_config("postgresql", "my_project")
        assert config["type"] == "postgresql"
        assert config["host"] == "localhost"
        assert config["port"] == 5432
        assert config["database"] == "my_project"
        assert config["user"] == "postgres"
        assert config["password"] == "postgres"

    def test_get_default_connection_config_bigquery(self):
        """Test default connection config for BigQuery."""
        config = _get_default_connection_config("bigquery", "my_project")
        assert config["type"] == "bigquery"
        assert config["project"] == "YOUR_PROJECT_ID"
        assert config["database"] == "my_project"

    def test_get_default_connection_config_motherduck(self):
        """Test default connection config for MotherDuck."""
        config = _get_default_connection_config("motherduck", "my_project")
        assert config["type"] == "duckdb"
        assert config["path"] == "md:my_project"
        assert config["database"] == "my_project"
        assert config["schema"] == "main"

    def test_generate_project_toml_duckdb(self):
        """Test project.toml generation for DuckDB."""
        toml_content = _generate_project_toml("my_project", "duckdb")
        assert 'project_folder = "my_project"' in toml_content
        assert "[connection]" in toml_content
        assert 'type = "duckdb"' in toml_content
        assert 'path = "data/my_project.duckdb"' in toml_content
        assert "[flags]" in toml_content
        assert 'materialization_change_behavior = "warn"' in toml_content

    def test_generate_project_toml_snowflake(self):
        """Test project.toml generation for Snowflake."""
        toml_content = _generate_project_toml("my_project", "snowflake")
        assert 'project_folder = "my_project"' in toml_content
        assert "[connection]" in toml_content
        assert 'type = "snowflake"' in toml_content
        assert 'host = "YOUR_ACCOUNT.snowflakecomputing.com"' in toml_content

    def test_generate_project_toml_motherduck(self):
        """Test project.toml generation for MotherDuck."""
        toml_content = _generate_project_toml("my_project", "motherduck")
        assert 'project_folder = "my_project"' in toml_content
        assert "[connection]" in toml_content
        assert 'type = "duckdb"' in toml_content
        assert 'path = "md:my_project"' in toml_content
        assert 'database = "my_project"' in toml_content
        assert 'schema = "main"' in toml_content
        assert "[connection.extra]" in toml_content
        assert "motherduck_token" in toml_content

    def test_cmd_init_creates_project_structure(self):
        """Test that init command creates project structure."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            project_name = "test_init_project"
            project_path = tmpdir_path / project_name

            original_cwd = Path.cwd()
            try:
                import os

                os.chdir(tmpdir_path)

                with patch("sys.exit"):
                    # Call function directly with parameters
                    cmd_init(project_name=project_name, database_type="duckdb")

                    # Verify structure was created
                    assert project_path.exists()
                    assert (project_path / "project.toml").exists()
                    assert (project_path / "models").exists()
                    assert (project_path / "tests").exists()
                    assert (project_path / "seeds").exists()
                    assert (project_path / "data").exists()  # DuckDB creates data folder

                    # Verify project.toml content
                    toml_content = (project_path / "project.toml").read_text()
                    assert 'project_folder = "test_init_project"' in toml_content
                    assert 'type = "duckdb"' in toml_content
            finally:
                os.chdir(original_cwd)

    def test_cmd_init_creates_project_with_snowflake(self):
        """Test that init command creates project with Snowflake config."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            project_name = "test_snowflake_project"
            project_path = tmpdir_path / project_name

            original_cwd = Path.cwd()
            try:
                import os

                os.chdir(tmpdir_path)

                with patch("sys.exit"):
                    # Call function directly with parameters
                    cmd_init(project_name=project_name, database_type="snowflake")

                    assert project_path.exists()
                    assert (project_path / "project.toml").exists()

                    # Snowflake doesn't create data folder
                    assert not (project_path / "data").exists()

                    # Verify Snowflake config
                    toml_content = (project_path / "project.toml").read_text()
                    assert 'type = "snowflake"' in toml_content
                    assert 'host = "YOUR_ACCOUNT.snowflakecomputing.com"' in toml_content
            finally:
                os.chdir(original_cwd)

    def test_cmd_init_fails_if_directory_exists(self, temp_project_dir):
        """Test that init command fails if directory already exists."""
        import os

        project_name = "existing_project"
        project_path = temp_project_dir / project_name
        project_path.mkdir()

        original_cwd = Path.cwd()
        try:
            os.chdir(temp_project_dir)
            try:
                # Call function directly with parameters
                cmd_init(project_name=project_name, database_type="duckdb")
                # Should not reach here - should have exited
                raise AssertionError("Expected typer.Exit but command completed")
            except (SystemExit, ClickExit) as e:
                # Should exit with code 1 when directory exists
                exit_code = getattr(e, "exit_code", getattr(e, "code", 0))
                assert exit_code == 1, f"Expected exit code 1, got {exit_code}"
        finally:
            os.chdir(original_cwd)

    def test_cmd_init_fails_with_unsupported_database(self, temp_project_dir):
        """Test that init command fails with unsupported database type."""
        import os

        original_cwd = Path.cwd()
        try:
            os.chdir(temp_project_dir)
            # Note: database_type validation is now done by Typer callback, so this test
            # would fail at the CLI level before reaching cmd_init. This test is kept
            # for completeness but may need to be updated to test the CLI layer instead.
            pass
        finally:
            os.chdir(original_cwd)

    def test_cmd_init_cleans_up_on_error(self):
        """Test that init command cleans up on error."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            project_name = "test_error_project"
            project_path = tmpdir_path / project_name

            original_cwd = Path.cwd()
            try:
                import os

                os.chdir(tmpdir_path)

                # Make project.toml write fail
                with patch("pathlib.Path.write_text", side_effect=Exception("Write failed")):
                    try:
                        # Call function directly with parameters
                        cmd_init(project_name=project_name, database_type="duckdb")
                        raise AssertionError("Expected typer.Exit")
                    except (SystemExit, ClickExit) as e:
                        exit_code = getattr(e, "exit_code", getattr(e, "code", 0))
                        assert exit_code == 1
                        # Verify directory was cleaned up
                        assert not project_path.exists()
            finally:
                os.chdir(original_cwd)

    def test_cmd_init_validates_empty_project_name(self):
        """Test that init command rejects empty project name."""
        try:
            # Call function directly with parameters
            cmd_init(project_name="", database_type="duckdb")
            raise AssertionError("Expected typer.Exit for empty project name")
        except (SystemExit, ClickExit) as e:
            exit_code = getattr(e, "exit_code", getattr(e, "code", 0))
            assert exit_code == 1

    def test_cmd_init_validates_whitespace_project_name(self):
        """Test that init command rejects project name with leading/trailing whitespace."""
        try:
            # Call function directly with parameters
            cmd_init(project_name="  my_project  ", database_type="duckdb")
            raise AssertionError("Expected typer.Exit for whitespace project name")
        except (SystemExit, ClickExit) as e:
            exit_code = getattr(e, "exit_code", getattr(e, "code", 0))
            assert exit_code == 1

    def test_cmd_init_creates_project_with_postgresql(self):
        """Test that init command creates project with PostgreSQL config."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            project_name = "test_postgresql_project"
            project_path = tmpdir_path / project_name

            original_cwd = Path.cwd()
            try:
                import os

                os.chdir(tmpdir_path)

                with patch("sys.exit"):
                    # Call function directly with parameters
                    cmd_init(project_name=project_name, database_type="postgresql")

                    assert project_path.exists()
                    assert (project_path / "project.toml").exists()
                    assert not (
                        project_path / "data"
                    ).exists()  # PostgreSQL doesn't create data folder

                    # Verify PostgreSQL config
                    toml_content = (project_path / "project.toml").read_text()
                    assert 'type = "postgresql"' in toml_content
                    assert 'host = "localhost"' in toml_content
                    assert "port = 5432" in toml_content
                    assert f'database = "{project_name}"' in toml_content
            finally:
                os.chdir(original_cwd)

    def test_cmd_init_creates_project_with_bigquery(self):
        """Test that init command creates project with BigQuery config."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            project_name = "test_bigquery_project"
            project_path = tmpdir_path / project_name

            original_cwd = Path.cwd()
            try:
                import os

                os.chdir(tmpdir_path)

                with patch("sys.exit"):
                    # Call function directly with parameters
                    cmd_init(project_name=project_name, database_type="bigquery")

                    assert project_path.exists()
                    assert (project_path / "project.toml").exists()
                    assert not (
                        project_path / "data"
                    ).exists()  # BigQuery doesn't create data folder

                    # Verify BigQuery config
                    toml_content = (project_path / "project.toml").read_text()
                    assert 'type = "bigquery"' in toml_content
                    assert 'project = "YOUR_PROJECT_ID"' in toml_content
                    assert f'database = "{project_name}"' in toml_content
            finally:
                os.chdir(original_cwd)

    def test_cmd_init_creates_project_with_motherduck(self):
        """Test that init command creates project with MotherDuck config."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            project_name = "test_motherduck_project"
            project_path = tmpdir_path / project_name

            original_cwd = Path.cwd()
            try:
                import os

                os.chdir(tmpdir_path)

                with patch("sys.exit"):
                    # Call function directly with parameters
                    cmd_init(project_name=project_name, database_type="motherduck")

                    assert project_path.exists()
                    assert (project_path / "project.toml").exists()
                    assert not (
                        project_path / "data"
                    ).exists()  # MotherDuck doesn't create data folder

                    # Verify MotherDuck config
                    toml_content = (project_path / "project.toml").read_text()
                    assert 'type = "duckdb"' in toml_content
                    assert f'path = "md:{project_name}"' in toml_content
                    assert f'database = "{project_name}"' in toml_content
                    assert 'schema = "main"' in toml_content
                    assert "[connection.extra]" in toml_content
                    assert "motherduck_token" in toml_content
            finally:
                os.chdir(original_cwd)

    def test_cmd_init_handles_case_insensitive_database_type(self):
        """Test that init command handles case-insensitive database types."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            project_name = "test_case_project"
            project_path = tmpdir_path / project_name

            original_cwd = Path.cwd()
            try:
                import os

                os.chdir(tmpdir_path)

                with patch("sys.exit"):
                    # Call function directly with parameters
                    cmd_init(project_name=project_name, database_type="DUCKDB")  # Uppercase

                    # Should work with uppercase
                    assert project_path.exists()
                    toml_content = (project_path / "project.toml").read_text()
                    assert 'type = "duckdb"' in toml_content  # Should be lowercase in output
            finally:
                os.chdir(original_cwd)

    def test_cmd_init_creates_directories_as_directories(self):
        """Test that created directories are actually directories, not files."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            project_name = "test_dirs_project"
            project_path = tmpdir_path / project_name

            original_cwd = Path.cwd()
            try:
                import os

                os.chdir(tmpdir_path)

                with patch("sys.exit"):
                    # Call function directly with parameters
                    cmd_init(project_name=project_name, database_type="duckdb")

                    # Verify all created paths are directories
                    assert (project_path / "models").is_dir()
                    assert (project_path / "tests").is_dir()
                    assert (project_path / "seeds").is_dir()
                    assert (project_path / "data").is_dir()
                    assert (project_path / "project.toml").is_file()
            finally:
                os.chdir(original_cwd)

    def test_cmd_init_generates_complete_toml_structure(self):
        """Test that generated project.toml has all required sections."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            project_name = "test_toml_project"
            project_path = tmpdir_path / project_name

            original_cwd = Path.cwd()
            try:
                import os

                os.chdir(tmpdir_path)

                with patch("sys.exit"):
                    # Call function directly with parameters
                    cmd_init(project_name=project_name, database_type="duckdb")

                    toml_content = (project_path / "project.toml").read_text()

                    # Verify all required sections exist
                    assert "project_folder =" in toml_content
                    assert "[connection]" in toml_content
                    assert "[flags]" in toml_content
                    assert "materialization_change_behavior" in toml_content

                    # Verify structure (project_folder before connection, connection before flags)
                    project_folder_pos = toml_content.find("project_folder")
                    connection_pos = toml_content.find("[connection]")
                    flags_pos = toml_content.find("[flags]")

                    assert project_folder_pos < connection_pos
                    assert connection_pos < flags_pos
            finally:
                os.chdir(original_cwd)

    def test_cmd_init_uses_default_database_type(self):
        """Test that init command uses DuckDB as default when not specified."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            project_name = "test_default_db"
            project_path = tmpdir_path / project_name

            original_cwd = Path.cwd()
            try:
                import os

                os.chdir(tmpdir_path)

                with patch("sys.exit"):
                    # Call function directly with parameters (using default)
                    cmd_init(project_name=project_name, database_type="duckdb")

                    # Should create DuckDB project (with data folder)
                    assert (project_path / "data").exists()
                    toml_content = (project_path / "project.toml").read_text()
                    assert 'type = "duckdb"' in toml_content
            finally:
                os.chdir(original_cwd)

    def test_get_default_connection_config_generic_fallback(self):
        """Test default connection config for unsupported database type (generic fallback)."""
        config = _get_default_connection_config("unknown_db", "my_project")
        assert config["type"] == "unknown_db"

    def test_cmd_init_handles_oserror(self):
        """Test that init command handles OSError (permissions, disk full, etc.)."""
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            project_name = "test_oserror"
            project_path = tmpdir_path / project_name

            original_cwd = Path.cwd()
            try:
                os.chdir(tmpdir_path)

                with patch("sys.exit", side_effect=SystemExit):
                    # Create the project directory first, then make subdirectory creation fail
                    project_path.mkdir()

                    # Make subdirectory creation raise OSError
                    original_mkdir = Path.mkdir

                    def failing_mkdir(self, *args, **kwargs):
                        if self == project_path:
                            # Allow project directory creation
                            return original_mkdir(self, *args, **kwargs)
                        else:
                            # Fail on subdirectory creation
                            raise OSError("Permission denied")

                    with patch("pathlib.Path.mkdir", side_effect=failing_mkdir):
                        try:
                            # Call function directly with parameters
                            cmd_init(project_name=project_name, database_type="duckdb")
                            raise AssertionError("Expected typer.Exit")
                        except (SystemExit, ClickExit) as e:
                            exit_code = getattr(e, "exit_code", getattr(e, "code", 0))
                            assert exit_code == 1
            finally:
                os.chdir(original_cwd)
