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
    bot_username: str = ""
    telegram_webhook_url: str = ""
    telegram_webhook_secret: str = Field(default="", min_length=0, max_length=256)

    # Versioned product onboarding. Copy/links are deployment-owned rather than legal text in code.
    onboarding_enabled: bool = True
    onboarding_version: str = "1"
    onboarding_title: str = "Добро пожаловать в Ксю"
    onboarding_body: str = "Перед началом работы завершите короткий вводный экран."
    onboarding_rules_url: str = ""
    onboarding_privacy_url: str = ""

    start_balance_rox: Decimal = Decimal("0")
    internal_credit_rub: Decimal = Decimal("10")
    referral_first_percent: Decimal = Decimal("30")
    referral_second_percent: Decimal = Decimal("5")
    # Product spec defines a minimum withdrawal but does not fix the business value.
    # Zero means no separate minimum beyond amount > 0.
    partner_min_withdrawal_rub: Decimal = Decimal("0")
    rox_packages_json: str = "{}"
    generation_pricing_json: str = "{}"

    # Generation reliability. PostgreSQL outbox is authoritative; Redis only wakes workers.
    generation_worker_poll_seconds: int = 5
    generation_outbox_lease_seconds: int = 90
    generation_submission_max_attempts: int = 5
    generation_submission_unknown_timeout_seconds: int = 900
    generation_reconcile_interval_seconds: int = 60
    generation_reconcile_stale_seconds: int = 60
    generation_recovery_batch_size: int = 50

    # Durable provider-result ingestion into private S3-compatible object storage.
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

    # Payment lifecycle reconciliation.
    payment_reconcile_interval_seconds: int = 60
    payment_reconcile_stale_seconds: int = 30
    payment_reconcile_batch_size: int = 100

    # Durable transactional Telegram notifications.
    notification_worker_poll_seconds: int = 3
    notification_delivery_lease_seconds: int = 90
    notification_delivery_max_attempts: int = 8
    notification_retry_base_seconds: int = 5
    notification_retry_max_seconds: int = 900
    notification_delivery_batch_size: int = 50

    # OWASP API4 / resource-consumption controls. Zero disables an optional quota.
    abuse_protection_enabled: bool = True
    abuse_fail_closed: bool = True
    generation_rate_limit_per_minute: int = 10
    generation_max_active_per_user: int = 3
    generation_daily_spend_limit_credits: Decimal = Decimal("0")
    upload_rate_limit_per_minute: int = 12
    upload_daily_bytes_limit: int = 1024 * 1024 * 1024
    payment_create_rate_limit_per_minute: int = 6
    kie_submit_rate_limit_per_minute: int = 60
    kie_circuit_failure_threshold: int = 5
    kie_circuit_failure_window_seconds: int = 60
    kie_circuit_open_seconds: int = 60

    # Production observability.
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

    # Separate privileged-admin security domain.
    # ADMIN_SECURITY_KEY must be a random 32+ character secret in deployments using admin routes.
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

    kie_api_key: str = ""
    kie_base_url: str = "https://api.kie.ai"
    kie_upload_base_url: str = "https://kieai.redpandaai.co"
    kie_upload_max_bytes: int = 100 * 1024 * 1024
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
