from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.bot import texts
from app.bot.states import LoginFlow
from app.crypto import Crypto
from app.db.repo import Database
from app.sport.client import SportClient
from app.sport.errors import AuthError

router = Router(name="auth")


@router.message(Command("login"))
async def cmd_login(message: Message, state: FSMContext) -> None:
    await state.set_state(LoginFlow.login)
    await message.answer(texts.ASK_LOGIN)


@router.message(LoginFlow.login)
async def got_login(message: Message, state: FSMContext) -> None:
    await state.update_data(login=message.text.strip())
    await state.set_state(LoginFlow.password)
    await message.answer(texts.ASK_PASSWORD)


@router.message(LoginFlow.password)
async def got_password(
    message: Message,
    state: FSMContext,
    db: Database,
    crypto: Crypto,
    client: SportClient,
) -> None:
    data = await state.get_data()
    login = data["login"]
    password = message.text.strip()

    # Remove the message that contains the plaintext password.
    try:
        await message.delete()
    except Exception:  # noqa: BLE001
        pass
    await state.clear()

    await db.upsert_user(message.from_user.id)
    await db.set_credentials(message.from_user.id, login, crypto.encrypt(password))

    user = await db.get_user(message.from_user.id)
    try:
        await client.login_and_store(user)
    except AuthError as exc:
        # wipe stored creds on failure
        await db.set_credentials(message.from_user.id, login, crypto.encrypt(""))
        await message.answer(texts.LOGIN_FAIL.format(error=str(exc)))
        return
    await message.answer(texts.LOGIN_OK)
