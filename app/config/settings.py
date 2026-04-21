"""Application settings loaded from environment.

Single source of truth for runtime configuration. See .env.example.
"""
from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Telegram ---
    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    telegram_admin_chat_ids: str = Field(default="", alias="TELEGRAM_ADMIN_CHAT_IDS")

    # --- TrueData ---
    truedata_user: str = Field(default="", alias="TRUEDATA_USER")
    truedata_password: str = Field(default="", alias="TRUEDATA_PASSWORD")
    truedata_ws_url: str = Field(default="push.truedata.in", alias="TRUEDATA_WS_URL")
    truedata_ws_port: int = Field(default=8084, alias="TRUEDATA_WS_PORT")   # 8086=sandbox, 8084=prod
    truedata_historical_url: str = Field(default="https://history.truedata.in", alias="TRUEDATA_HISTORICAL_URL")
    truedata_api_url: str = Field(default="https://api.truedata.in", alias="TRUEDATA_API_URL")

    # --- Marketaux ---
    marketaux_key: str = Field(default="", alias="MARKETAUX_KEY")
    marketaux_url: str = Field(default="https://api.marketaux.com/v1", alias="MARKETAUX_URL")

    # --- LLM providers (first key that is non-empty wins) ---
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    anthropic_model: str = Field(default="claude-sonnet-4-6", alias="ANTHROPIC_MODEL")
    groq_api_key: str = Field(default="", alias="GROQ_API_KEY")
    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")

    # --- DB / Cache ---
    postgres_dsn: str = Field(
        default="postgresql+psycopg2://copilot:copilot@localhost:5432/copilot",
        alias="POSTGRES_DSN",
    )
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")

    # --- App ---
    app_env: str = Field(default="development", alias="APP_ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    tz: str = Field(default="Asia/Kolkata", alias="TZ")

    # --- Risk defaults ---
    default_capital: float = Field(default=500_000, alias="DEFAULT_CAPITAL")
    default_risk_pct: float = Field(default=1.0, alias="DEFAULT_RISK_PCT")
    daily_loss_limit_pct: float = Field(default=3.0, alias="DAILY_LOSS_LIMIT_PCT")

    @property
    def admin_chat_ids(self) -> List[int]:
        v = self.telegram_admin_chat_ids
        if not v:
            return []
        return [int(x.strip()) for x in v.split(",") if x.strip()]


@lru_cache(maxsize=1)
def _load() -> Settings:
    return Settings()


settings: Settings = _load()
