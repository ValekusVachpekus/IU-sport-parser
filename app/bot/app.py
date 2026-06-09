from __future__ import annotations

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.bot.middlewares import AccessMiddleware
from app.bot.routers import auth, rules, start
from app.config import Settings
from app.crypto import Crypto
from app.db.repo import Database
from app.sport.client import SportClient


def build_bot(settings: Settings) -> Bot:
    return Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def build_dispatcher(
    *,
    settings: Settings,
    db: Database,
    crypto: Crypto,
    client: SportClient,
    scheduler,
) -> Dispatcher:
    dp = Dispatcher()

    # Dependency injection: these become handler kwargs by name.
    dp["settings"] = settings
    dp["db"] = db
    dp["crypto"] = crypto
    dp["client"] = client
    dp["scheduler"] = scheduler

    access = AccessMiddleware(settings.allowed_ids)
    dp.message.middleware(access)
    dp.callback_query.middleware(access)

    dp.include_router(start.router)
    dp.include_router(auth.router)
    dp.include_router(rules.router)
    return dp
