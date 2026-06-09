from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Telegram
    bot_token: str = Field(alias="BOT_TOKEN")
    allowed_tg_ids: str = Field(default="", alias="ALLOWED_TG_IDS")

    # Security / storage
    fernet_key: str = Field(alias="FERNET_KEY")
    db_url: str = Field(default="sqlite+aiosqlite:///data/sportparser.db", alias="DB_URL")
    tz: str = Field(default="Europe/Moscow", alias="TZ")

    # Sport API / SSO
    sport_api_base: str = Field(
        default="https://sport.innopolis.university/api", alias="SPORT_API_BASE"
    )
    sso_base: str = Field(default="https://sso.university.innopolis.ru/adfs", alias="SSO_BASE")
    oauth_client_id: str = Field(
        default="7d0eb0b9-ad73-4942-be55-284facc99a95", alias="OAUTH_CLIENT_ID"
    )
    oauth_redirect_uri: str = Field(
        default="https://sport.innopolis.university/oauth2/callback", alias="OAUTH_REDIRECT_URI"
    )

    # Behaviour
    burst_lead_seconds: float = Field(default=2.0, alias="BURST_LEAD_SECONDS")
    burst_interval_ms: int = Field(default=400, alias="BURST_INTERVAL_MS")
    burst_max_seconds: float = Field(default=8.0, alias="BURST_MAX_SECONDS")
    watch_interval_seconds: int = Field(default=45, alias="WATCH_INTERVAL_SECONDS")
    watch_jitter_seconds: int = Field(default=15, alias="WATCH_JITTER_SECONDS")
    planner_interval_minutes: int = Field(default=180, alias="PLANNER_INTERVAL_MINUTES")

    @property
    def allowed_ids(self) -> set[int]:
        return {int(x) for x in self.allowed_tg_ids.replace(" ", "").split(",") if x}


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
