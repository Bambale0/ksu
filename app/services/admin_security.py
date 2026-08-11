from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import struct
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote

from aiogram.types import User as TelegramUser
from aiogram.utils.web_app import safe_parse_webapp_init_data
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException, Request, status
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import AdminAccount, AdminAuditLog, AdminSession
from app.services.users import UserService


class AdminSecurityConfigurationError(RuntimeError):
    pass


ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "owner": frozenset({"*"}),
    "admin": frozenset(
        {
            "dashboard.read",
            "users.read",
            "users.pii",
            "users.manage",
            "users.wallet.adjust",
            "users.notes",
            "generations.read",
            "generations.manage",
            "payments.read",
            "promocodes.read",
            "promocodes.manage",
            "support.read",
            "support.manage",
            "withdrawals.read",
            "withdrawals.manage",
            "referrals.read",
            "audit.read",
            "admins.read",
            "security.read",
            "sessions.manage",
        }
    ),
    "support": frozenset(
        {
            "dashboard.read",
            "users.read",
            "users.notes",
            "generations.read",
            "payments.read",
            "support.read",
            "support.manage",
        }
    ),
    "finance": frozenset(
        {
            "dashboard.read",
            "users.read",
            "users.pii",
            "users.wallet.adjust",
            "payments.read",
            "withdrawals.read",
            "withdrawals.manage",
            "referrals.read",
            "audit.read",
        }
    ),
    "moderator": frozenset(
        {
            "dashboard.read",
            "users.read",
            "users.manage",
            "users.notes",
            "generations.read",
            "generations.manage",
            "support.read",
        }
    ),
    "auditor": frozenset(
        {
            "dashboard.read",
            "users.read",
            "generations.read",
            "payments.read",
            "promocodes.read",
            "support.read",
            "withdrawals.read",
            "referrals.read",
            "audit.read",
            "admins.read",
            "security.read",
        }
    ),
}

VALID_ADMIN_ROLES = frozenset(ROLE_PERMISSIONS)
SENSITIVE_AUDIT_KEYS = frozenset(
    {
        "authorization",
        "cookie",
        "password",
        "secret",
        "token",
        "access_token",
        "refresh_token",
        "session_token",
        "x_telegram_init_data",
        "telegram_init_data",
        "init_data",
        "mfa_secret",
        "recovery_code",
        "recovery_codes",
        "requisites",
        "provider_response",
    }
)


def utcnow() -> datetime:
    return datetime.now(UTC)


def _security_key() -> bytes:
    value = settings.admin_security_key.strip()
    if len(value) < 32:
        raise AdminSecurityConfigurationError(
            "ADMIN_SECURITY_KEY must contain at least 32 characters"
        )
    return value.encode()


def hash_admin_token(token: str) -> str:
    return hmac.new(_security_key(), token.encode(), hashlib.sha256).hexdigest()


def fingerprint(value: str | None) -> str | None:
    if not value:
        return None
    return hmac.new(_security_key(), value.encode(), hashlib.sha256).hexdigest()


def _fernet() -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(_security_key()).digest())
    return Fernet(key)


def encrypt_mfa_secret(secret: str) -> str:
    return _fernet().encrypt(secret.encode()).decode()


def decrypt_mfa_secret(encrypted: str) -> str:
    try:
        return _fernet().decrypt(encrypted.encode()).decode()
    except InvalidToken as exc:
        raise AdminSecurityConfigurationError("Unable to decrypt admin MFA secret") from exc


def generate_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _decode_base32(secret: str) -> bytes:
    padding = "=" * ((8 - len(secret) % 8) % 8)
    return base64.b32decode(secret.upper() + padding, casefold=True)


def totp_code(secret: str, *, timestamp: int | None = None, step: int = 30) -> str:
    current = int(time.time()) if timestamp is None else timestamp
    counter = current // step
    digest = hmac.new(
        _decode_base32(secret),
        struct.pack(">Q", counter),
        hashlib.sha1,
    ).digest()
    offset = digest[-1] & 0x0F
    binary = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return f"{binary % 1_000_000:06d}"


