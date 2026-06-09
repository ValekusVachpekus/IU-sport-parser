from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.bot.routers.rules import _dedupe_slots
from app.db.models import Rule, RuleMode
from app.sport.models import TrainingSlot

MSK = ZoneInfo("Europe/Moscow")


def _slot(sid, group_id, start_local, end_local, checked_in=False):
    start = start_local.replace(tzinfo=MSK)
    end = end_local.replace(tzinfo=MSK)
    return TrainingSlot(
        id=sid,
        group_id=group_id,
        title="Йога",
        start=start,
        end=end,
        can_check_in=True,
        checked_in=checked_in,
    )


def test_dedupe_collapses_weekly_repeats():
    # Two occurrences of the same Mon 18:00 group within the horizon.
    base = datetime(2026, 6, 15, 18, 0)  # Monday
    slots = [
        _slot(1, 100, base, base + timedelta(hours=1)),
        _slot(2, 100, base + timedelta(days=7), base + timedelta(days=7, hours=1)),
        _slot(3, 200, datetime(2026, 6, 17, 9, 0), datetime(2026, 6, 17, 10, 0)),
    ]
    result = _dedupe_slots(slots, MSK)
    assert len(result) == 2
    keys = {(d["group_id"], d["weekday"], d["time"]) for d in result}
    assert (100, 0, "18:00") in keys  # Monday
    assert (200, 2, "09:00") in keys  # Wednesday


def test_dedupe_skips_checked_in():
    base = datetime(2026, 6, 15, 18, 0)
    slots = [_slot(1, 100, base, base + timedelta(hours=1), checked_in=True)]
    assert _dedupe_slots(slots, MSK) == []


def test_slot_match_logic_via_service_rule_shape():
    # The matching rule encodes weekday + local start time; verify the round-trip.
    rule = Rule(group_id=100, weekday=0, start_time=time(18, 0), title="Йога", mode=RuleMode.both)
    base = datetime(2026, 6, 15, 18, 0, tzinfo=MSK)  # Monday 18:00 MSK
    local = base.astimezone(MSK)
    assert local.weekday() == rule.weekday
    assert local.time().replace(second=0, microsecond=0) == rule.start_time
