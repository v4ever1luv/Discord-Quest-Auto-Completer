from __future__ import annotations

import discord
import structlog
from discord.ext import commands

from discord_quest.bot._commands import register_commands
from discord_quest.bot._task_manager import TaskManager
from discord_quest.bot._token_store import EncryptedTokenStore

log = structlog.get_logger(__name__)


class BotClient(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = False
        intents.members = False
        intents.presences = False

        super().__init__(command_prefix="!", intents=intents)

        self.token_store = EncryptedTokenStore()
        self.task_manager = TaskManager()

    async def on_ready(self) -> None:
        log.info(
            "bot.ready",
            user=str(self.user),
            user_id=self.user.id if self.user else None,
        )
        activity = discord.Activity(
            type=discord.ActivityType.playing,
            name="/help | Quest Auto-Complete",
        )
        await self.change_presence(activity=activity)

    async def setup_hook(self) -> None:
        self.token_store.connect()
        register_commands(self)
        await self.tree.sync()
        log.info("bot.commands_synced")

    async def close(self) -> None:
        self.task_manager.stop_all()
        self.token_store.close()
        await super().close()
