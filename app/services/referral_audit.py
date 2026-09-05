from __future__ import annotations

import logging
import uuid

logger = logging.getLogger("ksu.referrals")


def log_referral_admission(
    *,
    visitor_telegram_id: int,
    inviter_telegram_id: int | None,
    attached: bool,
    reason: str,
    inviter_user_id: uuid.UUID | None = None,
) -> None:
    """Emit referral attribution diagnostics without Telegram initData or raw payloads."""

    logger.info(
        "referral_admission visitor_telegram_id=%s inviter_telegram_id=%s attached=%s reason=%s",
        visitor_telegram_id,
        inviter_telegram_id,
        attached,
        reason,
        extra={
            "referral_event": "admission",
            "visitor_telegram_id": visitor_telegram_id,
            "inviter_telegram_id": inviter_telegram_id,
            "referral_attached": attached,
            "referral_reason": reason,
            "inviter_user_id": str(inviter_user_id) if inviter_user_id is not None else None,
        },
    )


def log_signed_referral_validation(
    *,
    visitor_telegram_id: int,
    inviter_telegram_id: int,
    action: str,
    accepted: bool,
    reason: str,
) -> None:
    """Audit signed startapp referral validation without logging the signed Telegram data."""

    log = logger.info if accepted else logger.warning
    log(
        "referral_startapp visitor_telegram_id=%s inviter_telegram_id=%s action=%s accepted=%s reason=%s",
        visitor_telegram_id,
        inviter_telegram_id,
        action,
        accepted,
        reason,
        extra={
            "referral_event": "startapp_validation",
            "visitor_telegram_id": visitor_telegram_id,
            "inviter_telegram_id": inviter_telegram_id,
            "referral_action": action,
            "referral_accepted": accepted,
            "referral_reason": reason,
        },
    )
