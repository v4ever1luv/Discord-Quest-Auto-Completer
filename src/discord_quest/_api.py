from __future__ import annotations

import base64
import json
import random
import re
from typing import Any

import httpx
import structlog

from ._config import settings

log = structlog.get_logger(__name__)


def _fetch_build_number() -> int:
    try:
        ua = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/128.0.0.0 Safari/537.36"
        )
        r = httpx.get(
            "https://discord.com/app",
            headers={"User-Agent": ua},
            timeout=15,
        )
        if r.status_code != 200:
            log.warn("fetch_build_number.http_error", status=r.status_code)
            return settings.build_fallback

        scripts = re.findall(r"/assets/([a-f0-9]+)\.js", r.text)
        if not scripts:
            alt = re.findall(r'src="(/assets/[^"]+\.js)"', r.text)
            scripts = [s.split("/")[-1].replace(".js", "") for s in alt]

        if not scripts:
            log.warn("fetch_build_number.no_scripts")
            return settings.build_fallback

        for h in scripts[-5:]:
            try:
                ar = httpx.get(
                    f"https://discord.com/assets/{h}.js",
                    headers={"User-Agent": ua},
                    timeout=15,
                )
                m = re.search(r'buildNumber["\s:]+["\s]*(\d{5,7})', ar.text)
                if m:
                    bn = int(m.group(1))
                    log.info("fetch_build_number.ok", build=bn)
                    return bn
            except Exception:
                continue

        log.warn("fetch_build_number.not_found")
        return settings.build_fallback
    except Exception as e:
        log.warn("fetch_build_number.error", error=str(e))
        return settings.build_fallback


def make_super_properties(build_number: int, mobile: bool = False) -> str:
    if mobile:
        obj = {
            "os": "Android",
            "browser": "Discord Android",
            "release_channel": "stable",
            "client_version": "281.0",
            "os_version": "35",
            "os_arch": "aarch64",
            "app_arch": "arm64",
            "system_locale": "en-US",
            "browser_user_agent": "Discord-Android/281.0",
            "browser_version": "281.0",
            "client_build_number": build_number,
            "native_build_number": build_number,
            "client_event_source": None,
        }
    else:
        obj = {
            "os": "Windows",
            "browser": "Discord Client",
            "release_channel": "stable",
            "client_version": "1.0.9175",
            "os_version": "10.0.26100",
            "os_arch": "x64",
            "app_arch": "x64",
            "system_locale": "en-US",
            "browser_user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "discord/1.0.9175 Chrome/128.0.6613.186 "
                "Electron/32.2.7 Safari/537.36"
            ),
            "browser_version": "32.2.7",
            "client_build_number": build_number,
            "native_build_number": 59498,
            "client_event_source": None,
        }
    return base64.b64encode(json.dumps(obj).encode()).decode()


class DiscordAPI:
    def __init__(
        self,
        token: str,
        build_number: int,
        proxy: str | None = None,
    ) -> None:
        self.token = token
        self.build_number = build_number
        self.timeout = settings.request_timeout

        limits = httpx.Limits(
            max_keepalive_connections=10,
            max_connections=20,
            keepalive_expiry=60,
        )

        client_kwargs: dict[str, Any] = {
            "base_url": settings.api_base,
            "limits": limits,
            "timeout": httpx.Timeout(self.timeout, connect=15),
            "default_encoding": "utf-8",
        }

        if proxy:
            client_kwargs["proxies"] = {"http://": proxy, "https://": proxy}

        self.client = httpx.AsyncClient(**client_kwargs)

        ua = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "discord/1.0.9175 Chrome/128.0.6613.186 "
            "Electron/32.2.7 Safari/537.36"
        )
        sp = make_super_properties(build_number)
        self.client.headers.update(
            {
                "Authorization": token,
                "Content-Type": "application/json",
                "Accept": "*/*",
                "Accept-Language": "en-US,en;q=0.9",
                "User-Agent": ua,
                "X-Super-Properties": sp,
                "X-Discord-Locale": "en-US",
                "X-Discord-Timezone": "Asia/Ho_Chi_Minh",
                "Origin": "https://discord.com",
                "Referer": "https://discord.com/channels/@me",
            }
        )

    _ROTATE_UAS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        " (KHTML, like Gecko) discord/1.0.9175 Chrome/128.0.6613.186"
        " Electron/32.2.7 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        " (KHTML, like Gecko) discord/1.0.9176 Chrome/128.0.6613.187"
        " Electron/32.2.8 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        " (KHTML, like Gecko) discord/1.0.9177 Chrome/128.0.6613.188"
        " Electron/32.2.9 Safari/537.36",
    ]

    _ROTATE_LOCALES = ["en-US", "en-GB", "en", "vi-VN", "ja-JP"]

    def _rotate_headers(self) -> None:
        if not settings.anti_detect:
            return
        self.client.headers["User-Agent"] = random.choice(self._ROTATE_UAS)
        loc = random.choice(self._ROTATE_LOCALES)
        self.client.headers["Accept-Language"] = f"{loc},en;q=0.9"
        self.client.headers["X-Discord-Locale"] = loc
        bn = self.build_number + random.randint(-5, 5)
        self.client.headers["X-Super-Properties"] = make_super_properties(bn)

    async def get(self, path: str, **kwargs: Any) -> httpx.Response:
        kwargs.setdefault("timeout", self.timeout)
        self._rotate_headers()
        log.debug("http.get", path=path)
        r = await self.client.get(path, **kwargs)
        log.debug("http.get_done", path=path, status=r.status_code, size=len(r.content))
        return r

    async def post(
        self,
        path: str,
        payload: dict[str, Any] | None = None,
        is_mobile: bool = False,
        **kwargs: Any,
    ) -> httpx.Response:
        kwargs.setdefault("timeout", self.timeout)
        if is_mobile:
            kwargs.setdefault("headers", {})
            kwargs["headers"].setdefault(
                "X-Super-Properties", make_super_properties(self.build_number, mobile=True)
            )
            kwargs["headers"].setdefault("User-Agent", "Discord-Android/281.0")
        log.debug("http.post", path=path, mobile=is_mobile)
        r = await self.client.post(path, json=payload, **kwargs)
        log.debug("http.post_done", path=path, status=r.status_code, size=len(r.content))
        return r

    async def validate_token(self) -> bool:
        try:
            r = await self.get("/users/@me")
            if r.status_code == 200:
                user = r.json()
                name = user.get("username", "?")
                log.info("auth.ok", username=name, user_id=user["id"])
                return True
            log.error("auth.invalid_token", status=r.status_code)
            return False
        except httpx.TimeoutException:
            log.error("auth.timeout")
            return False
        except Exception as e:
            log.error("auth.error", error=str(e))
            return False

    async def close(self) -> None:
        await self.client.aclose()
