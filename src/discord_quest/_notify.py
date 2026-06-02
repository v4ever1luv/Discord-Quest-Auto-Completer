from __future__ import annotations

import httpx
import structlog

from ._config import settings

log = structlog.get_logger(__name__)


def _build_message(quest_id: str, reward: str, task_type: str) -> dict[str, str]:
    title = f"✅ Quest completed: `{task_type}`"
    desc = f"**Quest ID:** `{quest_id}`\n**Reward:** {reward}"
    return {"title": title, "description": desc}


async def notify_discord_webhook(quest_id: str, reward: str, task_type: str) -> None:
    url = settings.notify_webhook_url
    if not url:
        return
    msg = _build_message(quest_id, reward, task_type)
    payload = {
        "embeds": [{"title": msg["title"], "description": msg["description"], "color": 0x57F287}],
    }
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(url, json=payload, timeout=10)
            if r.status_code not in (200, 204):
                log.warn("notify.webhook_error", status=r.status_code)
            else:
                log.info("notify.webhook_sent", quest_id=quest_id)
    except Exception as e:
        log.debug("notify.webhook_exception", error=str(e))


async def notify_telegram(quest_id: str, reward: str, task_type: str) -> None:
    token = settings.notify_telegram_token
    chat_id = settings.notify_telegram_chat_id
    if not token or not chat_id:
        return
    msg = _build_message(quest_id, reward, task_type)
    text = f"{msg['title']}\n{msg['description']}"
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                url, json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}, timeout=10
            )
            if r.status_code != 200:
                log.warn("notify.telegram_error", status=r.status_code)
            else:
                log.info("notify.telegram_sent", quest_id=quest_id)
    except Exception as e:
        log.debug("notify.telegram_exception", error=str(e))


async def send_notification(quest_id: str, reward: str = "", task_type: str = "") -> None:
    await notify_discord_webhook(quest_id, reward, task_type)
    await notify_telegram(quest_id, reward, task_type)
