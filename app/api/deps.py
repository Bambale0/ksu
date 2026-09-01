from typing import Annotated

from aiogram.types import User as TelegramUser
from aiogram.utils.web_app import safe_parse_webapp_init_data
from fastapi import Depends, Header, HTTPException, Request, status
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.telegram_security import validate_webapp_auth_date
from app.db.models import User
from app.db.session import get_session
from app.services.feed import FeedNotFoundError, FeedService
from app.services.feed_links import parse_feed_deep_link
from app.services.onboarding import OnboardingService
from app.services.trends import TrendService
from app.services.users import UserService

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_redis(request: Request) -> Redis:
    return request.app.state.redis


RedisDep = Annotated[Redis, Depends(get_redis)]


def _path_is_under(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith(f"{prefix}/")


def _onboarding_gate_applies(request: Request) -> bool:
    if not settings.onboarding_enabled:
        return False
    method = request.method.upper()
    if method in {"GET", "HEAD", "OPTIONS", "DELETE"}:
        return False

    path = request.url.path.rstrip("/")
    safe_prefixes = (
        "/api/v1/onboarding",
        "/api/v1/me",
        "/api/v1/support",
        "/api/v1/notifications",
    )
    if any(_path_is_under(path, prefix) for prefix in safe_prefixes):
        return False

    # Recovery/reversal actions must stay possible after an onboarding version bump.
    if path.endswith("/cancel") or path.endswith("/history/restore"):
        return False
    return path.startswith("/api/v1/")


async def _existing_inviter(session: AsyncSession, telegram_id: int) -> int | None:
    if telegram_id <= 0:
        return None
    return await session.scalar(
        select(User.telegram_id).where(User.telegram_id == telegram_id)
    )


async def _validated_startapp_inviter(
    session: AsyncSession,
    start_param: str | None,
) -> int | None:
    """Validate referral attribution carried by a Telegram Mini App launch.

    Telegram-signed ``start_param`` is authoritative. Public post/remix/trend
    payloads validate that their source still exists, while referral ownership
    belongs to the authenticated user who shared the link rather than the
    original author of that source. Profile payloads stay bound to that profile.
    """

    link = parse_feed_deep_link(start_param)
    if link is None:
        return None
    if link.action == "ref":
        return await _existing_inviter(session, link.referral_telegram_id)
    if link.action == "trend":
        if link.trend_id is None or link.referral_telegram_id <= 0:
            return None
        try:
            await TrendService.get_public(session, trend_id=link.trend_id)
        except LookupError:
            return None
        return await _existing_inviter(session, link.referral_telegram_id)
    if link.action == "posts" and link.profile_referral_code:
        if str(link.referral_telegram_id) != link.profile_referral_code:
            return None
        try:
            author = await FeedService.author_by_referral_code(
                session,
                link.profile_referral_code,
            )
        except FeedNotFoundError:
            return None
        return author.telegram_id
    if link.generation_id is None:
        return None

    generation = None
    for surface in ("feed", "profile"):
        try:
            generation = await FeedService.assert_surface_visible(
                session,
                link.generation_id,
                surface=surface,
            )
            break
        except FeedNotFoundError:
            continue
    if generation is None:
        return None
    return await _existing_inviter(session, link.referral_telegram_id)


async def get_current_user(
    request: Request,
    session: SessionDep,
    x_telegram_init_data: Annotated[str | None, Header()] = None,
    x_telegram_start_param: Annotated[str | None, Header()] = None,
) -> User:
    if not settings.bot_token:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Bot is not configured")
    if not x_telegram_init_data:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Telegram initData")
    try:
        init_data = safe_parse_webapp_init_data(settings.bot_token, x_telegram_init_data)
        # Real aiogram WebAppInitData always carries auth_date. Some unit tests
        # use a minimal SimpleNamespace after replacing signature parsing; keep
        # those test doubles compatible without weakening the real wire format.
        auth_date = getattr(init_data, "auth_date", None)
        if auth_date is not None:
            validate_webapp_auth_date(auth_date)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired Telegram initData"
        ) from exc
    if init_data.user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Telegram user missing")
    web_user = init_data.user
    tg_user = TelegramUser(
        id=web_user.id,
        is_bot=False,
        first_name=web_user.first_name,
        last_name=web_user.last_name,
        username=web_user.username,
        language_code=web_user.language_code,
    )
    signed_start_param = str(getattr(init_data, "start_param", None) or "").strip()
    fallback_start_param = str(x_telegram_start_param or "").strip()
    resolved_start_param = signed_start_param or fallback_start_param or None
    inviter_telegram_id = await _validated_startapp_inviter(session, resolved_start_param)
    user = await UserService.get_or_create(
        session,
        tg_user,
        inviter_telegram_id=inviter_telegram_id,
    )
    await session.commit()
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is restricted")
    if _onboarding_gate_applies(request) and not await OnboardingService.is_complete(session, user.id):
        raise HTTPException(
            status_code=status.HTTP_428_PRECONDITION_REQUIRED,
            detail={
                "code": "onboarding_required",
                "version": settings.onboarding_version.strip() or "1",
            },
        )
    # Carry the authenticated principal on this SQLAlchemy session so shared
    # quote/model preflight code can read only this user's trusted reference
    # metadata without changing every service method signature.
    session.info["current_user_id"] = user.id
    return user


CurrentUserDep = Annotated[User, Depends(get_current_user)]


async def get_optional_current_user(
    request: Request,
    session: SessionDep,
    x_telegram_init_data: Annotated[str | None, Header()] = None,
    x_telegram_start_param: Annotated[str | None, Header()] = None,
) -> User | None:
    """Authenticate signed Mini App requests while preserving public read previews."""

    if not x_telegram_init_data:
        return None
    return await get_current_user(
        request,
        session,
        x_telegram_init_data,
        x_telegram_start_param,
    )


OptionalCurrentUserDep = Annotated[User | None, Depends(get_optional_current_user)]


async def get_onboarded_user(
    user: CurrentUserDep,
    session: SessionDep,
) -> User:
    if not await OnboardingService.is_complete(session, user.id):
        raise HTTPException(
            status_code=status.HTTP_428_PRECONDITION_REQUIRED,
            detail={
                "code": "onboarding_required",
                "version": settings.onboarding_version.strip() or "1",
            },
        )
    return user


OnboardedUserDep = Annotated[User, Depends(get_onboarded_user)]
