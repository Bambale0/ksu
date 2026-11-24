"""Passwordless web login, Telegram identity proof and Yandex OAuth (PKCE).

All providers resolve to canonical users.id. Web sessions are first-party,
opaque, server-backed cookies. Provider collisions never merge balances.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import re
import secrets
import smtplib
import ssl
from email.message import EmailMessage
from urllib.parse import parse_qsl, urlencode, urlsplit
from uuid import UUID

import httpx
from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import SessionDep
from app.api.v1.browser_auth import TelegramLoginPayload
from app.core.config import settings
from app.core.telegram_browser_auth import verify_telegram_login_widget
from app.db.models import User
from app.db.web_auth_models import WebIdentity
from app.services.web_identity import verified_telegram_identity, verified_web_identity
from app.services.web_sessions import (
    assert_first_party, current_web_user_id, issue_web_session,
    redis_from_request, revoke_web_session,
)

router = APIRouter(prefix="/web-auth", tags=["web-auth"])
YANDEX_AUTH_URL = "https://oauth.yandex.ru/authorize"
YANDEX_TOKEN_URL = "https://oauth.yandex.ru/token"
YANDEX_USER_URL = "https://login.yandex.ru/info"
EMAIL_RE = re.compile(r"^[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}$", re.I)
EMAIL_TTL = 600
YANDEX_TTL = 600


def _email_ready() -> bool:
    return bool(
        settings.web_auth_email_secret and
        settings.web_auth_smtp_host and
        settings.web_auth_smtp_sender
    )


def _yandex_ready() -> bool:
    if not settings.web_auth_yandex_client_id or not settings.web_auth_yandex_redirect_uri:
        return False
    redirect = urlsplit(settings.web_auth_yandex_redirect_uri)
    public = urlsplit(settings.public_base_url)
    return (
        redirect.scheme == "https"
        and bool(public.netloc)
        and redirect.netloc.lower() == public.netloc.lower()
        and redirect.path == "/api/v1/web-auth/yandex/callback"
    )


def _normalized_email(raw: str) -> str:
    email = str(raw or "").strip().lower()
    if len(email) > 254 or not EMAIL_RE.fullmatch(email) or ".." in email:
        raise HTTPException(422, "Некорректный адрес почты")
    return email


def _email_key(email: str) -> str:
    return hashlib.sha256(email.encode("utf-8")).hexdigest()


def _otp_digest(email: str, otp: str) -> str:
    return hmac.new(
        settings.web_auth_email_secret.encode("utf-8"),
        f"ROXY_EMAIL_OTP:{email}:{otp}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _target_path(raw: str | None) -> str:
    """Only known studio routes and bounded public launch parameters."""
    try:
        parsed = urlsplit(str(raw or "").strip())
    except ValueError:
        return "/mini-app/"
    path = parsed.path.rstrip("/")
    if parsed.scheme or parsed.netloc or parsed.fragment or path not in {"/mini-app", "/mini-app/trend"}:
        return "/mini-app/"
    params = dict(parse_qsl(parsed.query))
    query = {}
    if path == "/mini-app/trend":
        try:
            query["id"] = str(UUID(params.get("id", "")))
        except (ValueError, TypeError, AttributeError):
            return "/mini-app/"
    else:
        route = params.get("route")
        if route in {"create", "profile", "partners"}:
            query["route"] = route
        if route == "create" and params.get("create_media") in {"image", "video"}:
            query["create_media"] = params["create_media"]
    for key in ("startapp", "start_payload", "ref"):
        value = params.get(key)
        if value and len(value) <= 256:
            query[key] = value
    return path + "/" + ("?" + urlencode(query) if query else "")


def _mail_send_sync(email: str, otp: str) -> None:
    message = EmailMessage()
    message["From"] = settings.web_auth_smtp_sender
    message["To"] = email
    message["Subject"] = "ROXY AI STUDIO — код входа"
    message.set_content(
        f"Код входа в ROXY AI STUDIO: {otp}\n"
        "Он действителен 10 минут и используется один раз.\n"
        "Если это были не вы, проигнорируйте письмо."
    )
    port = settings.web_auth_smtp_port
    host = settings.web_auth_smtp_host
    if settings.web_auth_smtp_ssl:
        with smtplib.SMTP_SSL(host, port, timeout=12, context=ssl.create_default_context()) as smtp:
            if settings.web_auth_smtp_username:
                smtp.login(settings.web_auth_smtp_username, settings.web_auth_smtp_password)
            smtp.send_message(message)
    else:
        with smtplib.SMTP(host, port, timeout=12) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            if settings.web_auth_smtp_username:
                smtp.login(settings.web_auth_smtp_username, settings.web_auth_smtp_password)
            smtp.send_message(message)


class EmailStart(BaseModel):
    email: str = Field(min_length=3, max_length=254)


class EmailVerify(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    code: str = Field(pattern=r"^[0-9]{6}$")
    link: bool = False


class TelegramVerify(BaseModel):
    telegram_auth: TelegramLoginPayload
    link: bool = False


@router.get("/config")
async def web_auth_config(response: Response) -> dict[str, object]:
    response.headers["Cache-Control"] = "no-store"
    return {
        "ok": True,
        "providers": {
            "telegram": bool(settings.bot_token and settings.bot_username),
            "email": _email_ready(),
            "yandex": _yandex_ready(),
        },
        "bot_username": settings.bot_username.strip().lstrip("@") if settings.bot_token else "",
    }


@router.get("/me")
async def web_auth_me(request: Request, session: SessionDep, response: Response) -> dict[str, object]:
    response.headers["Cache-Control"] = "no-store"
    user_id = await current_web_user_id(request)
    if not user_id:
        return {"authenticated": False}
    user = await session.get(User, user_id)
    if not user or not user.is_active:
        return {"authenticated": False}
    ids = (await session.scalars(
        select(WebIdentity.provider).where(WebIdentity.user_id == user.id)
    )).all()
    return {
        "authenticated": True, "user_id": str(user.id),
        "telegram_connected": user.telegram_id is not None,
        "providers": sorted(set(ids) | ({"telegram"} if user.telegram_id else set())),
        "first_name": user.first_name,
    }


@router.post("/email/request")
async def request_email_code(payload: EmailStart, request: Request) -> dict[str, object]:
    assert_first_party(request)
    if not _email_ready():
        raise HTTPException(503, "Вход по почте ещё не настроен")
    email = _normalized_email(payload.email)
    redis = redis_from_request(request)
    key = _email_key(email)
    ip = request.client.host if request.client else "unknown"
    ip_digest = hashlib.sha256(ip.encode()).hexdigest()
    try:
        per_ip = await redis.incr("roxy:email:ip:" + ip_digest)
        if per_ip == 1:
            await redis.expire("roxy:email:ip:" + ip_digest, 3600)
        if per_ip > 15:
            raise HTTPException(429, "Слишком много запросов")
        admitted = await redis.set("roxy:email:cooldown:" + key, "1", nx=True, ex=75)
        if not admitted:
            raise HTTPException(429, "Запросите код немного позже")
        code = f"{secrets.randbelow(1_000_000):06d}"
        await redis.set("roxy:email:code:" + key, _otp_digest(email, code), ex=EMAIL_TTL)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, "Сервис входа временно недоступен") from exc

    try:
        await asyncio.to_thread(_mail_send_sync, email, code)
    except Exception as exc:
        await redis.delete("roxy:email:code:" + key)
        raise HTTPException(503, "Письмо временно не отправляется") from exc
    return {"ok": True, "message": "Проверьте почту — код действует 10 минут"}


@router.post("/email/verify")
async def verify_email(
    payload: EmailVerify, request: Request, response: Response, session: SessionDep,
) -> dict[str, object]:
    assert_first_party(request)
    if not _email_ready():
        raise HTTPException(503, "Вход по почте ещё не настроен")
    email = _normalized_email(payload.email)
    key = _email_key(email)
    redis = redis_from_request(request)
    try:
        stored = await redis.getdel("roxy:email:code:" + key)
    except Exception as exc:
        raise HTTPException(503, "Сервис входа временно недоступен") from exc
    if not stored or not hmac.compare_digest(str(stored), _otp_digest(email, payload.code)):
        raise HTTPException(401, "Код неверный или истёк")
    link_user = await current_web_user_id(request) if payload.link else None
    if payload.link and link_user is None:
        raise HTTPException(401, "Сначала войдите в аккаунт для привязки")
    user = await verified_web_identity(
        session, provider="email", subject=email, display_email=email,
        display_name=email.split("@", 1)[0], link_user_id=link_user,
    )
    await issue_web_session(request, response, user.id)
    return {"ok": True, "user_id": str(user.id), "telegram_connected": user.telegram_id is not None}


@router.post("/telegram")
async def telegram_web_login(
    payload: TelegramVerify, request: Request, response: Response, session: SessionDep,
) -> dict[str, object]:
    assert_first_party(request)
    if not settings.bot_token:
        raise HTTPException(503, "Вход через Telegram ещё не настроен")
    try:
        identity = verify_telegram_login_widget(
            payload.telegram_auth.model_dump(exclude_none=True),
            settings.bot_token,
        )
    except ValueError as exc:
        raise HTTPException(401, "Недействительное подтверждение Telegram") from exc
    link_user = await current_web_user_id(request) if payload.link else None
    if payload.link and link_user is None:
        raise HTTPException(401, "Сначала войдите в аккаунт для привязки")
    user = await verified_telegram_identity(session, verified_user=identity, link_user_id=link_user)
    await issue_web_session(request, response, user.id)
    return {"ok": True, "user_id": str(user.id), "telegram_connected": True}


@router.get("/yandex/start")
async def yandex_start(
    request: Request,
    link: bool = Query(default=False),
    next: str = Query(default="/mini-app/", max_length=1000),
) -> RedirectResponse:
    if not _yandex_ready():
        raise HTTPException(503, "Вход через Яндекс ещё не настроен")
    owner = await current_web_user_id(request) if link else None
    if link and owner is None:
        raise HTTPException(401, "Сначала войдите в аккаунт для привязки")
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    payload = json.dumps({"verifier": verifier, "link_user_id": str(owner) if owner else "",
                          "next": _target_path(next)}, separators=(",", ":"))
    try:
        await redis_from_request(request).set("roxy:yandex:state:" + state, payload, nx=True, ex=YANDEX_TTL)
    except Exception as exc:
        raise HTTPException(503, "Вход временно недоступен") from exc
    url = YANDEX_AUTH_URL + "?" + urlencode({
        "response_type": "code", "client_id": settings.web_auth_yandex_client_id,
        "redirect_uri": settings.web_auth_yandex_redirect_uri, "scope": "login:info login:email",
        "state": state, "code_challenge": challenge, "code_challenge_method": "S256",
    })
    response = RedirectResponse(url, status_code=302)
    response.set_cookie(
        "roxy_yandex_state", state, secure=settings.is_production,
        httponly=True, samesite="lax", max_age=YANDEX_TTL, path="/api/v1/web-auth/yandex",
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@router.get("/yandex/callback")
async def yandex_callback(
    request: Request, session: SessionDep,
    state: str = Query(default="", max_length=256),
    code: str = Query(default="", max_length=2000),
    error: str = Query(default="", max_length=100),
) -> RedirectResponse:
    state_cookie = str(request.cookies.get("roxy_yandex_state") or "")
    if not state or not state_cookie or not hmac.compare_digest(state, state_cookie):
        raise HTTPException(401, "OAuth state verification failed")
    try:
        raw = await redis_from_request(request).getdel("roxy:yandex:state:" + state)
    except Exception as exc:
        raise HTTPException(503, "Вход временно недоступен") from exc
    if not raw:
        raise HTTPException(401, "OAuth state expired or already used")
    if error or not code or not _yandex_ready():
        return RedirectResponse("/login?error=yandex", status_code=303)
    try:
        ctx = json.loads(raw)
        if ctx.get("link_user_id"):
            active = await current_web_user_id(request)
            if not active or str(active) != ctx["link_user_id"]:
                raise HTTPException(401, "OAuth linking session expired")
        async with httpx.AsyncClient(timeout=12, follow_redirects=False) as http:
            token = await http.post(YANDEX_TOKEN_URL, data={
                "grant_type": "authorization_code", "code": code,
                "client_id": settings.web_auth_yandex_client_id,
                "client_secret": settings.web_auth_yandex_client_secret,
                "code_verifier": ctx["verifier"],
            })
            token.raise_for_status()
            access_token = token.json().get("access_token")
            if not isinstance(access_token, str) or len(access_token) < 10:
                raise ValueError("Missing token")
            profile = await http.get(YANDEX_USER_URL, headers={"Authorization": f"OAuth {access_token}"})
            profile.raise_for_status()
            identity = profile.json()
            subject = str(identity.get("id") or "")
            if not subject.isdigit():
                raise ValueError("Missing stable Yandex user id")
    except HTTPException:
        raise
    except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
        raise HTTPException(502, "Не удалось проверить вход через Яндекс") from exc
    user = await verified_web_identity(
        session, provider="yandex", subject=subject,
        display_name=str(identity.get("display_name") or identity.get("real_name") or "ROXY"),
        display_email=str(identity.get("default_email") or "") or None,
        link_user_id=UUID(ctx["link_user_id"]) if ctx.get("link_user_id") else None,
    )
    response = RedirectResponse(
        "/login?linked=1" if ctx.get("link_user_id") else _target_path(ctx.get("next")),
        status_code=303,
    )
    response.delete_cookie(
        "roxy_yandex_state", path="/api/v1/web-auth/yandex",
        secure=settings.is_production, httponly=True, samesite="lax",
    )
    await issue_web_session(request, response, user.id)
    return response


@router.post("/logout")
async def web_logout(request: Request, response: Response) -> dict[str, bool]:
    assert_first_party(request)
    await revoke_web_session(request, response)
    return {"ok": True}
