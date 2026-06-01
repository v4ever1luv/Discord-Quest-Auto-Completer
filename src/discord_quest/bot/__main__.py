"""Bot entry point — chạy Discord bot với slash commands."""

from __future__ import annotations

import sys

import structlog

from discord_quest._config import settings
from discord_quest._log import setup_logging
from discord_quest.bot._client import BotClient

log = structlog.get_logger(__name__)


def main() -> None:
    """Run the bot."""
    setup_logging()

    token = settings.bot_token
    if not token:
        log.error("bot.missing_token")
        sys.exit(1)

    client = BotClient()
    try:
        client.run(token, log_handler=None)
    except KeyboardInterrupt:
        log.info("bot.shutdown.keyboard")
    except Exception as e:
        log.exception("bot.fatal", error=str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
