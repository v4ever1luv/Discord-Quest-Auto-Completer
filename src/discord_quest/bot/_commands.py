from __future__ import annotations

from typing import Any

import discord
import httpx
import structlog
from discord import app_commands

log = structlog.get_logger(__name__)


async def _validate_token(token: str) -> bool:
    try:
        headers = {"Authorization": token, "Content-Type": "application/json"}
        async with httpx.AsyncClient(base_url="https://discord.com/api/v9") as c:
            r = await c.get("/users/@me", headers=headers, timeout=15)
            return r.status_code == 200
    except Exception:
        return False


async def _fetch_quests(token: str) -> list[dict[str, Any]]:
    try:
        headers = {"Authorization": token, "Content-Type": "application/json"}
        async with httpx.AsyncClient(base_url="https://discord.com/api/v9") as c:
            r = await c.get("/quests/@me", headers=headers, timeout=15)
            if r.status_code != 200:
                return []
            data = r.json()
            return data.get("quests") or []
    except Exception:
        return []


def register_commands(bot: Any) -> None:  # noqa: ANN401
    store: Any = bot.token_store  # noqa: ANN401
    manager: Any = bot.task_manager  # noqa: ANN401

    @bot.tree.command(name="help", description="Hướng dẫn sử dụng bot")
    async def help_cmd(interaction: discord.Interaction) -> None:
        embed = discord.Embed(title="Quest Bot — Hướng dẫn", color=0x5865F2)
        embed.add_field(
            name="/token set <token>",
            value="Gửi token Discord cho bot (chỉ mình bạn thấy)",
            inline=False,
        )
        embed.add_field(
            name="/token remove",
            value="Xoá token khỏi bot",
            inline=False,
        )
        embed.add_field(
            name="/token info",
            value="Xem tài khoản đã đăng ký",
            inline=False,
        )
        embed.add_field(
            name="/quests list",
            value="Xem danh sách quest đang có",
            inline=False,
        )
        embed.add_field(
            name="/quests status",
            value="Xem trạng thái completer",
            inline=False,
        )
        embed.set_footer(text="Token được mã hoá và bảo vệ")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    class TokenGroup(app_commands.Group):
        @app_commands.command(name="set", description="Đăng ký token Discord")
        async def token_set(
            self,
            interaction: discord.Interaction,
            token: str,
        ) -> None:
            await interaction.response.defer(ephemeral=True)

            valid = await _validate_token(token)

            if not valid:
                await interaction.followup.send(
                    "❌ Token không hợp lệ hoặc đã hết hạn.",
                    ephemeral=True,
                )
                return

            uid = str(interaction.user.id)
            store.set_token(uid, token)
            manager.start_user(uid, token)

            await interaction.followup.send(
                "✅ Token đã được lưu và mã hoá. Bot đang chạy quest cho bạn.",
                ephemeral=True,
            )

        @app_commands.command(name="remove", description="Xoá token khỏi bot")
        async def token_remove(self, interaction: discord.Interaction) -> None:
            uid = str(interaction.user.id)
            removed = store.remove_token(uid)
            manager.stop_user(uid)

            if removed:
                await interaction.response.send_message(
                    "✅ Đã xoá token của bạn.",
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    "⚠️ Bạn chưa đăng ký token nào.",
                    ephemeral=True,
                )

        @app_commands.command(name="info", description="Xem thông tin token đã lưu")
        async def token_info(self, interaction: discord.Interaction) -> None:
            uid = str(interaction.user.id)
            token = store.get_token(uid)
            if not token:
                await interaction.response.send_message(
                    "⚠️ Bạn chưa đăng ký token. Dùng `/token set` để thêm.",
                    ephemeral=True,
                )
                return

            valid = await _validate_token(token)

            running = manager.is_running(uid)
            status = "🟢 Đang chạy" if running else "🔴 Chưa chạy"

            if not valid:
                msg = (
                    "⚠️ Token đã lưu nhưng không hợp lệ. "
                    f"Dùng `/token set` để cập nhật.\nTrạng thái: {status}"
                )
                await interaction.response.send_message(msg, ephemeral=True)
                return

            masked = token[:15] + "..." + token[-5:]
            await interaction.response.send_message(
                f"✅ Token hợp lệ\nToken: `{masked}`\nTrạng thái: {status}",
                ephemeral=True,
            )

    class QuestsGroup(app_commands.Group):
        @app_commands.command(name="list", description="Xem danh sách quest")
        async def quests_list(self, interaction: discord.Interaction) -> None:
            await interaction.response.defer(ephemeral=True)

            uid = str(interaction.user.id)
            token = store.get_token(uid)
            if not token:
                await interaction.followup.send(
                    "⚠️ Bạn chưa đăng ký token. Dùng `/token set <token>`.",
                    ephemeral=True,
                )
                return

            quests = await _fetch_quests(token)

            if not quests:
                await interaction.followup.send(
                    "📭 Không có quest nào.",
                    ephemeral=True,
                )
                return

            lines: list[str] = []
            for q in quests:
                qid = q.get("id", "?")[:8]
                task_type = q.get("config", {}).get("task_type", "?")
                us = q.get("userStatus") or {}
                enrolled = "📥" if us.get("enrolledAt") else "📄"
                lines.append(f"{enrolled} `{qid}` — {task_type}")

            await interaction.followup.send(
                f"**Quest của bạn ({len(quests)}):**\n" + "\n".join(lines),
                ephemeral=True,
            )

        @app_commands.command(name="status", description="Xem trạng thái completer")
        async def quests_status(self, interaction: discord.Interaction) -> None:
            uid = str(interaction.user.id)
            running = manager.is_running(uid)
            if running:
                await interaction.response.send_message(
                    "🟢 Bot đang tự động hoàn thành quest cho bạn.",
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    "🔴 Bot chưa chạy cho bạn. Đã có token chưa? `/token info`",
                    ephemeral=True,
                )

    class AdminGroup(app_commands.Group):
        def _is_owner(self, interaction: discord.Interaction) -> bool:
            app = interaction.client.application
            return app is not None and interaction.user.id == app.owner.id

        @app_commands.command(name="list", description="Danh sách user đã đăng ký token")
        async def admin_list(self, interaction: discord.Interaction) -> None:
            if not self._is_owner(interaction):
                await interaction.response.send_message(
                    "❌ Chỉ bot owner mới dùng được.", ephemeral=True
                )
                return
            await interaction.response.defer(ephemeral=True)
            users = store.list_users()
            active = manager.list_active()
            lines = [f"**Tổng: {len(users)} user**"]
            for uid in users:
                status = "🟢" if uid in active else "🔴"
                lines.append(f"{status} `{uid}`")
            await interaction.followup.send("\n".join(lines), ephemeral=True)

        @app_commands.command(name="start-all", description="Chạy quest cho tất cả user")
        async def admin_start_all(self, interaction: discord.Interaction) -> None:
            if not self._is_owner(interaction):
                await interaction.response.send_message(
                    "❌ Chỉ bot owner mới dùng được.", ephemeral=True
                )
                return
            await interaction.response.defer(ephemeral=True)
            users = store.list_users()
            started = 0
            for uid in users:
                token = store.get_token(uid)
                if token and not manager.is_running(uid):
                    manager.start_user(uid, token)
                    started += 1
            await interaction.followup.send(f"✅ Đã start **{started}** user.", ephemeral=True)

        @app_commands.command(name="stop-all", description="Dừng tất cả user")
        async def admin_stop_all(self, interaction: discord.Interaction) -> None:
            if not self._is_owner(interaction):
                await interaction.response.send_message(
                    "❌ Chỉ bot owner mới dùng được.", ephemeral=True
                )
                return
            await interaction.response.defer(ephemeral=True)
            manager.stop_all()
            await interaction.followup.send("✅ Đã dừng tất cả user.", ephemeral=True)

    bot.tree.add_command(TokenGroup(name="token", description="Quản lý token"))
    bot.tree.add_command(QuestsGroup(name="quests", description="Xem quest và trạng thái"))
    bot.tree.add_command(AdminGroup(name="admin", description="Admin - quản lý user"))
