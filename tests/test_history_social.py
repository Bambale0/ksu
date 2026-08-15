from decimal import Decimal
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from app.api.v1.social import (
    generation_social_state,
    like_generation,
    public_profile,
    public_profile_by_username,
    subscribe,
    subscriptions,
    unlike_generation,
    unsubscribe,
)
from app.db.models import Generation, User
from app.db.profile_models import UserPreference
from app.db.session import SessionFactory
from app.db.social_models import GenerationLike, UserSubscription

ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "app" / "web" / "mini_app"


@pytest.mark.asyncio
async def test_generation_like_is_owner_scoped_and_idempotent() -> None:
    async with SessionFactory() as session:
        owner = User(telegram_id=940000000000001, first_name="Owner")
        stranger = User(telegram_id=940000000000002, first_name="Stranger")
        session.add_all([owner, stranger])
        await session.flush()
        generation = Generation(
            user_id=owner.id,
            kind="text_to_image",
            status="succeeded",
            prompt="test",
            cost_rox=Decimal("1.00"),
            parameters={},
        )
        session.add(generation)
        await session.commit()
        generation_id = generation.id

        first = await like_generation(generation_id, owner, session)
        second = await like_generation(generation_id, owner, session)
        assert first["liked_by_me"] is True
        assert second["liked_by_me"] is True
        assert second["like_count"] == 1
        count = await session.scalar(
            select(func.count()).select_from(GenerationLike).where(
                GenerationLike.generation_id == generation_id
            )
        )
        assert int(count or 0) == 1

        with pytest.raises(HTTPException) as error:
            await generation_social_state(generation_id, stranger, session)
        assert error.value.status_code == 404

        removed = await unlike_generation(generation_id, owner, session)
        removed_again = await unlike_generation(generation_id, owner, session)
        assert removed["liked_by_me"] is False
        assert removed_again["like_count"] == 0


@pytest.mark.asyncio
async def test_public_profiles_are_opt_in_safe_and_subscriptions_survive_privacy_change() -> None:
    async with SessionFactory() as session:
        viewer = User(telegram_id=940000000000003, first_name="Viewer")
        author = User(
            telegram_id=940000000000004,
            username="VisibleAuthor",
            first_name="Visible",
            last_name="Author",
        )
        private = User(
            telegram_id=940000000000005,
            username="PrivateAuthor",
            first_name="Private",
        )
        session.add_all([viewer, author, private])
        await session.flush()
        session.add_all(
            [
                UserPreference(user_id=author.id, profile_discoverable=True),
                UserPreference(user_id=private.id, profile_discoverable=False),
            ]
        )
        await session.commit()
        author_id = author.id
        private_id = private.id

        visible = await public_profile(author_id, viewer, session)
        assert visible["display_name"] == "Visible Author"
        assert visible["username"] == "VisibleAuthor"
        assert visible["profile_discoverable"] is True
        assert visible["subscribed_by_me"] is False
        for forbidden in ("telegram_id", "language_code", "balance_rox", "contact", "last_name"):
            assert forbidden not in visible

        by_username = await public_profile_by_username(
            viewer,
            session,
            username="@visibleauthor",
        )
        assert by_username["id"] == str(author_id)

        with pytest.raises(HTTPException) as private_error:
            await public_profile(private_id, viewer, session)
        assert private_error.value.status_code == 404
        with pytest.raises(HTTPException) as lookup_error:
            await public_profile_by_username(viewer, session, username="PrivateAuthor")
        assert lookup_error.value.status_code == 404

        first = await subscribe(author_id, viewer, session)
        second = await subscribe(author_id, viewer, session)
        assert first["subscribed_by_me"] is True
        assert second["follower_count"] == 1
        count = await session.scalar(
            select(func.count()).select_from(UserSubscription).where(
                UserSubscription.author_user_id == author_id
            )
        )
        assert int(count or 0) == 1

        with pytest.raises(HTTPException) as self_error:
            await subscribe(viewer.id, viewer, session)
        assert self_error.value.status_code == 409

        preference = await session.get(UserPreference, author_id)
        assert preference is not None
        preference.profile_discoverable = False
        await session.commit()

        listed = await subscriptions(viewer, session, limit=50, offset=0)
        assert len(listed["items"]) == 1
        assert listed["items"][0]["id"] == str(author_id)
        assert listed["items"][0]["profile_discoverable"] is False
        assert listed["items"][0]["display_name"] == "Скрытый профиль"
        assert listed["items"][0]["username"] is None

        result = await unsubscribe(author_id, viewer, session)
        assert result["subscribed_by_me"] is False
        listed = await subscriptions(viewer, session, limit=50, offset=0)
        assert listed["items"] == []


@pytest.mark.asyncio
async def test_owner_can_view_own_safe_profile_even_when_not_discoverable() -> None:
    async with SessionFactory() as session:
        user = User(
            telegram_id=940000000000006,
            username="SelfProfile",
            first_name="Self",
        )
        session.add(user)
        await session.flush()
        session.add(UserPreference(user_id=user.id, profile_discoverable=False))
        await session.commit()

        profile = await public_profile(user.id, user, session)
        assert profile["is_self"] is True
        assert profile["profile_discoverable"] is False
        assert profile["username"] == "SelfProfile"


def test_social_mini_app_uses_server_truth_confirmation_and_explicit_context() -> None:
    script = (MINI / "social.js").read_text(encoding="utf-8")
    context = (MINI / "roxy-generation-context.js").read_text(encoding="utf-8")
    for token in (
        '"X-Telegram-Init-Data"',
        "/api/v1/social/generations/",
        "/api/v1/social/profiles?username=",
        "/api/v1/social/subscriptions?limit=50",
        '/history`, {\n        method: "DELETE"',
        "askRemovalConfirmation",
        "socialHistoryConfirm",
        "roxy:history-context",
        "roxy:generation-context",
        "RoxyGenerationContext",
        "profile.profile_discoverable",
        "Профиль скрыт",
        "Создать контент",
    ):
        assert token in script, token
    assert "window.fetch =" not in script
    assert "originalFetch" not in script
    assert "localStorage" not in script
    assert "sessionStorage" not in script
    assert "initDataUnsafe" not in script
    assert 'emit("roxy:history-context"' in context
    assert 'emit("roxy:generation-context"' in context


def test_social_module_is_mounted_and_checked_by_ci() -> None:
    integration = (MINI / "shell-integration.js").read_text(encoding="utf-8")
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert 'stylesheet.href = "/mini-app/social.css"' in integration
    assert 'script.src = "/mini-app/social.js"' in integration
    assert "node --check app/web/mini_app/social.js" in workflow
    assert (MINI / "social.css").is_file()
