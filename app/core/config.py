import json
from decimal import Decimal
from functools import lru_cache

from pydantic import Field, field_validator
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
    '"seedance-2.0":{"per_second":50,"by_resolution":{"480p":40,"720p":50,"1080p":60}},'
    '"seedance-2.5":{"per_second":60,"by_resolution":{"480p":50,"720p":60,"1080p":70}},'
    '"kling-2.5-turbo-pro-t2v":{"per_second":8},'
    '"kling-2.5-turbo-pro-i2v":{"per_second":8},'
    '"kling-avatar-standard":{"per_second":100},'
    '"kling-avatar-pro":{"per_second":150},'
    '"kling-3.0":{"per_second":30},'
    '"veo-3.1":{"per_second":35},'
    '"grok-video-i2v":{"per_second":15},'
    '"grok-video-1.5":{"per_second":30},'
    '"gemini-omni-video":{"per_second":30},'
    '"kling-motion-2.6":{"per_second":20,"by_mode":{"720p":20,"1080p":30}},'
    '"kling-motion-3.0":{"per_second":60,"by_mode":{"720p":60,"1080p":80}}'
    '}'
)


def _generation_pricing_with_defaults(value: object) -> str:
    """Merge deployment overrides over the canonical public ROXY tariff matrix.

    Production .env files historically carried GENERATION_PRICING_JSON={}. An
    empty object must mean "no overrides", not "discard product tariffs and fall
    back to legacy ModelSpec prices". Partial deployment overrides behave the same
    way as published admin tariffs: only named models replace code defaults.
    """

    defaults = json.loads(DEFAULT_GENERATION_PRICING_JSON)
    if value is None or (isinstance(value, str) and not value.strip()):
        overrides: object = {}
    elif isinstance(value, str):
        overrides = json.loads(value)
    else:
        overrides = value
    if not isinstance(overrides, dict):
        raise ValueError("GENERATION_PRICING_JSON must be a JSON object")
    defaults.update(overrides)
    return json.dumps(defaults, separators=(",", ":"), sort_keys=True)


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
    telegram_mini_app_short_name: str = ""
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

    @field_validator("generation_pricing_json", mode="before")
    @classmethod
    def merge_generation_pricing_defaults(cls, value: object) -> str:
        return _generation_pricing_with_defaults(value)

    music_generation_model: str = "V5_5"
    music_generation_price_rox: Decimal = Decimal("25")

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
    media_presign_ttl_seconds: int = 900
    media_legacy_reconcile_seconds: int = 60

    s3_bucket: str = ""
    s3_region: str = "us-east-1"
    s3_endpoint_url: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_session_token: str = ""
    s3_addressing_style: str = "auto"
    s3_multipart_threshold_bytes: int = 8 * 1024 * 1024
    s3_multipart_chunk_bytes: int = 8 * 1024 * 1024
    s3_max_concurrency: int = 4

    payment_reconcile_interval_seconds: int = 60
    payment_reconcile_stale_seconds: int = 30
    payment_reconcile_batch_size: int = 100

    creator_partnership_grant_interval_seconds: int = 3600

    card_api_key: str = ""
    card_api_base_url: str = "https://gate.lava.top"
    card_webhook_key: str = ""
    card_offer_id: str = ""
    card_packages_json: str = "{}"
    card_payment_route_by_currency_json: str = "{}"

    notification_worker_poll_seconds: int = 3
    notification_delivery_lease_seconds: int = 90
    notification_delivery_max_attempts: int = 8
    notification_retry_base_seconds: int = 5
    notification_retry_max_seconds: int = 900
    notification_delivery_batch_size: int = 50

    support_outbox_worker_poll_seconds: int = 3
    support_outbox_lease_seconds: int = 90
    support_outbox_max_attempts: int = 8
    support_outbox_batch_size: int = 50
    campaign_worker_poll_seconds: int = 3
    campaign_delivery_lease_seconds: int = 90
    campaign_delivery_max_attempts: int = 8
    campaign_delivery_batch_size: int = 50

    abuse_protection_enabled: bool = True
    abuse_fail_closed: bool = True
    generation_rate_limit_per_minute: int = 10
    generation_max_active_per_user: int = 6
    generation_daily_spend_limit_credits: Decimal = Decimal("0")
    generation_action_contexts_enabled: bool = True
    generation_action_context_ttl_seconds: int = 604800
    upload_rate_limit_per_minute: int = 12
    upload_daily_bytes_limit: int = 1024 * 1024 * 1024
    payment_create_rate_limit_per_minute: int = 6
    kie_submit_rate_limit_per_minute: int = 60
    kie_circuit_failure_threshold: int = 5
    kie_circuit_failure_window_seconds: int = 60
    kie_circuit_open_seconds: int = 60

    log_level: str = "INFO"
    json_logs: bool = True
    metrics_enabled: bool = True
    metrics_bearer_token: str = ""
    worker_heartbeat_ttl_seconds: int = 180
    worker_stale_after_seconds: int = 120
    otel_enabled: bool = False
    otel_service_name: str = "ksu"
    otel_exporter_otlp_traces_endpoint: str = ""
    otel_trace_sample_ratio: float = 0.10

    admin_security_key: str = ""
    admin_bootstrap_telegram_ids: str = ""
    admin_require_mfa: bool = True
    admin_session_ttl_minutes: int = 480
    admin_idle_timeout_minutes: int = 30
    admin_step_up_minutes: int = 10
    admin_login_rate_limit_per_minute: int = 5
    admin_request_rate_limit_per_minute: int = 120
    admin_login_max_failures: int = 5
    admin_login_lock_minutes: int = 15

    internal_admin_hmac_secret: str = ""
    internal_admin_network_allowlist: str = "127.0.0.1/32,::1/128"
    internal_admin_timestamp_skew_seconds: int = 300

    kie_api_key: str = ""
    kie_base_url: str = "https://api.kie.ai"
    kie_upload_base_url: str = "https://kieai.redpandaai.co"
    # Must be at least as large as the biggest per-model upload advertised in
    # ui_schema. Seedance 2.5 currently accepts reference videos up to 200 MB.
    kie_upload_max_bytes: int = 200 * 1024 * 1024
    kie_webhook_hmac_key: str = ""
    kie_credit_alert_enabled: bool = True
    kie_credit_alert_threshold: Decimal = Decimal("500")
    kie_credit_alert_poll_seconds: int = 60
    kie_credit_alert_repeat_seconds: int = 21600

    cryptopay_api_token: str = ""
    cryptopay_base_url: str = "https://pay.crypt.bot"

    payment_2328_project_uuid: str = ""
    payment_2328_api_key: str = ""
    payment_2328_base_url: str = "https://api.2328.io/api"

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
