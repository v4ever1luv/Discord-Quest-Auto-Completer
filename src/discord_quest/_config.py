from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    api_base: str = "https://discord.com/api/v9"
    poll_interval: int = 60
    heartbeat_interval: int = 20
    auto_accept: bool = True
    log_progress: bool = True
    debug: bool = True
    request_timeout: int = 30
    proxy: str | None = None
    token_file: Path = Field(default=Path(".token"))
    completed_db: Path = Field(default=Path("completed.db"))
    build_fallback: int = 504649

    model_config = SettingsConfigDict(
        env_prefix="DQ_",
        env_file=".env",
        env_file_encoding="utf-8",
        frozen=True,
    )


settings = Settings()
