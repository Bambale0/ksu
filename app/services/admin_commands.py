from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.admin_models import AdminCommand

SECRET_KEYS = frozenset(
    {
        "token",
        "secret",
        "password",
        "authorization",
        "api_key",
        "webhook",
        "callback",
        "access_token",
        "refresh_token",
        "cookie",
    }
)


class AdminIdempotencyConflict(RuntimeError):
    pass


class AdminCommandInProgress(RuntimeError):
    pass


class AdminCommandStoredFailure(RuntimeError):
    def __init__(self, command: AdminCommand) -> None:
        super().__init__(command.error or "Stored admin command failed")
        self.command = command


def utcnow() -> datetime:
    return datetime.now(UTC)


def redact_secrets(value: Any, *, parent_key: str | None = None) -> Any:
    if parent_key and parent_key.lower() in SECRET_KEYS:
        return "[redacted]"
    if isinstance(value, Mapping):
        return {
            str(key): redact_secrets(item, parent_key=str(key))
            for key, item in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [redact_secrets(item) for item in value]
    return value


def canonical_payload(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    safe = redact_secrets(dict(payload or {}))
    assert isinstance(safe, dict)
    return safe


def payload_hash(payload: Mapping[str, Any] | None) -> str:
    encoded = json.dumps(
        dict(payload or {}),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class AdminCommandLedger:
    @staticmethod
    def _matches(
        command: AdminCommand,
        *,
        action: str,
        target_id: str | None,
        request_hash: str,
        admin_user_id: Any,
    ) -> bool:
        return (
            command.action == action
            and command.target_id == target_id
            and command.request_hash == request_hash
            and str(command.admin_user_id) == str(admin_user_id)
        )

    @classmethod
    async def reserve(
        cls,
        session: AsyncSession,
        *,
        idempotency_key: str,
        admin_user_id: Any,
        request_id: str,
        action: str,
        target_id: str | None,
        request_payload: Mapping[str, Any] | None,
    ) -> tuple[AdminCommand, bool]:
        key = idempotency_key.strip()
        if not key:
            raise ValueError("Idempotency key is required")
        digest = payload_hash(request_payload)

        existing = await session.scalar(
            select(AdminCommand).where(AdminCommand.idempotency_key == key)
        )
        if existing is not None:
            if not cls._matches(
                existing,
                action=action,
                target_id=target_id,
                request_hash=digest,
                admin_user_id=admin_user_id,
            ):
                raise AdminIdempotencyConflict(
                    "Idempotency key was already used for a different admin command"
                )
            return existing, True

        command = AdminCommand(
            idempotency_key=key,
            admin_user_id=admin_user_id,
            request_id=request_id,
            action=action,
            target_id=target_id,
            request_hash=digest,
            request_payload=canonical_payload(request_payload),
            status="reserved",
        )
        try:
            async with session.begin_nested():
                session.add(command)
                await session.flush()
            return command, False
        except IntegrityError:
            existing = await session.scalar(
                select(AdminCommand).where(AdminCommand.idempotency_key == key)
            )
            if existing is None:
                raise
            if not cls._matches(
                existing,
                action=action,
                target_id=target_id,
                request_hash=digest,
                admin_user_id=admin_user_id,
            ):
                raise AdminIdempotencyConflict(
                    "Idempotency key was concurrently used for a different admin command"
                )
            return existing, True

    @staticmethod
    def replay(command: AdminCommand) -> dict[str, Any]:
        if command.status == "completed":
            return dict(command.response_payload or {})
        if command.status == "failed":
            raise AdminCommandStoredFailure(command)
        raise AdminCommandInProgress("Admin command with this idempotency key is in progress")

    @staticmethod
    async def complete(
        session: AsyncSession,
        command: AdminCommand,
        response_payload: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        response = canonical_payload(response_payload)
        command.response_payload = response
        command.status = "completed"
        command.error = None
        command.completed_at = utcnow()
        await session.flush()
        return response

    @staticmethod
    async def fail(
        session: AsyncSession,
        command: AdminCommand,
        exc: BaseException,
    ) -> None:
        command.status = "failed"
        command.error = str(exc)[:4000]
        command.completed_at = utcnow()
        await session.flush()

    @classmethod
    async def execute(
        cls,
        session: AsyncSession,
        *,
        idempotency_key: str,
        admin_user_id: Any,
        request_id: str,
        action: str,
        target_id: str | None,
        request_payload: Mapping[str, Any] | None,
        operation: Callable[[], Awaitable[Mapping[str, Any]]],
    ) -> tuple[dict[str, Any], bool]:
        command, replayed = await cls.reserve(
            session,
            idempotency_key=idempotency_key,
            admin_user_id=admin_user_id,
            request_id=request_id,
            action=action,
            target_id=target_id,
            request_payload=request_payload,
        )
        if replayed:
            return cls.replay(command), True
        try:
            result = await operation()
            response = await cls.complete(session, command, result)
            return response, False
        except BaseException as exc:
            await cls.fail(session, command, exc)
            raise
