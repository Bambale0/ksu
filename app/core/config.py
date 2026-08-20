from decimal import Decimal
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


DEFAULT_GENERATION_PRICING_JSON = (
    '{'
    '"nano-banana-pro":{"flat":25},'
    '"wan-2.7-image-pro":{"flat":20},'
    '"gpt-image-2-t2i":{"flat":20},'
    '"gpt-image-2-i2i":{"flat":20},'
    '"nano-banana-2":{"flat":25},'
    '"nano-banana-2-lite":{"flat":25},'
    '"seedream-4.5-edit":{"flat":20},'
    '"seedream-5-pro-t2i":{"flat":20},'
    '"seedream-5-pro-i2i":{"flat":20},'
    '"seedance-2.0":{"per_second":40},'
    '"seedance-2.5":{"per_second":60},'
    '"kling-3.0":{"per_second":30},'
    '"veo-3.1":{"per_second":35},'
    '"grok-video-i2v":{"per_second":15},'
    '"grok-video-1.5":{"per_second":30},'
    '"gemini-omni-video":{"per_second":30},'
    '"kling-motion-2.6":{"per_second":20,"by_mode":{"720p":20,"1080p":30}},'
    '"kling-motion-3.0":{"per_second":60,"by_mode":{"720p":60,"1080p":80}}'
    '}'
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    public_base_url: str = ""

    database_url: str = "postgresql+asyncpg://ksu:ksu@localhost:5432/ksu"
    redis_url: str = "redis://localhost:6379/0"

    bot_token: str = ""
    bot_username: str = ""
    support_telegram_url: str = ""
    partner_telegram_url: str = ""
    telegram_webhook_url: str = ""
    telegram_webhook_secret: str = Field(default="", min_length=0, max_length=256)

    onboarding_enabled: bool = True
    onboarding_version: str = "1"
    onboarding_title: str = "Добро пожаловать в ROXY"
    onboarding_body: str = "Перед началом работы завершите короткий вводный экран."
    onboarding_rules_url: str = ""
    onboarding_privacy_url: str = ""

    # ROXY economy: 1 ROX = 1 RUB. Wallet ROX are spendable in ROXY; partner
    # referral earnings stay in RUB until the user withdraws them or converts them to ROX.
    start_balance_rox: Decimal = Decimal("50")
    invite_bonus_rox: Decimal = Decimal("30")
    prompt_repeat_bonus_rox: Decimal = Decimal("5")
    internal_credit_rub: Decimal = Decimal("1")
    referral_first_percent: Decimal = Decimal("30")
    referral_second_percent: Decimal = Decimal("5")
    partner_min_withdrawal_rub: Decimal = Decimal("3000")
    referral_antifraud_max_per_hour: int = 30
    referral_antifraud_max_per_day: int = 120
    referral_antifraud_burst_window_seconds: int = 10
    referral_antifraud_burst_max: int = 6
    referral_antifraud_burst_autoban: bool = True
    rox_packages_json: str = "{}"
    generation_pricing_json: str = DEFAULT_GENERATION_PRICING_JSON

    # Music is a distinct Kie/Suno provider contract but uses the same ROXY wallet,
    # generation history and durable worker/recovery infrastructure.
    music_generation_model: str = "V5_5"
    music_generation_price_rox: Decimal = Decimal("100")

    generation_worker_poll_seconds: int = 5
    generation_outbox_lease_seconds: int = 90
    generation_submission_max_attempts: int = 5
    generation_submission_unknown_timeout_seconds: int = 900
    generation_hard_timeout_seconds: int = 7200
    generation_reconcile_interval_seconds: int = 60
    generation_reconcile_stale_seconds: int = 60
    generation_recovery_batch_size: int = 50

    media_worker_poll_seconds: int = 5
    media_ingest_lease_seconds: int = 600
    media_ingest_max_attempts: int = 5
    media_ingest_max_bytes: int = 1024 * 1024 * 1024
    media_ingest_connect_timeout_seconds: float = 10.0
    media_ingest_read_timeout_seconds: float = 180.0
    media_ingest_max_redirects: int = 5

    media_storage_endpoint_url: str = ""
    media_storage_region: str = "us-east-1"
    media_storage_bucket: str = ""
    media_storage_access_key_id: str = ""
    media_storage_secret_access_key: str = ""
    media_storage_force_path_style: bool = False
    media_storage_signed_url_ttl_seconds: int = 900

    kie_api_key: str = ""
    kie_base_url: str = "https://api.kie.ai"
    kie_upload_base_url: str = "https://kieai.redpandaai.co"
    kie_timeout_seconds: float = 120.0
    kie_callback_url: str = ""
    kie_webhook_hmac_key: str = ""
    kie_webhook_max_age_seconds: int = 300
    kie_provider_rate_limit_per_second: int = 10
    kie_provider_rate_limit_burst: int = 20
    kie_circuit_breaker_failure_threshold: int = 5
    kie_circuit_breaker_reset_seconds: int = 30

    generation_rate_limit_per_minute: int = 15
    generation_concurrency_limit: int = 3
    abuse_protection_enabled: bool = True

    # Remaining settings continue below unchanged in the repository.
