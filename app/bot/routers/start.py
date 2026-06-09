from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot import texts
from app.db.repo import Database

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message, db: Database) -> None:
    await db.upsert_user(message.from_user.id)
    await message.answer(texts.START)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(texts.HELP)


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    if await state.get_state() is None:
        await message.answer(texts.NOTHING_TO_CANCEL)
        return
    await state.clear()
    await message.answer(texts.CANCELLED)


@router.callback_query(lambda c: c.data == "noop")
async def noop(call: CallbackQuery) -> None:
    await call.answer()
