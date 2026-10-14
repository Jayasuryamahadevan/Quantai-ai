"""
app/config.py — Central configuration via pydantic-settings.
All settings come from environment variables / .env file.
Credentials NEVER reach the LLM or appear in logs.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

# Silence LangChain/LangSmith tracing unconditionally before any import
os.environ.setdefault("LANGCHAIN_TRACING_V2", "false")
os.environ.setdefault("LANGCHAIN_API_KEY", "disabled")
os.environ.setdefault("ANONYMIZED_TELEMETRY", "false")


class Settings(BaseSettings):
    """All application settings — loaded from .env or environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── LLM ─────────────────────────────────────────────────────────────────
    ollama_base_url: str = "http://127.0.0.1:11434"
    llm_model: str = "qwen2.5-coder:7b"
    llm_fallback_model: str = "qwen2.5-coder:3b"
    llm_embed_model: str = "nomic-embed-text"
    llm_num_ctx: int = 4096
    llm_temperature_sql: float = 0.0
    llm_temperature_insight: float = 0.2
    llm_timeout_sec: int = 120
    llm_auto_fallback: bool = True

    # ── MySQL ────────────────────────────────────────────────────────────────
    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3306
    mysql_root_password: str = "YourPassword"

    mysql_readonly_user: str = "quantai_readonly"
    mysql_readonly_password: str = "YourPassword"

    mysql_import_user: str = "quantai_import"
    mysql_import_password: str = "YourPassword"

    mysql_app_user: str = "quantai_app"
    mysql_app_password: str = "YourPassword"

    mysql_data_schema: str = "quantai_data"
    mysql_app_schema: str = "quantai_app"

    # ── Privacy / Accuracy ───────────────────────────────────────────────────
    schema_only_mode: bool = False
    pii_masking_enabled: bool = True
    pii_column_patterns: str = "name,email,phone,ssn,address,dob,birth"
    sample_rows_for_llm: int = 3
    date_anchor: Literal["data_max", "today"] = "data_max"

    # ── Column Selector ──────────────────────────────────────────────────────
    column_selector_top_k: int = 20
    embedding_cache_dir: Path = Path("data/embeddings")

    # ── Query / Execution ────────────────────────────────────────────────────
    max_query_rows_display: int = 1000
    max_export_rows: int = 100_000
    query_timeout_ms: int = 30_000
    accuracy_mode: Literal["fast", "balanced", "max"] = "balanced"

    # ── Exports / Uploads ────────────────────────────────────────────────────
    exports_dir: Path = Path("data/exports")
    exports_auto_expiry_days: int = 7
    uploads_dir: Path = Path("data/uploads")
    dictionaries_dir: Path = Path("data/dictionaries")

    # ── App ──────────────────────────────────────────────────────────────────
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    frontend_dist: Path = Path("frontend/dist")
    secret_key: str = "change_me_to_random_32_char_string"

    # ── Telemetry (always off) ───────────────────────────────────────────────
    # Temporal runs separately; API remains local-only until auth is added.
    temporal_enabled: bool = False
    temporal_address: str = "127.0.0.1:7233"
    temporal_namespace: str = "default"
    temporal_task_queue: str = "quantai-analyst"
    temporal_max_concurrent_activities: int = 1

    langchain_tracing_v2: bool = False
    langchain_api_key: str = "disabled"
    anonymized_telemetry: bool = False

    # ── Derived helpers ──────────────────────────────────────────────────────

    @property
    def pii_patterns_list(self) -> list[str]:
        return [p.strip().lower() for p in self.pii_column_patterns.split(",") if p.strip()]

    def _mysql_dsn(self, username: str, password: str, database: str | None = None) -> str:
        return URL.create(
            drivername="mysql+pymysql",
            username=username,
            password=password,
            host=self.mysql_host,
            port=self.mysql_port,
            database=database,
            query={"charset": "utf8mb4"},
        ).render_as_string(hide_password=False)

    @property
    def readonly_dsn(self) -> str:
        return self._mysql_dsn(self.mysql_readonly_user, self.mysql_readonly_password, self.mysql_data_schema)

    @property
    def import_dsn(self) -> str:
        return self._mysql_dsn(self.mysql_import_user, self.mysql_import_password, self.mysql_data_schema)

    @property
    def app_dsn(self) -> str:
        return self._mysql_dsn(self.mysql_app_user, self.mysql_app_password, self.mysql_app_schema)

    @property
    def root_dsn(self) -> str:
        return self._mysql_dsn("root", self.mysql_root_password)

    @model_validator(mode="after")
    def _ensure_dirs(self) -> "Settings":
        for d in [
            self.embedding_cache_dir,
            self.exports_dir,
            self.uploads_dir,
            self.dictionaries_dir,
        ]:
            d.mkdir(parents=True, exist_ok=True)
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings singleton."""
    return Settings()
