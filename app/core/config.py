from decimal import Decimal
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    database_url: str = "postgresql+asyncpg://ksu:ksu@localhost:5432/ksu"
    redis_url: str = "redis://localhost:6379/0"

    bot_token: str = ""
    telegram_webhook_url: str = ""
    telegram_webhook_secret: str = Field(default="", min_length=0, max_length=256)

    start_balance_rox: Decimal = Decimal("0")
    referral_first_percent: Decimal = Decimal("30")
    referral_second_percent: Decimal = Decimal("5")

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
