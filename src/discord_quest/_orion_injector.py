from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

import httpx
import structlog

log = structlog.get_logger(__name__)

ORION_RAW_URL = "https://raw.githubusercontent.com/nyxxbit/discord-quest-completer/main/index.js"
ORION_EXPECTED_HASH = "a7f82997a3b75cfa9d98c008fcaea78f1cdb87284c5eefc8a31526c02e9f1c20"
CACHE_DIR = Path(".orion_cache")
CACHE_FILE = CACHE_DIR / "index.js"
CACHE_HASH = CACHE_DIR / "index.sha256"

JS_BRIDGE = """
() => {
    if (window.__orionInjected) return true;
    window.__orionInjected = true;
    window.__orionBridge = {
        getQuests: () => {
            const s = window.__findStore?.('QuestStore') || window.__findStore?.('QuestsStore');
            if (!s) return [];
            const q = s.quests || s.getState?.()?.quests || {};
            const l = q instanceof Map ? [...q.values()] : Object.values(q);
            return l.map(x => ({ id: x.id, config: x.config, userStatus: x.userStatus }));
        },
        getCompleted: () => {
            const s = window.__findStore?.('QuestStore') || window.__findStore?.('QuestsStore');
            if (!s) return [];
            const q = s.quests || s.getState?.()?.quests || {};
            const l = q instanceof Map ? [...q.values()] : Object.values(q);
            const has = x => x.userStatus?.completedAt || x.userStatus?.completed_at;
            return l.filter(has).map(x => x.id);
        },
    };
    return true;
}
"""


async def fetch_orion_source(*, force: bool = False) -> str:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if not force and CACHE_FILE.exists():
        log.info("orion.using_cached")
        return CACHE_FILE.read_text(encoding="utf-8")
    log.info("orion.fetching", url=ORION_RAW_URL)
    async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
        r = await client.get(ORION_RAW_URL)
        r.raise_for_status()
        source = r.text
    actual_hash = hashlib.sha256(source.encode()).hexdigest()
    if actual_hash != ORION_EXPECTED_HASH:
        log.error(
            "orion.hash_mismatch",
            expected=ORION_EXPECTED_HASH,
            actual=actual_hash,
            size=len(source),
        )
        short_expected = ORION_EXPECTED_HASH[:16]
        msg = f"Orion hash mismatch: expected {short_expected}..., got {actual_hash[:16]}..."
        raise ValueError(msg)
    CACHE_FILE.write_text(source, encoding="utf-8")
    CACHE_HASH.write_text(actual_hash)
    log.info("orion.cached", size=len(source))
    return source


async def inject_orion(page, *, force_fetch: bool = False) -> bool:
    for attempt in range(3):
        try:
            source = await fetch_orion_source(force=(force_fetch and attempt > 0))
            await page.evaluate(source)
            await page.evaluate(JS_BRIDGE)
            log.info("orion.injected")
            return True
        except Exception as e:
            log.warn("orion.inject_retry", attempt=attempt, error=str(e))
            await asyncio.sleep(2)
    log.error("orion.inject_failed")
    return False
