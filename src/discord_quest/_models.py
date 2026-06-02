from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class QuestProgress:
    value: float = 0.0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> QuestProgress:
        return cls(value=data.get("value", 0.0))


@dataclass
class UserStatus:
    enrolled_at: str | None = None
    completed_at: str | None = None
    progress: dict[str, QuestProgress] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UserStatus:
        raw = data.get("progress", {}) or {}
        progress = {k: QuestProgress.from_dict(v) for k, v in raw.items() if isinstance(v, dict)}
        return cls(
            enrolled_at=_get(data, "enrolledAt", "enrolled_at"),
            completed_at=_get(data, "completedAt", "completed_at"),
            progress=progress,
        )


@dataclass
class Quest:
    id: str
    config: dict[str, Any] = field(default_factory=dict)
    user_status: UserStatus | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Quest:
        us_raw = _get(data, "userStatus", "user_status")
        content = data.get("content") or {}
        if not us_raw and content:
            us_raw = _get(content, "userStatus", "user_status")
        return cls(
            id=data.get("id", ""),
            config=data.get("config", {}),
            user_status=UserStatus.from_dict(us_raw) if us_raw else None,
            raw=data,
        )

    def get_task_type(self) -> str:
        tasks = (self.config.get("task_config_v2") or {}).get("tasks") or {}
        for name in tasks:
            return name
        return self.config.get("task_type") or ""

    def get_task_target(self) -> int:
        task_type = self.get_task_type()
        if not task_type:
            return 0
        tasks = (self.config.get("task_config_v2") or {}).get("tasks") or {}
        task = tasks.get(task_type) or {}
        return task.get("target") or 0


SUPPORTED_TASKS = frozenset(
    {
        "WATCH_VIDEO",
        "PLAY_ON_DESKTOP",
        "STREAM_ON_DESKTOP",
        "PLAY_ACTIVITY",
        "WATCH_VIDEO_ON_MOBILE",
    }
)

HEARTBEAT_TASKS = frozenset({"PLAY_ON_DESKTOP", "STREAM_ON_DESKTOP", "PLAY_ACTIVITY"})
VIDEO_TASKS = frozenset({"WATCH_VIDEO", "WATCH_VIDEO_ON_MOBILE"})


def _get(d: dict[str, Any] | None, *keys: str) -> Any:
    if d is None:
        return None
    for k in keys:
        if k in d:
            return d[k]
    return None
