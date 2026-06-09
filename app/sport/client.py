"""Authenticated client for the Innopolis sport API (Django session cookie auth).

One session per user: lazily logs in via SSO, caches the {sessionid, csrftoken}
cookies in memory and (encrypted) in the DB, and re-logs-in on a 401/403. Unsafe
methods carry the CSRF token + Referer that Django's SessionAuthentication requires.
Requests for a given user are serialized with a per-user lock.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

import httpx

from app.crypto import Crypto
from app.db.models import User
from app.db.repo import Database
from app.sport.auth import SsoAuth
from app.sport.errors import (
    AlreadyCheckedIn,
    AuthError,
    AuthExpired,
    CannotCheckIn,
    CheckInError,
    SportError,
)
from app.sport.models import Sport, TrainingInfo, TrainingSlot

_BROWSER_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
# Django default session age is 2 weeks; refresh well before that.
_SESSION_TTL = timedelta(days=10)


def _parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class SportClient:
    def __init__(self, *, api_base: str, db: Database, crypto: Crypto, sso: SsoAuth) -> None:
        self._api_base = api_base.rstrip("/")
        self._db = db
        self._crypto = crypto
        self._sso = sso
        self._cookies: dict[int, dict[str, str]] = {}
        self._locks: dict[int, asyncio.Lock] = {}

    def _lock(self, tg_id: int) -> asyncio.Lock:
        return self._locks.setdefault(tg_id, asyncio.Lock())

    # --- session management ---
    def _load_cached_cookies(self, user: User) -> dict[str, str] | None:
        cached = self._cookies.get(user.tg_id)
        if cached is not None:
            return cached
        if user.access_token_enc and user.token_expires_at:
            expires = user.token_expires_at
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) >= expires:
                return None
            try:
                cookies = json.loads(self._crypto.decrypt(user.access_token_enc))
            except Exception:  # noqa: BLE001
                return None
            self._cookies[user.tg_id] = cookies
            return cookies
        return None

    async def _persist_cookies(self, tg_id: int, cookies: dict[str, str]) -> None:
        self._cookies[tg_id] = cookies
        await self._db.set_tokens(
            tg_id,
            self._crypto.encrypt(json.dumps(cookies)),
            None,
            datetime.now(timezone.utc) + _SESSION_TTL,
        )

    async def _relogin(self, user: User) -> dict[str, str]:
        if not user.sport_login or not user.password_enc:
            raise AuthError("нет сохранённых данных входа; используй /login")
        password = self._crypto.decrypt(user.password_enc)
        cookies = await self._sso.login(user.sport_login, password)
        await self._persist_cookies(user.tg_id, cookies)
        return cookies

    async def _cookies_for(self, user: User) -> dict[str, str]:
        cookies = self._load_cached_cookies(user)
        if cookies is not None:
            return cookies
        return await self._relogin(user)

    async def login_and_store(self, user: User) -> None:
        """Force a fresh login (used by the bot login wizard to validate creds)."""
        async with self._lock(user.tg_id):
            await self._relogin(user)

    # --- low-level request with one auth retry ---
    async def _request(self, user: User, method: str, path: str, **kwargs) -> httpx.Response:
        url = f"{self._api_base}/{path.lstrip('/')}"
        async with self._lock(user.tg_id):
            cookies = await self._cookies_for(user)
            async with httpx.AsyncClient(
                timeout=20.0, base_url=self._sso.site_root, follow_redirects=False
            ) as client:
                resp = await self._send(client, method, url, cookies, **kwargs)
                if resp.status_code in (401, 403):
                    self._cookies.pop(user.tg_id, None)
                    cookies = await self._relogin(user)
                    resp = await self._send(client, method, url, cookies, **kwargs)
        if resp.status_code in (401, 403):
            raise AuthExpired("сессия недействительна после повторного входа")
        return resp

    def _send(
        self, client: httpx.AsyncClient, method: str, url: str, cookies: dict[str, str], **kwargs
    ):
        headers = {
            "User-Agent": _BROWSER_UA,
            "Accept": "application/json",
            "Referer": f"{self._sso.site_root}/",
            "Origin": self._sso.site_root,
        }
        if method.upper() != "GET" and cookies.get("csrftoken"):
            headers["X-CSRFToken"] = cookies["csrftoken"]
        headers.update(kwargs.pop("headers", {}))
        return client.request(method, url, headers=headers, cookies=cookies, **kwargs)

    # --- API methods ---
    async def get_profile(self, user: User) -> dict:
        resp = await self._request(user, "GET", "profile/student")
        resp.raise_for_status()
        return resp.json()

    async def get_sports(self, user: User) -> list[Sport]:
        resp = await self._request(user, "GET", "sports")
        resp.raise_for_status()
        return [
            Sport(id=s["id"], name=s["name"], special=bool(s.get("special", False)))
            for s in resp.json().get("sports", [])
        ]

    async def select_sport(self, user: User, sport_id: int) -> None:
        resp = await self._request(user, "POST", "select_sport", json={"sport_id": sport_id})
        if resp.status_code != 200:
            raise SportError(f"select_sport failed: {resp.status_code} {resp.text[:200]}")

    async def get_trainings(
        self, user: User, start: datetime, end: datetime
    ) -> list[TrainingSlot]:
        resp = await self._request(
            user,
            "GET",
            "calendar/trainings",
            params={"start": start.isoformat(), "end": end.isoformat()},
        )
        resp.raise_for_status()
        slots: list[TrainingSlot] = []
        for item in resp.json():
            ext = item.get("extendedProps", {})
            slots.append(
                TrainingSlot(
                    id=ext["id"],
                    group_id=ext["group_id"],
                    title=item.get("title", ""),
                    start=_parse_dt(item["start"]),
                    end=_parse_dt(item["end"]),
                    can_check_in=bool(ext.get("can_check_in", False)),
                    checked_in=bool(ext.get("checked_in", False)),
                )
            )
        return slots

    async def get_training(self, user: User, training_id: int) -> TrainingInfo:
        resp = await self._request(user, "GET", f"training/{training_id}")
        resp.raise_for_status()
        data = resp.json()
        t = data["training"]
        group = t.get("group", {})
        return TrainingInfo(
            id=t["id"],
            group_id=group.get("id", 0),
            title=group.get("name") or t.get("custom_name") or "",
            start=_parse_dt(t["start"]),
            end=_parse_dt(t["end"]),
            load=int(t.get("load", 0)),
            capacity=int(group.get("capacity", 0)),
            can_check_in=bool(data.get("can_check_in", False)),
            checked_in=bool(data.get("checked_in", False)),
        )

    async def check_in(self, user: User, training_id: int) -> None:
        """Raise AlreadyCheckedIn / CannotCheckIn / CheckInError on failure."""
        resp = await self._request(user, "POST", f"training/{training_id}/check_in")
        if resp.status_code == 200:
            return
        if resp.status_code == 404:
            raise CheckInError(None, "training not found")
        try:
            body = resp.json()
            code, detail = body.get("code"), body.get("detail", "")
        except Exception:  # noqa: BLE001
            code, detail = None, resp.text[:200]
        if code == 1:
            raise AlreadyCheckedIn(code, detail)
        if code == 2:
            raise CannotCheckIn(code, detail)
        raise CheckInError(code, detail or f"HTTP {resp.status_code}")

    async def cancel_check_in(self, user: User, training_id: int) -> None:
        resp = await self._request(user, "POST", f"training/{training_id}/cancel_check_in")
        if resp.status_code != 200:
            raise CheckInError(None, f"cancel failed: {resp.status_code} {resp.text[:200]}")
