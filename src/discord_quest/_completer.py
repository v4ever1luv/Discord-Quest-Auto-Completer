from __future__ import annotations

import asyncio
import random
import signal
from typing import Any

import structlog

from ._config import settings
from ._models import SUPPORTED_TASKS, Quest
from ._notify import send_notification
from ._persist import StateStore
from ._playwright_client import PlaywrightClient

log = structlog.get_logger(__name__)


class QuestAutocompleter:
    def __init__(self, token: str, proxy: str | None = None) -> None:
        self.token = token
        self.proxy = proxy
        self.browser = PlaywrightClient(
            token=token,
            headless=settings.headless,
            user_data_dir=settings.user_data_dir,
        )
        self.store = StateStore()
        self.running = True
        self._idle_count = 0

    async def start(self) -> None:
        self.store.connect()
        await self._start_browser()

        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        log.info("startup.begin")
        try:
            while self.running:
                await self._tick()
                jitter = settings.poll_interval + random.uniform(0, 30)
                await asyncio.sleep(jitter)
        except asyncio.CancelledError:
            pass
        finally:
            self.running = False
            await self.browser.close()
            self.store.close()
            log.info("shutdown.complete")

    async def _start_browser(self) -> None:
        for attempt in range(3):
            try:
                await self.browser.start()
                return
            except Exception as e:
                log.warn("browser.start_retry", attempt=attempt, error=str(e))
                await asyncio.sleep(3)
        log.error("browser.start_failed")

    def _handle_signal(self, sig: int, _frame: Any) -> None:
        log.info("signal.received", signum=sig)
        self.running = False

    async def _tick(self) -> None:
        if not await self.browser.ensure_ready():
            return
        quests = await self.browser.get_quests()
        if not quests:
            await self._check_idle()
            return
        pending = [q for q in quests if self._should_process(q)]
        if not pending:
            await self._check_idle()
            return
        self._idle_count = 0
        for q in pending:
            await self._handle_completed(q)

    async def _check_idle(self) -> None:
        self._idle_count += 1
        if self._idle_count >= settings.max_idle_polls:
            log.info("shutdown.no_pending_quests", idle_polls=self._idle_count)
            self.running = False

    def _should_process(self, quest: Quest) -> bool:
        if self.store.is_completed(quest.id):
            return False
        t = quest.get_task_type()
        if not t or t not in SUPPORTED_TASKS:
            return False
        return True

    async def _handle_completed(self, quest: Quest) -> None:
        us = quest.user_status
        if not us or not us.completed_at:
            return
        self.store.mark_completed(quest.id, us.completed_at)
        log.info("quest.completed", quest_id=quest.id, task=quest.get_task_type())
        task = asyncio.create_task(send_notification(quest.id, "", quest.get_task_type()))
        task.add_done_callback(
            lambda t: t.exception() and log.warn("notify.exception", error=str(t.exception()))
        )
