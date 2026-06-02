"""Tests for Discord Quest Auto-Completer."""

from __future__ import annotations

from discord_quest._config import settings
from discord_quest._models import HEARTBEAT_TASKS, SUPPORTED_TASKS, VIDEO_TASKS, Quest, UserStatus


class TestModels:
    def test_quest_from_dict(self) -> None:
        data = {
            "id": "quest_123",
            "config": {"task_type": "WATCH_VIDEO"},
            "userStatus": {
                "enrolledAt": "2026-01-01T00:00:00Z",
                "completedAt": None,
                "progress": {"video": {"value": 50.0}},
            },
        }
        q = Quest.from_dict(data)
        assert q.id == "quest_123"
        assert q.config["task_type"] == "WATCH_VIDEO"
        assert q.user_status is not None
        assert q.user_status.enrolled_at == "2026-01-01T00:00:00Z"
        assert q.user_status.completed_at is None

    def test_quest_no_user_status(self) -> None:
        data = {"id": "quest_456", "config": {"task_type": "PLAY_ON_DESKTOP"}}
        q = Quest.from_dict(data)
        assert q.id == "quest_456"
        assert q.user_status is None

    def test_user_status_completed_at_camel(self) -> None:
        data = {
            "completedAt": "2026-06-01T12:00:00Z",
        }
        us = UserStatus.from_dict(data)
        assert us.completed_at == "2026-06-01T12:00:00Z"

    def test_user_status_completed_at_snake(self) -> None:
        data = {
            "completed_at": "2026-06-01T12:00:00Z",
        }
        us = UserStatus.from_dict(data)
        assert us.completed_at == "2026-06-01T12:00:00Z"

    def test_supported_tasks(self) -> None:
        assert "WATCH_VIDEO" in SUPPORTED_TASKS
        assert "PLAY_ON_DESKTOP" in SUPPORTED_TASKS
        assert "UNKNOWN_TASK" not in SUPPORTED_TASKS

    def test_heartbeat_tasks(self) -> None:
        assert "PLAY_ON_DESKTOP" in HEARTBEAT_TASKS
        assert "WATCH_VIDEO" not in HEARTBEAT_TASKS

    def test_video_tasks(self) -> None:
        assert "WATCH_VIDEO" in VIDEO_TASKS
        assert "WATCH_VIDEO_ON_MOBILE" in VIDEO_TASKS
        assert "PLAY_ON_DESKTOP" not in VIDEO_TASKS

    def test_quest_from_dict_with_task_config_v2(self) -> None:
        data = {
            "id": "quest_v2",
            "config": {
                "task_config_v2": {
                    "tasks": {
                        "WATCH_VIDEO_ON_MOBILE": {"target": 39},
                    },
                },
            },
        }
        q = Quest.from_dict(data)
        assert q.get_task_type() == "WATCH_VIDEO_ON_MOBILE"
        assert q.get_task_target() == 39


class TestConfig:
    def test_defaults(self) -> None:
        assert settings.poll_interval == 60
        assert settings.headless is False
