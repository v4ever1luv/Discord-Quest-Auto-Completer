from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict, YamlConfigSettingsSource


class Settings(BaseSettings):
    poll_interval: int = 60
    auto_accept: bool = True
    log_progress: bool = True
    debug: bool = True
    token_file: Path = Field(default=Path(".token"))
    completed_db: Path = Field(default=Path("completed.db"))
    health_port: int = 0

    # Playwright settings
    browser_type: str = "chromium"
    headless: bool = False
    user_data_dir: str = ".discord_profile"

    # Blacklist quest IDs — skip these
    quest_blacklist: list[str] = Field(default_factory=list)

    # Orion — auto-update from GitHub
    orion_auto_update: bool = True

    # Auto-stop khi không có quest pending sau N lần poll
    max_idle_polls: int = 3

    # Random delay [min, max] seconds before enroll
    enroll_delay_range: list[int] = Field(default=[5, 15])

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
