"""Central configuration loader.

Combines two sources:
  1. configs/settings.yaml -> non-secret settings (paths, table files, tickers)
  2. .env / environment     -> secrets (API keys) and machine-specific overrides

Every other module calls `get_settings()` instead of hardcoding paths or keys.
Pydantic validates types at startup, so a typo in the YAML fails loudly and early
("fail fast") rather than causing a confusing error deep inside the pipeline.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Project root = two levels above this file: src/supplier_copilot/config.py -> repo root.
# Anchoring paths here means the code works no matter which folder you run it from.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "configs" / "settings.yaml"


# --- Typed config sections. Each class mirrors one block of settings.yaml. ---

class PathsConfig(BaseModel):
    raw_m5_dir: Path
    interim_dir: Path
    duckdb_path: Path
    sec_filings_dir: Path
    transcripts_dir: Path


class M5Config(BaseModel):
    sales_file: str
    calendar_file: str
    prices_file: str


class DuckDBConfig(BaseModel):
    memory_limit: str = "4GB"
    threads: int = 4


class SecConfig(BaseModel):
    tickers: list[str]
    form_types: list[str] = Field(default_factory=lambda: ["10-K"])


class Settings(BaseModel):
    """The full, validated application configuration."""

    project_name: str
    paths: PathsConfig
    m5: M5Config
    duckdb: DuckDBConfig = Field(default_factory=DuckDBConfig)
    sec: SecConfig

    # Secrets / env-only values (never stored in YAML)
    log_level: str = "INFO"
    sec_user_agent: str | None = None
    openai_api_key: str | None = None


def _resolve_paths(paths: PathsConfig) -> PathsConfig:
    """Turn relative paths from YAML into absolute paths anchored at PROJECT_ROOT."""
    resolved = {
        name: (value if value.is_absolute() else PROJECT_ROOT / value)
        for name, value in paths.model_dump().items()
    }
    return PathsConfig(**resolved)


def load_settings(config_path: Path | None = None) -> Settings:
    """Read YAML + environment variables and return a validated Settings object."""
    # load_dotenv copies key=value pairs from .env into os.environ (if the file exists).
    load_dotenv(PROJECT_ROOT / ".env")

    # Allow an env var to point at a different YAML (e.g., configs/settings.prod.yaml).
    path = config_path or Path(os.getenv("SUPPLIER_COPILOT_CONFIG", DEFAULT_CONFIG_PATH))
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))  # safe_load: never executes code

    settings = Settings(
        **raw,
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        sec_user_agent=os.getenv("SEC_USER_AGENT"),
        openai_api_key=os.getenv("OPENAI_API_KEY") or None,
    )
    settings.paths = _resolve_paths(settings.paths)
    return settings


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached accessor: the YAML is parsed once per process, then reused (singleton pattern)."""
    return load_settings()
