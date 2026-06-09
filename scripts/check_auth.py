"""Manual end-to-end check of SSO login + sport API (no bot, no DB).

Usage:
    python -m scripts.check_auth <login> <password>

Verifies that we can obtain an ADFS token and read profile/sports/trainings.
Prints what it finds so you can confirm endpoint shapes against your account.
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta, timezone

import httpx

from app.config import get_settings
from app.sport.auth import SsoAuth


async def main(login: str, password: str) -> None:
    s = get_settings()
    sso = SsoAuth(sso_base=s.sso_base, client_id=s.oauth_client_id, redirect_uri=s.oauth_redirect_uri)

    print("→ logging in via SSO ...")
    cookies = await sso.login(login, password)
    print(f"  got cookies: {list(cookies.keys())}")

    headers = {"Accept": "application/json", "Referer": f"{sso.site_root}/"}
    async with httpx.AsyncClient(
        base_url=s.sport_api_base, headers=headers, cookies=cookies, timeout=20
    ) as c:
        prof = await c.get("/profile/student")
        print(f"→ /profile/student: {prof.status_code}")
        print("  ", str(prof.text)[:300])

        sports = await c.get("/sports")
        print(f"→ /sports: {sports.status_code}")
        if sports.status_code == 200:
            for sp in sports.json().get("sports", [])[:10]:
                print(f"   - {sp.get('id')}: {sp.get('name')} (free={sp.get('free_places')})")

        now = datetime.now(timezone.utc)
        cal = await c.get(
            "/calendar/trainings",
            params={"start": now.isoformat(), "end": (now + timedelta(days=8)).isoformat()},
        )
        print(f"→ /calendar/trainings: {cal.status_code}")
        if cal.status_code == 200:
            for t in cal.json()[:10]:
                ext = t.get("extendedProps", {})
                print(
                    f"   - training_id={ext.get('id')} group={ext.get('group_id')} "
                    f"{t.get('start')} '{t.get('title')}' "
                    f"can_check_in={ext.get('can_check_in')} checked_in={ext.get('checked_in')}"
                )


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    asyncio.run(main(sys.argv[1], sys.argv[2]))
