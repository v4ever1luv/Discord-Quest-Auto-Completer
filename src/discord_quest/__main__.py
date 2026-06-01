"""CLI entry point for Discord Quest Auto-Completer."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

import structlog

from ._completer import QuestAutocompleter
from ._config import settings
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
        "--proxy",
        type=str,
        default=None,
        help="HTTP/S proxy URL (e.g. http://127.0.0.1:8080)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=settings.request_timeout,
        help="HTTP request timeout in seconds (default: %(default)s)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        default=None,
        help="Enable debug logging",
    )
    return parser.parse_args()


async def amain(poll_interval: int, proxy: str | None, timeout: int, debug: bool | None) -> None:
    """Async entry point."""
    if debug is not None:
        os.environ["DQ_DEBUG"] = str(debug)

    setup_logging()
    log.info(
        "startup",
        poll_interval=poll_interval,
        proxy=bool(proxy),
        timeout=timeout,
    )

    token = _load_token()
    completer = QuestAutocompleter(token, proxy)
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
        asyncio.run(amain(args.poll_interval, args.proxy, args.timeout, args.debug))
    except KeyboardInterrupt:
        log.info("shutdown.keyboard")
    except Exception as e:
        log.exception("fatal", error=str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
