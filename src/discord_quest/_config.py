from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict, YamlConfigSettingsSource


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
    health_port: int = 0

    # Anti-detect
    anti_detect: bool = True

    # Notification settings
    notify_webhook_url: str = ""
    notify_telegram_token: str = ""
    notify_telegram_chat_id: str = ""

    # Bot settings
    bot_token: str = ""
    bot_encryption_key: str = ""
    max_users: int = 10

    model_config = SettingsConfigDict(
        env_prefix="DQ_",
        env_file=".env",
        env_file_encoding="utf-8",
        frozen=True,
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        sources = (init_settings, env_settings, dotenv_settings)
        try:
            cfg_path = Path("config.yaml")
            if cfg_path.exists():
                sources += (YamlConfigSettingsSource(settings_cls, yaml_file=str(cfg_path)),)
        except Exception:
            pass
        return sources


settings = Settings()
