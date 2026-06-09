"""Job coroutines executed by APScheduler.

burst_check_in -- fires ~burst_lead_seconds before sign-up opens, then hammers the
check_in endpoint every burst_interval_ms (with jitter) until it succeeds or the
burst window elapses. This is the only time we send rapid requests.

watch_check_in -- low-frequency poll that grabs a freed spot any time after sign-up
has opened.
"""
from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, timezone

from app.db.repo import Database
from app.sport.errors import AlreadyCheckedIn, CannotCheckIn, SportError

log = logging.getLogger(__name__)


async def _try_check_in(client, db: Database, tg_id: int, rule_id: int, training_id: int) -> bool:
    """Attempt one check-in. Returns True if checked in (now or already)."""
    user = await db.get_user(tg_id)
    if user is None:
        return True  # user gone: stop trying
    try:
        await client.check_in(user, training_id)
        return True
    except AlreadyCheckedIn:
        return True
    except CannotCheckIn:
        return False  # full / outside window / hour limits -> keep trying
    except SportError as exc:
        log.warning("check_in rule=%s training=%s error: %s", rule_id, training_id, exc)
        return False


async def burst_check_in(
    *, client, db: Database, notify, settings, tg_id, rule_id, training_id, open_at, title
) -> None:
    interval = settings.burst_interval_ms / 1000.0
    deadline = datetime.now(timezone.utc).timestamp() + settings.burst_max_seconds

    # Pre-warm the auth token and the persistent TCP/TLS connection so the
    # first real attempt is instant.
    user = await db.get_user(tg_id)
    if user is not None:
        try:
            await client.get_training(user, training_id)
        except Exception:  # noqa: BLE001
            pass

    # Wait out the final sliver until sign-up actually opens.
    while True:
        remaining = open_at.timestamp() - datetime.now(timezone.utc).timestamp()
        if remaining <= 0:
            break
        await asyncio.sleep(min(remaining, 0.2))

    while datetime.now(timezone.utc).timestamp() < deadline:
        if await _try_check_in(client, db, tg_id, rule_id, training_id):
            await db.set_rule_result(rule_id, f"✅ {title} ({datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC)")
            await notify(tg_id, f"✅ Записал на «{title}» (открытие записи)")
            return
        await asyncio.sleep(interval + random.uniform(0, interval / 2))

    # No notification on a missed burst -- watch-mode keeps trying silently.
    await db.set_rule_result(rule_id, f"⏳ burst не успел: {title}")


async def watch_check_in(
    *, client, db: Database, notify, scheduler, tg_id, rule_id, training_id, title
) -> None:
    user = await db.get_user(tg_id)
    if user is None:
        _remove(scheduler, f"watch:{rule_id}:{training_id}")
        return
    try:
        info = await client.get_training(user, training_id)
    except SportError as exc:
        log.warning("watch get_training rule=%s: %s", rule_id, exc)
        return

    if info.checked_in:
        _remove(scheduler, f"watch:{rule_id}:{training_id}")
        return

    if info.free_places > 0 or info.can_check_in:
        if await _try_check_in(client, db, tg_id, rule_id, training_id):
            await db.set_rule_result(rule_id, f"✅ {title} (освободилось место)")
            await notify(tg_id, f"✅ Поймал свободное место и записал на «{title}»")
            _remove(scheduler, f"watch:{rule_id}:{training_id}")


def _remove(scheduler, job_id: str) -> None:
    try:
        scheduler.remove_job(job_id)
    except Exception:  # noqa: BLE001
        pass