def verify_totp(secret: str, code: str, *, timestamp: int | None = None) -> bool:
    if len(code) != 6 or not code.isdigit():
        return False
    current = int(time.time()) if timestamp is None else timestamp
    return any(
        hmac.compare_digest(totp_code(secret, timestamp=current + offset * 30), code)
        for offset in (-1, 0, 1)
    )


def provisioning_uri(secret: str, *, telegram_id: int) -> str:
    issuer = "KSU Admin"
    label = f"KSU Admin:{telegram_id}"
    return (
        f"otpauth://totp/{quote(label)}?secret={secret}"
        f"&issuer={quote(issuer)}&algorithm=SHA1&digits=6&period=30"
    )


def generate_recovery_codes(count: int = 8) -> list[str]:
    return [f"{secrets.token_hex(4)}-{secrets.token_hex(4)}" for _ in range(count)]


def hash_recovery_code(code: str) -> str:
    normalized = code.strip().lower()
    return hmac.new(_security_key(), normalized.encode(), hashlib.sha256).hexdigest()


def consume_recovery_code(admin: AdminAccount, code: str) -> bool:
    candidate = hash_recovery_code(code)
    hashes = list(admin.recovery_code_hashes or [])
    for index, stored in enumerate(hashes):
        if hmac.compare_digest(stored, candidate):
            hashes.pop(index)
            admin.recovery_code_hashes = hashes
            return True
    return False


def has_permission(admin: AdminAccount, permission: str) -> bool:
    base = ROLE_PERMISSIONS.get(admin.role, frozenset())
    overrides = admin.permission_overrides or {}
    deny = {str(item) for item in overrides.get("deny", [])}
    allow = {str(item) for item in overrides.get("allow", [])}
    if permission in deny or "*" in deny:
        return False
    if "*" in base or permission in base:
        return True
    return permission in allow or "*" in allow


def effective_permissions(admin: AdminAccount) -> list[str]:
    base = ROLE_PERMISSIONS.get(admin.role, frozenset())
    overrides = admin.permission_overrides or {}
    deny = {str(item) for item in overrides.get("deny", [])}
    allow = {str(item) for item in overrides.get("allow", [])}
    if "*" in base:
        return ["*"]
    return sorted((set(base) | allow) - deny)


def parse_bootstrap_ids() -> set[int]:
    result: set[int] = set()
    for raw in settings.admin_bootstrap_telegram_ids.split(","):
        raw = raw.strip()
        if not raw:
            continue
        try:
            result.add(int(raw))
        except ValueError:
            continue
    return result


def sanitize_audit_metadata(value: Any, *, depth: int = 0) -> Any:
    if depth > 5:
        return "[truncated]"
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for raw_key, raw_value in list(value.items())[:50]:
            key = str(raw_key)
            lowered = key.lower()
            if lowered in SENSITIVE_AUDIT_KEYS or any(
                marker in lowered for marker in ("password", "secret", "token", "cookie")
            ):
                clean[key] = "[redacted]"
            else:
                clean[key] = sanitize_audit_metadata(raw_value, depth=depth + 1)
        return clean
    if isinstance(value, (list, tuple, set)):
        return [sanitize_audit_metadata(item, depth=depth + 1) for item in list(value)[:20]]
    if isinstance(value, str):
        return value[:1000]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:1000]


def audit_integrity_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hmac.new(_security_key(), canonical.encode(), hashlib.sha256).hexdigest()


