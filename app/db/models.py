from __future__ import annotations

import enum
from datetime import datetime, time, timezone

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, ForeignKey, Integer, String, Time
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class RuleMode(str, enum.Enum):
    scheduled = "scheduled"  # check in the instant sign-up opens (start - 7d)
    watch = "watch"          # check in as soon as a spot frees up
    both = "both"            # scheduled, then fall back to watching


class User(Base):
    __tablename__ = "users"

    tg_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    sport_login: Mapped[str | None] = mapped_column(String, nullable=True)
    # Fernet-encrypted secrets
    password_enc: Mapped[str | None] = mapped_column(String, nullable=True)
    access_token_enc: Mapped[str | None] = mapped_column(String, nullable=True)
    refresh_token_enc: Mapped[str | None] = mapped_column(String, nullable=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    rules: Mapped[list["Rule"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Rule(Base):
    """A recurring weekly training slot the user wants to be auto-checked-in to."""

    __tablename__ = "rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_tg_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.tg_id", ondelete="CASCADE"), index=True
    )

    group_id: Mapped[int] = mapped_column(Integer)
    weekday: Mapped[int] = mapped_column(Integer)          # 0=Mon .. 6=Sun (Python weekday)
    start_time: Mapped[time] = mapped_column(Time)         # local site time
    title: Mapped[str] = mapped_column(String, default="")

    mode: Mapped[RuleMode] = mapped_column(Enum(RuleMode), default=RuleMode.both)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_result: Mapped[str | None] = mapped_column(String, nullable=True)

    user: Mapped[User] = relationship(back_populates="rules")
