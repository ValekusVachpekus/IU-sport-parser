"""Scheduling service: turns Rules into precisely-timed check-in jobs.

Jobs live in an in-memory store and are (re)built by the planner on startup and on
an interval, so a restart simply re-derives everything from the DB + live schedule.
"""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import Settings
from app.db.models import Rule, RuleMode, User
from app.db.repo import Database
from app.scheduler.jobs import burst_check_in, watch_check_in
from app.sport.client import SportClient

log = logging.getLogger(__name__)

Notify = Callable[[int, str], Awaitable[None]]

_WEEK = timedelta(days=7)
_HORIZON = timedelta(days=8)  # scan a little past the 7-day open window


class SchedulerService:
    def __init__(
        self,
        *,
        settings: Settings,
        db: Database,
        client: SportClient,
        notify: Notify,
    ) -> None:
        self._settings = settings
        self._db = db
        self._client = client
        self._notify = notify
        self._tz = ZoneInfo(settings.tz)
        self._scheduler = AsyncIOScheduler(timezone=self._tz)

    def start(self) -> None:
        self._scheduler.add_job(
            self.run_planner,
            "interval",
            minutes=self._settings.planner_interval_minutes,
            id="planner",
            replace_existing=True,
            next_run_time=datetime.now(self._tz),  # run once immediately
        )
        self._scheduler.start()
        log.info("scheduler started (planner every %s min)", self._settings.planner_interval_minutes)

    async def run_planner(self) -> None:
        """Scan active rules, resolve concrete trainings, (re)schedule their jobs."""
        rules = await self._db.active_rules()
        by_user: dict[int, list[Rule]] = {}
        for rule in rules:
            by_user.setdefault(rule.user_tg_id, []).append(rule)

        now = datetime.now(timezone.utc)
        for tg_id, user_rules in by_user.items():
            user = await self._db.get_user(tg_id)
            if user is None or not user.sport_login:
                continue
            try:
                slots = await self._client.get_trainings(user, now, now + _HORIZON)
            except Exception as exc:  # noqa: BLE001
                log.warning("planner: cannot fetch trainings for %s: %s", tg_id, exc)
                continue
            self._schedule_user(user, user_rules, slots, now)

    def _schedule_user(self, user: User, rules: list[Rule], slots, now: datetime) -> None:
        for rule in rules:
            for slot in slots:
                if not self._slot_matches(rule, slot):
                    continue
                if slot.checked_in or slot.end <= now:
                    continue
                open_at = slot.start - _WEEK
                self._schedule_slot(user, rule, slot, open_at, now)

    def _slot_matches(self, rule: Rule, slot) -> bool:
        if slot.group_id != rule.group_id:
            return False
        local = slot.start.astimezone(self._tz)
        return local.weekday() == rule.weekday and local.time().replace(
            second=0, microsecond=0
        ) == rule.start_time.replace(second=0, microsecond=0)

    def _schedule_slot(self, user: User, rule: Rule, slot, open_at: datetime, now: datetime) -> None:
        lead = timedelta(seconds=self._settings.burst_lead_seconds)
        wants_scheduled = rule.mode in (RuleMode.scheduled, RuleMode.both)
        wants_watch = rule.mode in (RuleMode.watch, RuleMode.both)

        if wants_scheduled:
            run_at = max(open_at - lead, now + timedelta(seconds=1))
            # Only schedule the burst if sign-up hasn't been open for long already;
            # if we're already well inside the window, watch-mode handles it.
            if run_at <= slot.start:
                self._scheduler.add_job(
                    burst_check_in,
                    "date",
                    run_date=run_at.astimezone(self._tz),
                    id=f"burst:{rule.id}:{slot.id}",
                    replace_existing=True,
                    misfire_grace_time=300,
                    kwargs={
                        "client": self._client,
                        "db": self._db,
                        "notify": self._notify,
                        "settings": self._settings,
                        "tg_id": user.tg_id,
                        "rule_id": rule.id,
                        "training_id": slot.id,
                        "open_at": open_at,
                        "title": rule.title or slot.title,
                    },
                )

        if wants_watch:
            interval = self._settings.watch_interval_seconds
            jitter = self._settings.watch_jitter_seconds
            start_watch = max(open_at, now)
            self._scheduler.add_job(
                watch_check_in,
                "interval",
                seconds=interval,
                jitter=jitter,
                start_date=start_watch.astimezone(self._tz),
                end_date=slot.start.astimezone(self._tz),
                id=f"watch:{rule.id}:{slot.id}",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
                kwargs={
                    "client": self._client,
                    "db": self._db,
                    "notify": self._notify,
                    "scheduler": self._scheduler,
                    "tg_id": user.tg_id,
                    "rule_id": rule.id,
                    "training_id": slot.id,
                    "title": rule.title or slot.title,
                },
            )
