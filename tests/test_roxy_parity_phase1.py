import random
from decimal import Decimal
from pathlib import Path

import pytest

from app.api.v1.generation_history import hidden_generations
from app.api.v1.generations import hide_generation_from_history, restore_generation_to_history
from app.db.models import Generation, User
from app.db.session import SessionFactory


ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "app" / "web" / "mini_app"


def _telegram_id() -> int:
    return random.randint(9_810_000_000_000_000, 9_819_999_999_999_999)


@pytest.mark.asyncio
async def test_hidden_history_is_durable_and_restorable_after_fresh_list() -> None:
    async with SessionFactory() as session:
        user = User(telegram_id=_telegram_id(), first_name="Parity hidden history")
        session.add(user)
        await session.flush()
        generation = Generation(
            user_id=user.id,
            kind="text_to_image",
            status="succeeded",
            prompt="restore me after reload",
            cost_rox=Decimal("8"),
            provider="kie",
            parameters={"_model_id": "nano-banana"},
        )
        session.add(generation)
        await session.commit()

        await hide_generation_from_history(generation.id, user, session)
        hidden = await hidden_generations(user, session, limit=20, before=None)
        assert [item["id"] for item in hidden["items"]] == [str(generation.id)]
        assert hidden["items"][0]["hidden_from_history"] is True

        await restore_generation_to_history(generation.id, user, session)
        hidden = await hidden_generations(user, session, limit=20, before=None)
        assert hidden["items"] == []


def test_hidden_history_ui_loads_persisted_server_state() -> None:
    source = (MINI / "roxy-history-management.js").read_text(encoding="utf-8")
    assert "/api/v1/generation-history/hidden?limit=50" in source
    assert 'activeTab: "visible"' in source
    assert 'button("Скрытые"' in source
    assert 'button("Вернуть"' in source
    assert "__hiddenLocally" not in source


def test_generation_history_router_is_registered() -> None:
    source = (ROOT / "app" / "api" / "router.py").read_text(encoding="utf-8")
    assert "generation_history," in source
    assert "api_router.include_router(generation_history.router)" in source
