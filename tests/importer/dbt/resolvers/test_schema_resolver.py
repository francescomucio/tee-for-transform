"""
Tests for schema resolver.
"""

from pathlib import Path


from t4t.importer.dbt.resolvers import SchemaResolver


class TestSchemaResolver:
    """Tests for schema resolver."""

    def test_resolve_schema_default(self):
        """Test schema resolution with no configuration."""
        dbt_project = {"name": "test_project", "raw_config": {}}
        resolver = SchemaResolver(dbt_project, default_schema="public")

        model_path = Path("/path/to/models/customers.sql")
        schema = resolver.resolve_schema("customers", model_path, None)

        # Default schema when no profile is "dev"
        assert schema == "dev"

    def test_resolve_schema_from_profile(self):
        """Test schema resolution from profile schema."""
        dbt_project = {"name": "test_project", "raw_config": {}}
        resolver = SchemaResolver(dbt_project, profile_schema="analytics", default_schema="public")

        model_path = Path("/path/to/models/customers.sql")
        schema = resolver.resolve_schema("customers", model_path, None)

        assert schema == "analytics"

    def test_resolve_schema_from_folder_structure(self):
        """Test schema resolution from folder structure as fallback."""
        dbt_project = {"name": "test_project", "raw_config": {}}
        resolver = SchemaResolver(dbt_project, default_schema="public")

        # Model in staging folder
        model_path = Path("/path/to/models/staging/customers.sql")
        schema = resolver.resolve_schema("customers", model_path, None)

        # Should use folder name as fallback when no config
        assert schema == "staging"

    def test_resolve_schema_parent_folder_ignored_when_child_exists(self):
        """Test that parent folder schema is ignored when child folder has schema."""
        dbt_config = {
            "name": "test_project",
            "models": {
                "test_project": {"staging": {"+schema": "staging"}, "marts": {"+schema": "marts"}}
            },
        }
        dbt_project = {"name": "test_project", "raw_config": dbt_config}
        resolver = SchemaResolver(dbt_project, profile_schema="analytics", default_schema="public")

        # Model in marts folder (not staging)
        model_path = Path("/path/to/models/marts/customers.sql")
        schema = resolver.resolve_schema("customers", model_path, None)

        # Should use marts schema (most specific for this path), not staging
        assert schema == "analytics_marts"

    def test_resolve_schema_from_project_config_simple(self):
        """Test schema resolution from dbt_project.yml with simple folder schema."""
        dbt_config = {
            "name": "test_project",
            "models": {"test_project": {"staging": {"+schema": "staging"}}},
        }
        dbt_project = {"name": "test_project", "raw_config": dbt_config}
        resolver = SchemaResolver(dbt_project, profile_schema="analytics", default_schema="public")

        # Model in staging folder
        model_path = Path("/path/to/models/staging/customers.sql")
        schema = resolver.resolve_schema("customers", model_path, None)

        # Should combine: analytics_staging
        assert schema == "analytics_staging"

    def test_resolve_schema_from_project_config_replacement(self):
        """Test schema resolution with schema (replacement) instead of +schema."""
        dbt_config = {
            "name": "test_project",
            "models": {
                "test_project": {
                    "staging": {
                        "schema": "staging_only"  # Replaces base schema
                    }
                }
            },
        }
        dbt_project = {"name": "test_project", "raw_config": dbt_config}
        resolver = SchemaResolver(dbt_project, profile_schema="analytics", default_schema="public")

        model_path = Path("/path/to/models/staging/customers.sql")
        schema = resolver.resolve_schema("customers", model_path, None)

        # schema and +schema are aliases, both combine: analytics_staging_only
        assert schema == "analytics_staging_only"

    def test_resolve_schema_nested_folders(self):
        """Test schema resolution with nested folders - most specific wins."""
        dbt_config = {
            "name": "test_project",
            "models": {
                "test_project": {
                    "staging": {"+schema": "staging", "intermediate": {"+schema": "intermediate"}}
                }
            },
        }
        dbt_project = {"name": "test_project", "raw_config": dbt_config}
        resolver = SchemaResolver(dbt_project, profile_schema="analytics", default_schema="public")

        # Model in staging/intermediate folder
        # Most specific match is "intermediate" (not "staging")
        model_path = Path("/path/to/models/staging/intermediate/orders.sql")
        schema = resolver.resolve_schema("orders", model_path, None)

        # Should use most specific: analytics_intermediate (NOT analytics_staging_intermediate)
        assert schema == "analytics_intermediate"

    def test_resolve_schema_nested_folders_with_replacement(self):
        """Test nested folders where child uses schema (replacement) - most specific wins."""
        dbt_config = {
            "name": "test_project",
            "models": {
                "test_project": {
                    "staging": {
                        "+schema": "staging",
                        "intermediate": {
                            "schema": "intermediate_only"  # Replaces everything (not additive)
                        },
                    }
                }
            },
        }
        dbt_project = {"name": "test_project", "raw_config": dbt_config}
        resolver = SchemaResolver(dbt_project, profile_schema="analytics", default_schema="public")

        model_path = Path("/path/to/models/staging/intermediate/orders.sql")
        schema = resolver.resolve_schema("orders", model_path, None)

        # Most specific is intermediate_only, schema and +schema are aliases
        # So it combines: analytics_intermediate_only
        assert schema == "analytics_intermediate_only"

    def test_resolve_schema_model_specific(self):
        """Test model-specific schema configuration - most specific wins."""
        dbt_config = {
            "name": "test_project",
            "models": {
                "test_project": {
                    "staging": {"+schema": "staging", "customers": {"+schema": "custom"}}
                }
            },
        }
        dbt_project = {"name": "test_project", "raw_config": dbt_config}
        resolver = SchemaResolver(dbt_project, profile_schema="analytics", default_schema="public")

        model_path = Path("/path/to/models/staging/customers.sql")
        schema = resolver.resolve_schema("customers", model_path, None)

        # Model-specific schema is most specific, combines with base: analytics_custom
        # NOT analytics_staging_custom (no concatenation)
        assert schema == "analytics_custom"

    def test_resolve_schema_yaml_priority(self):
        """Test that schema.yml has priority over dbt_project.yml."""
        dbt_config = {
            "name": "test_project",
            "models": {"test_project": {"staging": {"+schema": "staging"}}},
        }
        dbt_project = {"name": "test_project", "raw_config": dbt_config}
        resolver = SchemaResolver(dbt_project, profile_schema="analytics", default_schema="public")

        # Schema metadata from schema.yml
        schema_metadata = {"config": {"+schema": "yaml_schema"}}

        model_path = Path("/path/to/models/staging/customers.sql")
        schema = resolver.resolve_schema("customers", model_path, schema_metadata)

        # YAML schema should take priority: analytics_yaml_schema
        assert schema == "analytics_yaml_schema"

    def test_resolve_schema_yaml_replacement(self):
        """Test that schema (replacement) in YAML replaces everything."""
        dbt_config = {
            "name": "test_project",
            "models": {"test_project": {"staging": {"+schema": "staging"}}},
        }
        dbt_project = {"name": "test_project", "raw_config": dbt_config}
        resolver = SchemaResolver(dbt_project, profile_schema="analytics", default_schema="public")

        # Schema metadata with replacement schema
        schema_metadata = {
            "config": {
                "schema": "yaml_only"  # Replaces everything
            }
        }

        model_path = Path("/path/to/models/staging/customers.sql")
        schema = resolver.resolve_schema("customers", model_path, schema_metadata)

        # YAML schema combines with base: analytics_yaml_only
        assert schema == "analytics_yaml_only"

    def test_resolve_schema_priority_order(self):
        """Test priority order: YAML > Project Config > Profile > Default."""
        dbt_config = {
            "name": "test_project",
            "models": {"test_project": {"staging": {"+schema": "project_schema"}}},
        }
        dbt_project = {"name": "test_project", "raw_config": dbt_config}
        resolver = SchemaResolver(
            dbt_project, profile_schema="profile_schema", default_schema="default_schema"
        )

        # No YAML metadata - should use project config
        model_path = Path("/path/to/models/staging/customers.sql")
        schema = resolver.resolve_schema("customers", model_path, None)

        # Project config combines with profile: profile_schema_project_schema
        assert schema == "profile_schema_project_schema"

    def test_resolve_schema_no_profile_uses_default(self):
        """Test that default schema is used when no profile schema."""
        dbt_config = {
            "name": "test_project",
            "models": {"test_project": {"staging": {"+schema": "staging"}}},
        }
        dbt_project = {"name": "test_project", "raw_config": dbt_config}
        resolver = SchemaResolver(dbt_project, profile_schema=None, default_schema="public")

        model_path = Path("/path/to/models/staging/customers.sql")
        schema = resolver.resolve_schema("customers", model_path, None)

        # Should combine with default: dev_staging
        assert schema == "dev_staging"

    def test_resolve_schema_project_name_extraction(self):
        """Test that project name is correctly extracted from models config."""
        dbt_config = {
            "name": "my_project",
            "models": {
                "my_project": {  # Project name as key
                    "staging": {"+schema": "staging"}
                }
            },
        }
        dbt_project = {"name": "my_project", "raw_config": dbt_config}
        resolver = SchemaResolver(dbt_project, profile_schema="analytics", default_schema="public")

        model_path = Path("/path/to/models/staging/customers.sql")
        schema = resolver.resolve_schema("customers", model_path, None)

        assert schema == "analytics_staging"

    def test_resolve_schema_direct_models_config(self):
        """Test models config without project name key."""
        dbt_config = {
            "name": "test_project",
            "models": {
                "staging": {  # Direct config, no project name
                    "+schema": "staging"
                }
            },
        }
        dbt_project = {"name": "test_project", "raw_config": dbt_config}
        resolver = SchemaResolver(dbt_project, profile_schema="analytics", default_schema="public")

        model_path = Path("/path/to/models/staging/customers.sql")
        schema = resolver.resolve_schema("customers", model_path, None)

        assert schema == "analytics_staging"

    def test_resolve_schema_complex_nested_scenario(self):
        """Test complex nested scenario with all three cases from examples."""
        dbt_config = {
            "name": "test_project",
            "models": {
                "test_project": {
                    "staging": {
                        "+schema": "staging",
                        "intermediate": {
                            "+schema": "intermediate",
                            "customers": {"+schema": "custom"},
                        },
                    }
                }
            },
        }
        dbt_project = {"name": "test_project", "raw_config": dbt_config}
        resolver = SchemaResolver(dbt_project, profile_schema="analytics", default_schema="public")

        # Case 1: Model in staging folder (uses staging schema)
        model_path_1 = Path("/path/to/models/staging/customers.sql")
        schema_1 = resolver.resolve_schema("customers", model_path_1, None)
        assert schema_1 == "analytics_staging"

        # Case 2: Model in staging/intermediate folder (uses intermediate schema)
        model_path_2 = Path("/path/to/models/staging/intermediate/orders.sql")
        schema_2 = resolver.resolve_schema("orders", model_path_2, None)
        assert schema_2 == "analytics_intermediate"

        # Case 3: Model in staging/intermediate with model-specific schema (uses custom schema)
        model_path_3 = Path("/path/to/models/staging/intermediate/customers.sql")
        schema_3 = resolver.resolve_schema("customers", model_path_3, None)
        assert schema_3 == "analytics_custom"
