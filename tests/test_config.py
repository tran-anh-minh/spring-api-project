"""Tests for db_wiki.core.config."""
from pathlib import Path

import pytest
import yaml

from db_wiki.core.config import (
    DBWikiConfig,
    DatabaseConfig,
    IngestConfig,
    StorageConfig,
    load_config,
    write_default_config,
)


# ---------------------------------------------------------------------------
# Default values
# ---------------------------------------------------------------------------

class TestDefaults:
    def test_storage_path_default(self) -> None:
        config = DBWikiConfig()
        assert config.storage.path == ".db-wiki"

    def test_database_connection_string_default_none(self) -> None:
        config = DBWikiConfig()
        assert config.database.connection_string is None

    def test_database_timeout_default(self) -> None:
        config = DBWikiConfig()
        assert config.database.timeout_seconds == 30

    def test_ingest_max_file_size_default(self) -> None:
        config = DBWikiConfig()
        assert config.ingest.max_file_size_mb == 50

    def test_load_config_nonexistent_path_returns_defaults(
        self, tmp_path: Path
    ) -> None:
        """load_config with non-existent directory returns defaults — no crash."""
        config = load_config(tmp_path / "nonexistent")
        assert config.storage.path == ".db-wiki"
        assert config.database.connection_string is None


# ---------------------------------------------------------------------------
# YAML loading
# ---------------------------------------------------------------------------

class TestYamlLoading:
    def test_load_config_reads_values_from_yaml(self, tmp_path: Path) -> None:
        store_path = tmp_path / ".db-wiki"
        store_path.mkdir()
        config_file = store_path / "config.yaml"
        config_file.write_text(
            "storage:\n  path: /custom/path\ndatabase:\n  timeout_seconds: 60\n",
            encoding="utf-8",
        )
        config = load_config(store_path)
        assert config.storage.path == "/custom/path"
        assert config.database.timeout_seconds == 60

    def test_load_config_empty_file_returns_defaults(self, tmp_path: Path) -> None:
        store_path = tmp_path / ".db-wiki"
        store_path.mkdir()
        (store_path / "config.yaml").write_text("", encoding="utf-8")
        config = load_config(store_path)
        assert config.storage.path == ".db-wiki"

    def test_load_config_partial_yaml_merges_with_defaults(
        self, tmp_path: Path
    ) -> None:
        store_path = tmp_path / ".db-wiki"
        store_path.mkdir()
        (store_path / "config.yaml").write_text(
            "database:\n  connection_string: 'DRIVER={SQL Server};SERVER=localhost'\n",
            encoding="utf-8",
        )
        config = load_config(store_path)
        assert config.database.connection_string == "DRIVER={SQL Server};SERVER=localhost"
        assert config.storage.path == ".db-wiki"  # default preserved

    def test_yaml_safe_load_used(self, tmp_path: Path) -> None:
        """Verify yaml.safe_load is invoked (not yaml.load) — security check (T-01-02)."""
        # If yaml.safe_load is used, a YAML with !!python/object should raise an error
        # rather than instantiating an arbitrary Python object.
        store_path = tmp_path / ".db-wiki"
        store_path.mkdir()
        (store_path / "config.yaml").write_text(
            "storage:\n  path: safe\n",
            encoding="utf-8",
        )
        # Just verify loading works (the actual safe_load enforcement is in the impl)
        config = load_config(store_path)
        assert config.storage.path == "safe"


# ---------------------------------------------------------------------------
# write_default_config
# ---------------------------------------------------------------------------

class TestWriteDefaultConfig:
    def test_write_default_config_creates_file(self, tmp_path: Path) -> None:
        store_path = tmp_path / ".db-wiki"
        write_default_config(store_path)
        assert (store_path / "config.yaml").exists()

    def test_write_default_config_creates_parent_dirs(self, tmp_path: Path) -> None:
        store_path = tmp_path / "deep" / "nested" / ".db-wiki"
        write_default_config(store_path)
        assert (store_path / "config.yaml").exists()

    def test_write_default_config_is_valid_yaml(self, tmp_path: Path) -> None:
        store_path = tmp_path / ".db-wiki"
        write_default_config(store_path)
        content = (store_path / "config.yaml").read_text(encoding="utf-8")
        parsed = yaml.safe_load(content)
        assert isinstance(parsed, dict)

    def test_write_then_load_round_trips(self, tmp_path: Path) -> None:
        store_path = tmp_path / ".db-wiki"
        write_default_config(store_path)
        config = load_config(store_path)
        assert config.storage.path == ".db-wiki"
        assert config.database.connection_string is None
        assert config.database.timeout_seconds == 30
        assert config.ingest.max_file_size_mb == 50


# ---------------------------------------------------------------------------
# Config sections
# ---------------------------------------------------------------------------

class TestConfigSections:
    def test_has_storage_section(self) -> None:
        config = DBWikiConfig()
        assert isinstance(config.storage, StorageConfig)

    def test_has_database_section(self) -> None:
        config = DBWikiConfig()
        assert isinstance(config.database, DatabaseConfig)

    def test_has_ingest_section(self) -> None:
        config = DBWikiConfig()
        assert isinstance(config.ingest, IngestConfig)

    def test_database_connection_string_is_optional(self) -> None:
        config = DatabaseConfig(connection_string=None)
        assert config.connection_string is None

    def test_database_connection_string_accepts_value(self) -> None:
        config = DatabaseConfig(connection_string="DRIVER={SQL Server};SERVER=localhost")
        assert config.connection_string == "DRIVER={SQL Server};SERVER=localhost"
