"""CLI entry point for Discord Quest Auto-Completer."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

import structlog

from ._completer import QuestAutocompleter
from ._config import settings
from ._health import start_health_server
from ._log import setup_logging

log = structlog.get_logger(__name__)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Discord Quest Auto-Completer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=settings.poll_interval,
        help="Poll interval in seconds (default: %(default)s)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        default=None,
        help="Run browser in headless mode",
    )
    parser.add_argument(
        "--user-data-dir",
        type=str,
        default=None,
        help="Chrome user data directory path",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        default=None,
        help="Enable debug logging",
    )
    return parser.parse_args()


async def amain(
    poll_interval: int, headless: bool | None, user_data_dir: str | None, debug: bool | None
) -> None:
    """Async entry point."""
    if debug is not None:
        os.environ["DQ_DEBUG"] = str(debug)
    if headless is not None:
        os.environ["DQ_HEADLESS"] = str(headless)
    if user_data_dir is not None:
        os.environ["DQ_USER_DATA_DIR"] = user_data_dir

    setup_logging()
    start_health_server(settings.health_port)
    log.info("startup", poll_interval=poll_interval, headless=settings.headless)

    token = _load_token()
    completer = QuestAutocompleter(token)
    await completer.start()


def _load_token() -> str:
    import getpass

    tf = settings.token_file
    if tf.exists():
        token = tf.read_text(encoding="utf-8").strip()
        if token:
            return token

    return getpass.getpass("Enter Discord token: ").strip()


def main() -> None:
    """CLI entry: parse args, run loop."""
    args = _parse_args()
    try:
        asyncio.run(amain(args.poll_interval, args.headless, args.user_data_dir, args.debug))
    except KeyboardInterrupt:
        log.info("shutdown.keyboard")
    except Exception as e:
        log.exception("fatal", error=str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