class AdminAuditService:
    @classmethod
    async def record(
        cls,
        session: AsyncSession,
        *,
        action: str,
        outcome: str,
        admin: AdminAccount | None = None,
        admin_session: AdminSession | None = None,
        request: Request | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        reason: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AdminAuditLog:
        request_id = None
        ip_hash = None
        user_agent_hash = None
        if request is not None:
            request_id = getattr(request.state, "request_id", None)
            ip_hash = fingerprint(request.client.host if request.client else None)
            user_agent_hash = fingerprint(request.headers.get("user-agent"))

        clean_metadata = sanitize_audit_metadata(metadata or {})
        integrity_payload = {
            "admin_id": str(admin.id) if admin else None,
            "session_id": str(admin_session.id) if admin_session else None,
            "action": action,
            "outcome": outcome,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "reason": reason,
            "request_id": request_id,
            "ip_hash": ip_hash,
            "user_agent_hash": user_agent_hash,
            "metadata": clean_metadata,
        }
        log = AdminAuditLog(
            admin_id=admin.id if admin else None,
            session_id=admin_session.id if admin_session else None,
            action=action[:128],
            outcome=outcome[:24],
            resource_type=(resource_type or "")[:64] or None,
            resource_id=(resource_id or "")[:128] or None,
            reason=(reason or "")[:1000] or None,
            request_id=(request_id or "")[:64] or None,
            ip_hash=ip_hash,
            user_agent_hash=user_agent_hash,
            metadata_json=clean_metadata,
            integrity_hash=audit_integrity_hash(integrity_payload),
        )
        session.add(log)
        await session.flush()
        return log


class AdminAuthService:
    @staticmethod
    def parse_telegram_init_data(raw: str) -> TelegramUser:
        if not settings.bot_token:
            raise HTTPException(status_code=503, detail="Bot is not configured")
        try:
            init_data = safe_parse_webapp_init_data(settings.bot_token, raw)
        except ValueError as exc:
            raise HTTPException(status_code=401, detail="Invalid Telegram initData") from exc
        if init_data.user is None:
            raise HTTPException(status_code=401, detail="Telegram user missing")
        user = init_data.user
        return TelegramUser(
            id=user.id,
            is_bot=False,
            first_name=user.first_name,
            last_name=user.last_name,
            username=user.username,
            language_code=user.language_code,
        )

    @classmethod
    async def get_or_bootstrap_admin(
        cls,
        session: AsyncSession,
        telegram_user: TelegramUser,
    ) -> AdminAccount | None:
        user = await UserService.get_or_create(session, telegram_user)
        admin = await session.scalar(select(AdminAccount).where(AdminAccount.user_id == user.id))
        if admin is None and telegram_user.id in parse_bootstrap_ids():
            admin = AdminAccount(user_id=user.id, role="owner", is_active=True)
            session.add(admin)
            await session.flush()
        return admin

    @staticmethod
    async def enforce_rate_limit(
        redis: Redis,
        *,
        key: str,
        limit: int,
        window_seconds: int = 60,
    ) -> None:
        if limit <= 0:
            return
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, window_seconds)
        if count > limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests",
                headers={"Retry-After": str(window_seconds)},
            )

    @staticmethod
    async def create_session(
        session: AsyncSession,
        *,
        admin: AdminAccount,
        request: Request,
        mfa_verified: bool,
    ) -> tuple[AdminSession, str]:
        now = utcnow()
        raw_token = secrets.token_urlsafe(48)
        record = AdminSession(
            admin_id=admin.id,
            token_hash=hash_admin_token(raw_token),
            created_at=now,
            last_seen_at=now,
            expires_at=now + timedelta(minutes=settings.admin_session_ttl_minutes),
            idle_expires_at=now + timedelta(minutes=settings.admin_idle_timeout_minutes),
            mfa_verified=mfa_verified,
            session_version=admin.session_version,
            ip_hash=fingerprint(request.client.host if request.client else None),
            user_agent_hash=fingerprint(request.headers.get("user-agent")),
        )
        session.add(record)
        await session.flush()
        return record, raw_token

    @staticmethod
    def session_is_valid(record: AdminSession, admin: AdminAccount) -> bool:
        now = utcnow()
        if record.revoked_at is not None:
            return False
        if not admin.is_active:
            return False
        if record.session_version != admin.session_version:
            return False
        return record.expires_at > now and record.idle_expires_at > now

    @staticmethod
    def step_up_valid(record: AdminSession) -> bool:
        return record.step_up_until is not None and record.step_up_until > utcnow()

    @staticmethod
    def verify_second_factor(
        admin: AdminAccount,
        *,
        otp: str | None,
        recovery_code: str | None,
    ) -> bool:
        if not admin.mfa_enabled or not admin.mfa_secret_encrypted:
            return False
        if otp:
            secret = decrypt_mfa_secret(admin.mfa_secret_encrypted)
            return verify_totp(secret, otp)
        if recovery_code:
            return consume_recovery_code(admin, recovery_code)
        return False
