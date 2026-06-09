from __future__ import annotations

import asyncio
import logging

from app.bot.app import build_bot, build_dispatcher
from app.config import get_settings
from app.crypto import Crypto
from app.db.repo import Database
from app.scheduler.service import SchedulerService
from app.sport.auth import SsoAuth
from app.sport.client import SportClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("sportparser")


async def main() -> None:
    settings = get_settings()

    db = Database(settings.db_url)
    await db.init()

    crypto = Crypto(settings.fernet_key)
    sso = SsoAuth(
        sso_base=settings.sso_base,
        client_id=settings.oauth_client_id,
        redirect_uri=settings.oauth_redirect_uri,
    )
    client = SportClient(api_base=settings.sport_api_base, db=db, crypto=crypto, sso=sso)

    bot = build_bot(settings)

    async def notify(tg_id: int, text: str) -> None:
        try:
            await bot.send_message(tg_id, text)
        except Exception as exc:  # noqa: BLE001
            log.warning("notify %s failed: %s", tg_id, exc)

    scheduler = SchedulerService(settings=settings, db=db, client=client, notify=notify)
    scheduler.start()

    dp = build_dispatcher(
        settings=settings, db=db, crypto=crypto, client=client, scheduler=scheduler
    )

    from aiogram.types import BotCommand

    await bot.set_my_commands(
        [
            BotCommand(command="add", description="Добавить занятие для автозаписи"),
            BotCommand(command="rules", description="Мои правила"),
            BotCommand(command="login", description="Войти в аккаунт Innopolis"),
            BotCommand(command="help", description="Справка"),
            BotCommand(command="cancel", description="Отменить текущий шаг"),
        ]
    )

    log.info("starting bot polling")
    try:
        await dp.start_polling(bot)
    finally:
        await client.aclose()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
