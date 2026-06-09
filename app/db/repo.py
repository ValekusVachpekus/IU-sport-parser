from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.models import Base, Rule, RuleMode, User


class Database:
    def __init__(self, url: str) -> None:
        self._engine = create_async_engine(url, future=True)
        self._sessionmaker = async_sessionmaker(self._engine, expire_on_commit=False)

    async def init(self) -> None:
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self._sessionmaker() as session:
            yield session

    # --- Users ---
    async def get_user(self, tg_id: int) -> User | None:
        async with self.session() as s:
            return await s.get(User, tg_id)

    async def upsert_user(self, tg_id: int) -> User:
        async with self.session() as s:
            user = await s.get(User, tg_id)
            if user is None:
                user = User(tg_id=tg_id)
                s.add(user)
                await s.commit()
                await s.refresh(user)
            return user

    async def set_credentials(self, tg_id: int, login: str, password_enc: str) -> None:
        async with self.session() as s:
            user = await s.get(User, tg_id) or User(tg_id=tg_id)
            user.sport_login = login
            user.password_enc = password_enc
            await s.merge(user)
            await s.commit()

    async def set_tokens(
        self,
        tg_id: int,
        access_enc: str | None,
        refresh_enc: str | None,
        expires_at: datetime | None,
    ) -> None:
        async with self.session() as s:
            user = await s.get(User, tg_id)
            if user is None:
                return
            user.access_token_enc = access_enc
            user.refresh_token_enc = refresh_enc
            user.token_expires_at = expires_at
            await s.commit()

    async def all_users(self) -> list[User]:
        async with self.session() as s:
            return list((await s.scalars(select(User))).all())

    # --- Rules ---
    async def add_rule(
        self,
        tg_id: int,
        group_id: int,
        weekday: int,
        start_time: time,
        title: str,
        mode: RuleMode,
    ) -> Rule:
        async with self.session() as s:
            rule = Rule(
                user_tg_id=tg_id,
                group_id=group_id,
                weekday=weekday,
                start_time=start_time,
                title=title,
                mode=mode,
            )
            s.add(rule)
            await s.commit()
            await s.refresh(rule)
            return rule

    async def list_rules(self, tg_id: int) -> list[Rule]:
        async with self.session() as s:
            return list(
                (await s.scalars(select(Rule).where(Rule.user_tg_id == tg_id))).all()
            )

    async def active_rules(self) -> list[Rule]:
        async with self.session() as s:
            return list((await s.scalars(select(Rule).where(Rule.active.is_(True)))).all())

    async def get_rule(self, rule_id: int) -> Rule | None:
        async with self.session() as s:
            return await s.get(Rule, rule_id)

    async def delete_rule(self, rule_id: int, tg_id: int) -> bool:
        async with self.session() as s:
            rule = await s.get(Rule, rule_id)
            if rule is None or rule.user_tg_id != tg_id:
                return False
            await s.delete(rule)
            await s.commit()
            return True

    async def set_rule_active(self, rule_id: int, tg_id: int, active: bool) -> bool:
        async with self.session() as s:
            rule = await s.get(Rule, rule_id)
            if rule is None or rule.user_tg_id != tg_id:
                return False
            rule.active = active
            await s.commit()
            return True

    async def set_rule_result(self, rule_id: int, result: str) -> None:
        async with self.session() as s:
            rule = await s.get(Rule, rule_id)
            if rule is not None:
                rule.last_result = result
                await s.commit()
