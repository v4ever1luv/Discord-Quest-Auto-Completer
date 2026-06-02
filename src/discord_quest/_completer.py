from __future__ import annotations

import asyncio
import math
import signal
from typing import Any

import structlog

from ._api import DiscordAPI, _fetch_build_number
from ._config import settings
from ._gateway import DiscordGateway
from ._models import (
    HEARTBEAT_TASKS,
    SUPPORTED_TASKS,
    VIDEO_TASKS,
    Quest,
    UserStatus,
    _get,
)
from ._notify import send_notification
from ._persist import StateStore

log = structlog.get_logger(__name__)


def calculate_heartbeat_progress(quest: Quest, duration_seconds: float) -> float:
    cfg = quest.config.get("heartbeat", {})
    required = cfg.get("required_seconds", 0) or cfg.get("required_seconds_v2", 0)
    if required <= 0:
        return 100.0
    pct = min(duration_seconds / required * 100.0, 100.0)
    return round(pct, 2)


def compute_sleep(quest: Quest, attempt: int, max_sleep: int = 300) -> int:
    if attempt <= 0:
        attempt = 1
    base: int | None = None
    hb = quest.config.get("heartbeat", {})
    if hb:
        base = hb.get("required_seconds", 0) or hb.get("required_seconds_v2", 0)
    vid = quest.config.get("video", {})
    if vid:
        v = vid.get("required_seconds", 0) or vid.get("required_seconds_v2", 0)
        if base is not None:
            base = min(base, v) if v else base
        else:
            base = v
    if not base or base <= 0:
        base = 300
    jitter = 0.9 + 0.2 * math.sin(attempt * 1.618)
    return min(int(base * jitter) + 5, max_sleep)


