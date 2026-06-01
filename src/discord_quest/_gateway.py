from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any

import structlog
import websockets.client

log = structlog.get_logger(__name__)

GATEWAY_URL = "wss://gateway.discord.gg/?v=9&encoding=json"

OnQuestUpdate = Callable[[dict[str, Any]], None]


class DiscordGateway:
    def __init__(self, token: str, build_number: int = 504649) -> None:
        self.token = token
        self.build_number = build_number
        self.seq: int | None = None
        self.ws: websockets.client.WebSocketClientProtocol | None = None
        self._running = False
        self._on_quest_update: OnQuestUpdate | None = None

    def on_quest_update(self, callback: OnQuestUpdate) -> None:
        self._on_quest_update = callback

    async def connect(self) -> None:
        self._running = True
        while self._running:
            try:
                self.ws = await websockets.client.connect(GATEWAY_URL, max_size=2**22)
                log.info("gateway.connected")
                hello = json.loads(await self.ws.recv())
                interval = hello.get("d", {}).get("heartbeat_interval", 41250) / 1000
                asyncio.create_task(self._heartbeat_loop(interval))
                await self._identify()
                await self._listen()
            except asyncio.CancelledError:
                break
            except websockets.exceptions.ConnectionClosed:
                log.info("gateway.disconnected_reconnect")
                await asyncio.sleep(5)
                continue
            except Exception as e:
                log.warn("gateway.error", error=str(e))
                await asyncio.sleep(10)
                continue
            break

    async def _identify(self) -> None:
        payload = {
            "op": 2,
            "d": {
                "token": self.token,
                "capabilities": 30717,
                "properties": {
                    "os": "Windows",
                    "browser": "Discord Client",
                    "device": "",
                    "system_locale": "en-US",
                    "browser_version": "32.2.7",
                    "client_build_number": self.build_number,
                },
                "presence": {"status": "online", "since": 0, "activities": [], "afk": False},
                "compress": False,
                "client_state": {
                    "guild_versions": {},
                    "highest_last_message_id": 0,
                    "read_state_version": 0,
                    "user_guild_settings_version": -1,
                },
            },
        }
        await self.ws.send(json.dumps(payload))
        log.info("gateway.identified")

    async def _heartbeat_loop(self, interval: float) -> None:
        while self._running:
            await asyncio.sleep(interval)
            try:
                await self.ws.send(json.dumps({"op": 1, "d": self.seq}))
            except Exception:
                break

    async def _listen(self) -> None:
        while self._running:
            try:
                msg = json.loads(await self.ws.recv())
                op = msg.get("op")
                if op == 0:
                    self.seq = msg.get("s")
                    t = msg.get("t", "")
                    if t == "USER_QUEST_UPDATE" and self._on_quest_update:
                        self._on_quest_update(msg.get("d", {}))
                elif op == 7:
                    log.info("gateway.reconnect_requested")
                    break
                elif op == 9:
                    log.info("gateway.invalid_session")
                    break
            except websockets.exceptions.ConnectionClosed:
                break
            except Exception as e:
                log.warn("gateway.listen_error", error=str(e))

    async def close(self) -> None:
        self._running = False
        if self.ws:
            await self.ws.close()
