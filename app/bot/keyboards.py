from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.texts import WEEKDAYS, WEEKDAYS_FULL
from app.db.models import Rule, RuleMode


def slots_keyboard(slots: list[dict]) -> InlineKeyboardMarkup:
    """Slots grouped by weekday with a non-clickable header per day.

    `slots` is expected to be sorted by (weekday, time); each item keeps its index
    in that list so the `slot:<idx>` callback maps back to it.
    """
    kb = InlineKeyboardBuilder()
    current_day: int | None = None
    for idx, s in enumerate(slots):
        if s["weekday"] != current_day:
            current_day = s["weekday"]
            kb.row(
                InlineKeyboardButton(
                    text=f"📅 {WEEKDAYS_FULL[current_day]}", callback_data="noop"
                )
            )
        kb.row(
            InlineKeyboardButton(
                text=f"🕒 {s['time']} · {s['title']}", callback_data=f"slot:{idx}"
            )
        )
    return kb.as_markup()


def mode_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⚡ В момент открытия", callback_data=f"mode:{RuleMode.scheduled.value}")],
            [InlineKeyboardButton(text="👀 Ловить место", callback_data=f"mode:{RuleMode.watch.value}")],
            [InlineKeyboardButton(text="⚡+👀 Оба", callback_data=f"mode:{RuleMode.both.value}")],
        ]
    )


def rules_keyboard(rules: list[Rule]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for r in rules:
        state = "🟢" if r.active else "⚪"
        kb.row(
            InlineKeyboardButton(
                text=f"{state} {WEEKDAYS[r.weekday]} {r.start_time:%H:%M} · {r.title}",
                callback_data=f"rule_toggle:{r.id}",
            ),
            InlineKeyboardButton(text="🗑", callback_data=f"rule_del:{r.id}"),
        )
    return kb.as_markup()
