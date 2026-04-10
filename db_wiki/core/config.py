"""YAML configuration system for the db-wiki knowledge store.

Security note (T-01-02): yaml.safe_load() is always used — never yaml.load().
pydantic validates all types after loading, rejecting unexpected values.

Config file location: {store_path}/config.yaml
Default store_path: .db-wiki (configurable via --store-path, D-07/D-08)
"""
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel


class StorageConfig(BaseModel):
    """Storage location settings."""

    path: str = ".db-wiki"


class DatabaseConfig(BaseModel):
    """Live database connection settings (optional — offline-first by default)."""

    connection_string: str | None = None
    timeout_seconds: int = 30


class IngestConfig(BaseModel):
    """Ingestion settings."""

    max_file_size_mb: int = 50


class EmbeddingConfig(BaseModel):
    """Embedding provider settings (CONFIG-01)."""

    provider: str = "local"  # "local" or "openai"
    model_name: str = "all-MiniLM-L6-v2"
    dimensions: int = 384
    openai_model: str = "text-embedding-3-small"
    openai_dimensions: int = 1536


class LearningGapWeightsConfig(BaseModel):
    """Weights for gap priority scoring formula."""

    severity: float = 0.30
    connectivity: float = 0.25
    query_frequency: float = 0.20
    staleness: float = 0.15
    solvability: float = 0.10


class LearningConfig(BaseModel):
    """Learning loop configuration."""

    max_gaps_per_run: int = 10
    llm_provider: str | None = None  # None = offline/heuristic mode
    llm_api_key: str | None = None
    llm_model: str | None = None
    decay_rate_weekly: float = 0.01
    decay_rate_confirmed_monthly: float = 0.005
    conflict_escalate_threshold: float = 0.1
    cooldown_hours: list[int] = [1, 4, 24, 72, 168]
    max_attempts_before_permanent: int = 5
    collector_timeout_seconds: int = 10
    collector_max_rows: int = 100
    collector_query_budget: int = 20
    gap_weights: LearningGapWeightsConfig = LearningGapWeightsConfig()


class DBWikiConfig(BaseModel):
    """Top-level configuration for db-wiki."""

    storage: StorageConfig = StorageConfig()
    database: DatabaseConfig = DatabaseConfig()
    ingest: IngestConfig = IngestConfig()
    embedding: EmbeddingConfig = EmbeddingConfig()
    learning: LearningConfig = LearningConfig()


def load_config(store_path: Path) -> DBWikiConfig:
    """Load configuration from *store_path*/config.yaml.

    Falls back to all defaults if the file does not exist or is empty.

    Security: uses yaml.safe_load() — never yaml.load() (T-01-02).

    Args:
        store_path: Directory that contains (or will contain) config.yaml.
    """
    config_file = Path(store_path) / "config.yaml"
    if not config_file.exists():
        return DBWikiConfig()
    text = config_file.read_text(encoding="utf-8").strip()
    if not text:
        return DBWikiConfig()
    data: Any = yaml.safe_load(text)
    if not isinstance(data, dict):
        return DBWikiConfig()
    return DBWikiConfig.model_validate(data)


def write_default_config(store_path: Path) -> None:
    """Write the default configuration to *store_path*/config.yaml.

    Creates parent directories if needed. Produces clean YAML output
    from the default :class:`DBWikiConfig` values.

    Args:
        store_path: Directory where config.yaml will be written.
    """
    store_path = Path(store_path)
    store_path.mkdir(parents=True, exist_ok=True)
    config = DBWikiConfig()
    config_file = store_path / "config.yaml"
    config_file.write_text(
        yaml.dump(config.model_dump(), default_flow_style=False, sort_keys=True),
        encoding="utf-8",
    )
