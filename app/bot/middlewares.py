from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.bot.texts import NOT_ALLOWED


class AccessMiddleware(BaseMiddleware):
    """Restrict the bot to a whitelist of Telegram user ids (empty = allow all)."""

    def __init__(self, allowed_ids: set[int]) -> None:
        self._allowed = allowed_ids

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if self._allowed:
            user = data.get("event_from_user")
            if user is not None and user.id not in self._allowed:
                if isinstance(event, Message):
                    await event.answer(NOT_ALLOWED)
                elif isinstance(event, CallbackQuery):
                    await event.answer(NOT_ALLOWED, show_alert=True)
                return None
        return await handler(event, data)
