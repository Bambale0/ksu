from decimal import Decimal
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    public_base_url: str = ""

    database_url: str = "postgresql+asyncpg://ksu:ksu@localhost:5432/ksu"
    redis_url: str = "redis://localhost:6379/0"

    bot_token: str = ""
    telegram_webhook_url: str = ""
    telegram_webhook_secret: str = Field(default="", min_length=0, max_length=256)

    start_balance_rox: Decimal = Decimal("0")
    internal_credit_rub: Decimal = Decimal("10")
    referral_first_percent: Decimal = Decimal("30")
    referral_second_percent: Decimal = Decimal("5")
    rox_packages_json: str = "{}"
    generation_pricing_json: str = "{}"

    kie_api_key: str = ""
    kie_base_url: str = "https://api.kie.ai"
    kie_webhook_hmac_key: str = ""

    cryptopay_api_token: str = ""
    cryptopay_base_url: str = "https://pay.crypt.bot"

    tbank_terminal_key: str = ""
    tbank_password: str = ""
    tbank_base_url: str = "https://securepay.tinkoff.ru"

    yookassa_shop_id: str = ""
    yookassa_secret_key: str = ""
    yookassa_base_url: str = "https://api.yookassa.ru"

    payment_return_url: str = ""

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    def webhook_url(self, path: str) -> str:
        if not self.public_base_url:
            return ""
        return f"{self.public_base_url.rstrip('/')}/{path.lstrip('/')}"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
