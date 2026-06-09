from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot import texts
from app.bot.keyboards import mode_keyboard, rules_keyboard, slots_keyboard
from app.bot.states import AddRuleFlow
from app.config import Settings
from app.db.models import RuleMode
from app.db.repo import Database
from app.scheduler.service import SchedulerService
from app.sport.client import SportClient
from app.sport.errors import SportError

router = Router(name="rules")

_HORIZON_DAYS = 8


def _dedupe_slots(slots, tz: ZoneInfo) -> list[dict]:
    """Collapse concrete trainings into distinct weekly slots (group+weekday+time)."""
    seen: dict[tuple[int, int, str], dict] = {}
    now = datetime.now(timezone.utc)
    for s in slots:
        if s.end <= now or s.checked_in:
            continue
        local = s.start.astimezone(tz)
        hhmm = local.strftime("%H:%M")
        key = (s.group_id, local.weekday(), hhmm)
        if key not in seen:
            seen[key] = {
                "group_id": s.group_id,
                "weekday": local.weekday(),
                "time": hhmm,
                "title": s.title,
            }
    return sorted(seen.values(), key=lambda d: (d["weekday"], d["time"]))


@router.message(Command("add"))
async def cmd_add(
    message: Message,
    state: FSMContext,
    db: Database,
    client: SportClient,
    settings: Settings,
) -> None:
    user = await db.get_user(message.from_user.id)
    if user is None or not user.sport_login:
        await message.answer(texts.NEED_LOGIN)
        return
    now = datetime.now(timezone.utc)
    try:
        slots = await client.get_trainings(user, now, now + timedelta(days=_HORIZON_DAYS))
    except SportError as exc:
        await message.answer(f"❌ Не смог получить расписание: {exc}")
        return
    deduped = _dedupe_slots(slots, ZoneInfo(settings.tz))
    if not deduped:
        await message.answer(texts.NO_SLOTS)
        return
    await state.set_state(AddRuleFlow.pick_slot)
    await state.update_data(slots=deduped)
    await message.answer(texts.PICK_SLOT, reply_markup=slots_keyboard(deduped))


@router.callback_query(AddRuleFlow.pick_slot, lambda c: c.data and c.data.startswith("slot:"))
async def picked_slot(call: CallbackQuery, state: FSMContext) -> None:
    idx = int(call.data.split(":", 1)[1])
    data = await state.get_data()
    slots = data.get("slots", [])
    if idx >= len(slots):
        await call.answer("Слот устарел, начни заново /add", show_alert=True)
        await state.clear()
        return
    chosen = slots[idx]
    await state.update_data(chosen=chosen)
    await state.set_state(AddRuleFlow.pick_mode)
    await call.message.edit_text(
        texts.PICK_MODE.format(title=chosen["title"]), reply_markup=mode_keyboard()
    )
    await call.answer()


@router.callback_query(AddRuleFlow.pick_mode, lambda c: c.data and c.data.startswith("mode:"))
async def picked_mode(
    call: CallbackQuery,
    state: FSMContext,
    db: Database,
    scheduler: SchedulerService,
) -> None:
    mode = RuleMode(call.data.split(":", 1)[1])
    data = await state.get_data()
    chosen = data["chosen"]
    await state.clear()

    hh, mm = (int(x) for x in chosen["time"].split(":"))
    await db.add_rule(
        tg_id=call.from_user.id,
        group_id=chosen["group_id"],
        weekday=chosen["weekday"],
        start_time=time(hh, mm),
        title=chosen["title"],
        mode=mode,
    )
    await scheduler.run_planner()
    await call.message.edit_text(texts.RULE_ADDED.format(title=chosen["title"]))
    await call.answer()


@router.message(Command("rules"))
async def cmd_rules(message: Message, db: Database) -> None:
    rules = await db.list_rules(message.from_user.id)
    if not rules:
        await message.answer(texts.NO_RULES)
        return
    await message.answer(texts.RULES_HEADER, reply_markup=rules_keyboard(rules))


@router.callback_query(lambda c: c.data and c.data.startswith("rule_del:"))
async def delete_rule(call: CallbackQuery, db: Database) -> None:
    rule_id = int(call.data.split(":", 1)[1])
    await db.delete_rule(rule_id, call.from_user.id)
    rules = await db.list_rules(call.from_user.id)
    if rules:
        await call.message.edit_reply_markup(reply_markup=rules_keyboard(rules))
    else:
        await call.message.edit_text(texts.NO_RULES)
    await call.answer(texts.RULE_DELETED)


@router.callback_query(lambda c: c.data and c.data.startswith("rule_toggle:"))
async def toggle_rule(call: CallbackQuery, db: Database, scheduler: SchedulerService) -> None:
    rule_id = int(call.data.split(":", 1)[1])
    rule = await db.get_rule(rule_id)
    if rule is None or rule.user_tg_id != call.from_user.id:
        await call.answer("Не найдено", show_alert=True)
        return
    await db.set_rule_active(rule_id, call.from_user.id, not rule.active)
    await scheduler.run_planner()
    rules = await db.list_rules(call.from_user.id)
    await call.message.edit_reply_markup(reply_markup=rules_keyboard(rules))
    await call.answer("Готово")
