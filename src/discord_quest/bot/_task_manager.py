from __future__ import annotations

import asyncio
from typing import Any

import structlog

from discord_quest._completer import QuestAutocompleter
from discord_quest._config import settings

log = structlog.get_logger(__name__)


class TaskManager:
    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task[Any]] = {}
        self._completers: dict[str, QuestAutocompleter] = {}

    def start_user(self, user_id: str, token: str) -> None:
        if user_id in self._tasks:
            log.info("task_manager.already_running", user_id=user_id)
            return
        if len(self._tasks) >= settings.max_users:
            log.warn("task_manager.max_users_reached", max=settings.max_users)
            return

        async def _run() -> None:
            try:
                c = QuestAutocompleter(token, settings.proxy)
                self._completers[user_id] = c
                await c.start()
            except asyncio.CancelledError:
                pass
            except Exception as e:
                log.error("task_manager.user_error", user_id=user_id, error=str(e))
            finally:
                self._tasks.pop(user_id, None)
                self._completers.pop(user_id, None)

        self._tasks[user_id] = asyncio.create_task(_run())
        log.info("task_manager.started", user_id=user_id)

    def stop_user(self, user_id: str) -> None:
        task = self._tasks.pop(user_id, None)
        if task:
            task.cancel()
        c = self._completers.pop(user_id, None)
        if c:
            c.running = False
        log.info("task_manager.stopped", user_id=user_id)

    def is_running(self, user_id: str) -> bool:
        return user_id in self._tasks

    def list_active(self) -> list[str]:
        return list(self._tasks.keys())

    def stop_all(self) -> None:
        for uid in list(self._tasks.keys()):
            self.stop_user(uid)
