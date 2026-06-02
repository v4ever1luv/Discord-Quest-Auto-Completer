from __future__ import annotations

import asyncio
import random
from pathlib import Path
from typing import Any

import structlog
from playwright.async_api import BrowserContext, Page, Playwright, async_playwright

from ._config import settings
from ._models import Quest, UserStatus
from ._orion_injector import inject_orion

log = structlog.get_logger(__name__)

STEALTH_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
Object.defineProperty(navigator, 'plugins', {
    get: () => [0, 1, 2, 3, 4, 5].map(() => ({ name: 'Chrome PDF Plugin' })),
});
"""

JS_INIT_WEBPACK = """
() => {
    if (window.__wpReady) return true;
    const chunk = window.webpackChunkdiscord_app;
    if (!chunk) return false;
    let req = null;
    chunk.push([[Symbol()], {}, (r) => { req = r; }]);
    chunk.pop();
    if (!req) return false;
    window.__wpCache = req.c;
    window.__wpReady = true;

    window.__findStore = function(name) {
        for (const id in window.__wpCache) {
            try {
                const mod = window.__wpCache[id].exports;
                const store = mod?.default || mod;
                if (store?.constructor?.displayName === name) return store;
            } catch {}
        }
        return null;
    };

    window.__findAPI = function() {
        for (const id in window.__wpCache) {
            try {
                const mod = window.__wpCache[id].exports;
                const target = mod?.default || mod;
                if (typeof target?.post === 'function' && !target._dispatcher) return target;
            } catch {}
        }
        return null;
    };

    return true;
}
"""

JS_GET_QUESTS = """
() => {
    if (!window.__wpReady) return [];
    const store = window.__findStore('QuestStore') || window.__findStore('QuestsStore');
    if (!store) return [];
    const quests = store.quests || store.getState?.()?.quests || {};
    const list = quests instanceof Map ? [...quests.values()] : Object.values(quests);
    return list.map(q => ({
        id: q.id,
        config: q.config,
        userStatus: q.userStatus,
    }));
}
"""

JS_ENROLL = """
(id) => {
    if (!window.__wpReady) return { error: 'Webpack not loaded' };
    const api = window.__findAPI();
    if (!api) return { error: 'API module not found' };
    try {
        return api.post({ url: '/quests/' + id + '/enroll', body: { location: 11, is_targeted: false } });
    } catch (e) {
        return { error: e.message };
    }
}
"""

JS_VIDEO_PROGRESS = """
(p) => {
    if (!window.__wpReady) return { error: 'Webpack not loaded' };
    const api = window.__findAPI();
    if (!api) return { error: 'API module not found' };
    try {
        return api.post({ url: '/quests/' + p.id + '/video-progress', body: { timestamp: p.ts } });
    } catch (e) {
        return { error: e.message };
    }
}
"""

JS_GET_QUEST_FROM_STORE = """
(id) => {
    if (!window.__wpReady) return null;
    const store = window.__findStore('QuestStore') || window.__findStore('QuestsStore');
    if (!store) return null;
    const quests = store.quests || store.getState?.()?.quests || {};
    const list = quests instanceof Map ? [...quests.values()] : Object.values(quests);
    const q = list.find(x => x.id === id);
    return q || null;
}
"""


class PlaywrightClient:
    def __init__(
        self,
        token: str,
        headless: bool = False,
        user_data_dir: str | None = None,
    ) -> None:
        self.token = token
        self.headless = headless
        self._user_data_dir = user_data_dir or settings.user_data_dir
        self._playwright: Playwright | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._ready = False
        self._orion_ready = False
        self._logged_in = False

    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("Browser not started")
        return self._page

    async def start(self) -> None:
        profile_path = Path(self._user_data_dir).resolve()
        profile_path.mkdir(parents=True, exist_ok=True)
        log.info("playwright.profile", path=str(profile_path))

        self._playwright = await async_playwright().start()

        self._context = await self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(profile_path),
            headless=self.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
            no_viewport=True,
        )

        self._page = (
            self._context.pages[0] if self._context.pages else await self._context.new_page()
        )

        await self._page.add_init_script(STEALTH_SCRIPT)

        await self._login()
        await self._init_webpack()
        await self._init_orion()
        log.info("playwright.client_ready")

    async def _login(self) -> None:
        page = self.page

        if await self._is_logged_in():
            log.info("playwright.session_valid")
            self._logged_in = True
            return

        log.info("playwright.login_first_time")

        await page.add_init_script(f"""
            localStorage.setItem('token', '{self.token}');
        """)

        await page.goto("https://discord.com/app", wait_until="domcontentloaded")

        for i in range(60):
            if not self._page:
                return
            url = page.url
            if "login" not in url:
                self._logged_in = True
                log.info("playwright.logged_in", url=url)
                return
            if i == 5:
                log.info("playwright.login.waiting")
            await asyncio.sleep(1)

        if self._page:
            log.warn("playwright.login.timeout", url=page.url)

    async def _is_logged_in(self) -> bool:
        page = self.page
        try:
            await page.goto("https://discord.com/app", wait_until="domcontentloaded", timeout=15000)
            await asyncio.sleep(2)
            url = page.url
            return "login" not in url
        except Exception:
            return False

    async def _init_webpack(self) -> None:
        page = self.page

        for i in range(30):
            try:
                ready = await page.evaluate(JS_INIT_WEBPACK)
                if ready:
                    self._ready = True
                    log.info("playwright.webpack.ready")
                    return
            except Exception as e:
                log.debug("playwright.webpack.retry", attempt=i, error=str(e))
            await asyncio.sleep(1)

        log.warn("playwright.webpack.timeout")

    async def _init_orion(self) -> None:
        if self._orion_ready:
            return
        self._orion_ready = await inject_orion(self.page)

    async def _ensure_page_alive(self) -> bool:
        if self._page is not None:
            try:
                await self._page.evaluate("1")
                return True
            except Exception:
                log.warn("playwright.page_dead_recovering")
                self._ready = False
                self._logged_in = False
                self._orion_ready = False

        if self._context is not None:
            try:
                self._page = await self._context.new_page()
                await self._page.add_init_script(STEALTH_SCRIPT)
                log.info("playwright.page_recovered")
                return True
            except Exception:
                log.warn("playwright.context_dead_restarting")

        return await self._restart_browser()

    async def _restart_browser(self) -> bool:
        await self.close()
        try:
            profile_path = Path(self._user_data_dir).resolve()
            self._playwright = await async_playwright().start()
            self._context = await self._playwright.chromium.launch_persistent_context(
                user_data_dir=str(profile_path),
                headless=self.headless,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
                no_viewport=True,
            )
            self._page = (
                self._context.pages[0] if self._context.pages else await self._context.new_page()
            )
            await self._page.add_init_script(STEALTH_SCRIPT)
            await self._login()
            await self._init_webpack()
            await self._init_orion()
            log.info("playwright.restarted")
            return True
        except Exception as e:
            log.error("playwright.restart_failed", error=str(e))
            return False

    async def ensure_ready(self) -> bool:
        if not await self._ensure_page_alive():
            return False
        page = self._page
        if page is None:
            return False

        if not self._ready:
            await self._init_webpack()
            return self._ready

        try:
            await page.wait_for_load_state("domcontentloaded", timeout=5000)
            url = page.url
            if "login" in url:
                log.warn("playwright.session_expired")

                await page.add_init_script(f"""
                    localStorage.setItem('token', '{self.token}');
                """)
                await page.goto("https://discord.com/app", wait_until="domcontentloaded")

                for _ in range(30):
                    cur = page.url
                    if "login" not in cur:
                        self._logged_in = True
                        break
                    await asyncio.sleep(1)

                await self._init_webpack()
                await self._init_orion()
        except Exception:
            log.warn("playwright.ensure_ready.error")
            return False

        return self._ready and self._logged_in

    async def get_quests(self) -> list[Quest]:
        if not await self.ensure_ready():
            return []

        try:
            raw = await self.page.evaluate(JS_GET_QUESTS)
        except Exception as e:
            log.warn("playwright.evaluate_error", error=str(e))
            self._ready = False
            return []

        if not raw:
            return []

        quests = []
        for r in raw:
            try:
                us = None
                if r.get("userStatus"):
                    us_raw = r["userStatus"]
                    progress = {}
                    for k, v in (us_raw.get("progress") or {}).items():
                        if isinstance(v, dict):
                            progress[k] = v.get("value", 0.0)
                    us = UserStatus(
                        enrolled_at=us_raw.get("enrolledAt") or us_raw.get("enrolled_at"),
                        completed_at=us_raw.get("completedAt") or us_raw.get("completed_at"),
                        progress=progress,
                    )
                quests.append(
                    Quest(
                        id=r.get("id", ""),
                        config=r.get("config", {}),
                        user_status=us,
                        raw=r,
                    )
                )
            except Exception as e:
                log.debug("playwright.parse_quest_error", error=str(e))

        log.info("playwright.quests_fetched", count=len(quests))
        return quests

    async def get_quest_from_store(self, quest_id: str) -> dict[str, Any] | None:
        if not await self.ensure_ready():
            return None
        try:
            return await self.page.evaluate(JS_GET_QUEST_FROM_STORE, quest_id)
        except Exception:
            return None

    async def enroll_quest(self, quest_id: str) -> dict[str, Any]:
        await asyncio.sleep(random.uniform(0.5, 2.0))
        try:
            result = await self.page.evaluate(JS_ENROLL, quest_id)
            return result or {}
        except Exception as e:
            log.warn("playwright.enroll_error", quest_id=quest_id, error=str(e))
            return {"error": str(e)}

    async def send_video_progress(self, quest_id: str, timestamp: float) -> dict[str, Any]:
        ts = round(timestamp, 6)
        try:
            result = await self.page.evaluate(JS_VIDEO_PROGRESS, {"id": quest_id, "ts": ts})
            return result or {}
        except Exception as e:
            log.warn("playwright.video_error", quest_id=quest_id, error=str(e))
            return {"error": str(e)}

    async def close(self) -> None:
        if self._context:
            await self._context.close()
        if self._playwright:
            await self._playwright.stop()
        self._ready = False
        self._logged_in = False
        self._orion_ready = False
        self._page = None
        self._context = None
        self._playwright = None
        log.info("playwright.closed")

    @property
    def is_ready(self) -> bool:
        return self._ready and self._logged_in