class QuestAutocompleter:
    def __init__(self, token: str, proxy: str | None = None) -> None:
        self.token = token
        self.proxy = proxy
        self.build_number = _fetch_build_number()
        self.api = DiscordAPI(token, self.build_number, proxy)
        self.store = StateStore()
        self.gateway = DiscordGateway(token, self.build_number)
        self.running = True
        self._last_fetch: str | None = None
        self._poll_triggered = False

    async def start(self) -> None:
        self.store.connect()
        self.store.list_all()

        if not await self.api.validate_token():
            log.error("startup.token_invalid")
            return

        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        gateway_task = asyncio.create_task(self.gateway.connect())
        self.gateway.on_quest_update(self._on_quest_update)
        self.gateway.on_passive_update(self._on_passive_update)

        log.info("startup.begin")
        try:
            while self.running:
                await self._poll()
                await asyncio.sleep(settings.poll_interval)
        except asyncio.CancelledError:
            pass
        finally:
            self.running = False
            gateway_task.cancel()
            await self.api.close()
            await self.gateway.close()
            self.store.close()
            log.info("shutdown.complete")

    def _handle_signal(self, sig: int, _frame: Any) -> None:
        log.info("signal.received", signum=sig)
        self.running = False

    def _on_quest_update(self, data: dict[str, Any]) -> None:
        quest_id = data.get("id", "")
        if quest_id and self.store.is_completed(quest_id):
            log.info("gateway.quest_already_completed", quest_id=quest_id)
            return
        log.info("gateway.quest_update", quest_id=quest_id)
        asyncio.create_task(self._handle_quest_update(data))

    async def _handle_quest_update(self, data: dict[str, Any]) -> None:
        await self._process_quest(Quest.from_dict(data))

    def _on_passive_update(self, data: dict[str, Any]) -> None:
        if not self._poll_triggered:
            self._poll_triggered = True
            asyncio.create_task(self._trigger_poll())

    async def _trigger_poll(self) -> None:
        await asyncio.sleep(2)
        await self._poll()
        self._poll_triggered = False

    async def _poll(self) -> None:
        log.info("poll.start")
        quests = await self._fetch_quests()
        if not quests:
            return
        pending = [q for q in quests if self._is_pending(q)]
        log.info("poll.quests", total=len(quests), pending=len(pending))
        for q in pending:
            await self._process_quest(q)

    async def _fetch_quests(self) -> list[Quest]:
        attempt = 0
        while self.running:
            try:
                r = await self.api.get("/users/@me/quests")
                if r.status_code == 200:
                    data: list[dict[str, Any]] = r.json()
                    return [Quest.from_dict(q) for q in data]
                log.warn("poll.http_error", status=r.status_code)
                if r.status_code == 429:
                    retry_after = _get(r.json(), "retry_after") or 5
                    await asyncio.sleep(min(retry_after + 2**attempt, 60))
                    attempt += 1
                    continue
                return []
            except Exception as e:
                log.debug("poll.error", error=str(e))
                await asyncio.sleep(min(2**attempt, 30))
                attempt += 1
        return []

    async def _process_quest(self, quest: Quest) -> None:
        us = quest.user_status
        if not us:
            log.debug("quest.no_user_status", quest_id=quest.id)
            return

        if us.completed_at:
            log.info("quest.already_completed", quest_id=quest.id)
            self.store.mark_completed(quest.id, us.completed_at)
            return

        task_type = quest.config.get("task_type")
        if task_type not in SUPPORTED_TASKS:
            log.debug("quest.unsupported", quest_id=quest.id, task=task_type)
            return

        saved = self.store.load_progress(quest.id)

        if task_type in HEARTBEAT_TASKS:
            await self._process_heartbeat(
                quest, initial_slept=(saved or {}).get("total_slept", 0.0)
            )

        elif task_type in VIDEO_TASKS:
            await self._process_video(quest, is_mobile=(task_type == "WATCH_VIDEO_ON_MOBILE"))

    def _is_pending(self, quest: Quest) -> bool:
        if self.store.is_completed(quest.id):
            return False
        us = quest.user_status
        if us and us.completed_at:
            return False
        return True

    async def _process_heartbeat(self, quest: Quest, initial_slept: float = 0.0) -> None:
        log.info("heartbeat.start", quest_id=quest.id, resumed=initial_slept > 0)
        us = quest.user_status or UserStatus()
        enrolled_at = us.enrolled_at or ""

        if not enrolled_at and settings.auto_accept:
            accepted = await self._enroll_quest(quest.id)
            if not accepted:
                return
            enrolled_at = us.enrolled_at or ""

        total_slept = initial_slept
        attempt = 0

        while self.running:
            r = await self.api.get("/users/@me/quests")
            if r.status_code != 200:
                await asyncio.sleep(30)
                continue

            quests: list[dict[str, Any]] = r.json()
            fresh_raw = next((q for q in quests if q["id"] == quest.id), None)
            if not fresh_raw:
                log.info("heartbeat.quest_gone", quest_id=quest.id)
                return

            fresh = Quest.from_dict(fresh_raw)
            fresh_us = fresh.user_status
            if fresh_us and fresh_us.completed_at:
                log.info("heartbeat.completed", quest_id=quest.id)
                self.store.mark_completed(quest.id, fresh_us.completed_at)
                return

            progress_pct = calculate_heartbeat_progress(quest, total_slept)
            log.info(
                "heartbeat.progress",
                quest_id=quest.id,
                progress=f"{progress_pct}%",
                slept=f"{total_slept:.0f}s",
            )
            if progress_pct >= 100:
                await self._trigger_complete(quest.id, quest.config.get("task_type", ""))
                return

            sleep_sec = compute_sleep(quest, attempt)
            log.debug("heartbeat.sleep", seconds=sleep_sec)
            await asyncio.sleep(sleep_sec)
            total_slept += sleep_sec
            attempt += 1
            self.store.save_progress(quest.id, "heartbeat", total_slept, enrolled_at)

    async def _process_video(self, quest: Quest, is_mobile: bool = False) -> None:
        log.info("video.start", quest_id=quest.id, mobile=is_mobile)
        segments = 0
        attempt = 0

        us = quest.user_status or UserStatus()
        if not us.enrolled_at and settings.auto_accept:
            accepted = await self._enroll_quest(quest.id)
            if not accepted:
                return

        while self.running:
            r = await self.api.get("/users/@me/quests")
            if r.status_code != 200:
                await asyncio.sleep(30)
                continue

            quests: list[dict[str, Any]] = r.json()
            fresh_raw = next((q for q in quests if q["id"] == quest.id), None)
            if not fresh_raw:
                log.info("video.quest_gone", quest_id=quest.id)
                return

            fresh = Quest.from_dict(fresh_raw)
            fresh_us = fresh.user_status
            if fresh_us and fresh_us.completed_at:
                log.info("video.completed", quest_id=quest.id)
                self.store.mark_completed(quest.id, fresh_us.completed_at)
                asyncio.create_task(
                    send_notification(quest.id, "", quest.config.get("task_type", ""))
                )
                return

            r2 = await self.api.post(
                f"/users/@me/quests/{quest.id}/video-progress", is_mobile=is_mobile
            )
            if r2.status_code in (200, 204):
                segments += 1
                log.info(
                    "video.segment",
                    quest_id=quest.id,
                    segments=segments,
                )
            elif r2.status_code == 429:
                retry = _get(r2.json(), "retry_after") or 5
                await asyncio.sleep(retry)

            sleep_sec = 30 + attempt * 5
            await asyncio.sleep(sleep_sec)
            attempt += 1

    async def _enroll_quest(self, quest_id: str) -> bool:
        attempt = 0
        while self.running:
            try:
                r = await self.api.post(
                    f"/users/@me/quests/{quest_id}/enroll",
                )
                if r.status_code in (200, 204):
                    log.info("quest.enrolled", quest_id=quest_id)
                    return True
                log.warn("enroll.error", quest_id=quest_id, status=r.status_code)
                retry_after = _get(r.json(), "retry_after") or 5
                await asyncio.sleep(min(retry_after + 2**attempt, 60))
                attempt += 1
            except Exception as e:
                log.debug("enroll.exception", quest_id=quest_id, error=str(e))
                await asyncio.sleep(min(2**attempt, 60))
                attempt += 1
        return False

    async def _trigger_complete(self, quest_id: str, task_type: str = "") -> None:
        for _ in range(3):
            try:
                r = await self.api.post(
                    f"/users/@me/quests/{quest_id}/complete",
                )
                if r.status_code == 200:
                    log.info("quest.completed", quest_id=quest_id)
                    data: dict[str, Any] = r.json()
                    completed_at = _get(data, "completedAt", "completed_at") or ""
                    self.store.mark_completed(quest_id, completed_at)
                    reward = data.get("reward", {}).get("name", "")
                    asyncio.create_task(send_notification(quest_id, reward, task_type))
                    return
                log.warn("complete.error", quest_id=quest_id, status=r.status_code)
                await asyncio.sleep(5)
            except Exception as e:
                log.debug("complete.exception", quest_id=quest_id, error=str(e))
                await asyncio.sleep(5)
