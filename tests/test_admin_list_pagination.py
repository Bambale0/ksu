from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import delete, func, select

from app.api.admin_deps import AdminContext, get_verified_admin
from app.api.v1 import admin_audit, admin_capabilities, admin_control, admin_operations, admin_users
from app.core.config import settings
from app.db.admin_models import AdminTrend, CmsDocument, NotificationCampaign, PromptLibraryItem
from app.db.models import AdminAccount, AdminSession, PromoCode, ReferralReward, User, WalletTransaction
from app.db.session import SessionFactory

pytestmark = pytest.mark.asyncio

CASES = [
    ("rewards", "/api/v1/admin/referrals/rewards", "referrals.read", 100),
    ("campaigns", "/api/v1/admin/notifications/campaigns", "notifications.read", 100),
    ("promos", "/api/v1/admin/promocodes", "promocodes.read", 100),
    ("promos", "/api/v1/admin/control/promocodes", "promocodes.read", 100),
    ("documents", "/api/v1/admin/cms/documents", "cms.read", 100),
    ("prompts", "/api/v1/admin/prompts", "prompts.read", 100),
    ("trends", "/api/v1/admin/trends", "social.moderate", 200),
    ("sessions", "/api/v1/admin/security/sessions", "security.read", 100),
]
MODELS = {
    "rewards": ReferralReward, "campaigns": NotificationCampaign, "promos": PromoCode,
    "documents": CmsDocument, "prompts": PromptLibraryItem, "trends": AdminTrend,
    "sessions": AdminSession,
}


@pytest.fixture
async def admin_client(monkeypatch):
    monkeypatch.setattr(settings, "admin_security_key", "pagination-test-only-security-key-32-plus-characters")
    now = datetime.now(UTC)
    async with SessionFactory() as session:
        users = [User(
            telegram_id=9_000_000_000_000 + uuid.uuid4().int % 10**12,
            first_name="Synthetic pagination actor",
        ) for _ in range(4)]
        session.add_all(users)
        await session.flush()
        account = AdminAccount(user_id=users[0].id, role="owner", permission_overrides={}, mfa_enabled=True)
        session.add(account)
        await session.flush()
        admin_session = AdminSession(
            admin_id=account.id, token_hash=uuid.uuid4().hex,
            created_at=now, last_seen_at=now, expires_at=now + timedelta(hours=1),
            idle_expires_at=now + timedelta(hours=1), mfa_verified=True,
            session_version=account.session_version,
        )
        session.add(admin_session)
        await session.commit()
    context = AdminContext(account=account, session=admin_session, user=users[0])
    actors = SimpleNamespace(context=context, partner=users[1], customer=users[2], other_partner=users[3])
    app = FastAPI()
    for router in (admin_operations.router, admin_capabilities.router, admin_control.router, admin_audit.router, admin_users.router):
        app.include_router(router, prefix="/api/v1")

    async def verified():
        return context

    app.dependency_overrides[get_verified_admin] = verified
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            yield client, actors
    finally:
        async with SessionFactory() as session:
            await session.execute(delete(AdminSession).where(AdminSession.admin_id == account.id))
            await session.execute(delete(AdminAccount).where(AdminAccount.id == account.id))
            await session.execute(delete(User).where(User.id.in_([user.id for user in users])))
            await session.commit()


@asynccontextmanager
async def seeded(kind, actors, *, count=5):
    model = MODELS[kind]
    now = datetime.now(UTC)
    stamp_column = (
        AdminSession.last_seen_at if kind == "sessions" else
        CmsDocument.updated_at if kind == "documents" else model.created_at
    )
    filters, params = [], {}
    if kind == "rewards":
        filters = [ReferralReward.partner_user_id == actors.partner.id, ReferralReward.status == "pending"]
        params = {"partner_user_id": str(actors.partner.id), "status": "pending"}
    elif kind == "prompts":
        filters = [PromptLibraryItem.status == "pending"]
        params = {"status": "pending"}
    elif kind == "trends":
        filters = [AdminTrend.is_active.is_(True)]
        params = {"is_active": "true"}
    elif kind == "sessions":
        filters = [
            AdminSession.revoked_at.is_(None), AdminSession.expires_at > now,
            AdminSession.idle_expires_at > now,
        ]
        params = {"active_only": "true"}

    ledger_ids = []
    async with SessionFactory() as session:
        baseline = int(await session.scalar(select(func.count()).select_from(model).where(*filters)) or 0)
        previous = await session.scalar(select(func.max(stamp_column)))
        stamp = max(now, previous or now) + timedelta(seconds=1)
        rows, extras = [], []
        for index in range(count):
            item_id = uuid.uuid4()
            common = {"id": item_id, "created_at": stamp}
            timestamped = {**common, "updated_at": stamp}
            if kind == "rewards":
                tx = WalletTransaction(
                    id=uuid.uuid4(), user_id=actors.customer.id, kind="payment",
                    amount=Decimal("1"), balance_before=Decimal("0"), balance_after=Decimal("1"),
                )
                session.add(tx)
                await session.flush()
                ledger_ids.append(tx.id)
                row = ReferralReward(
                    **common, partner_user_id=actors.partner.id, source_user_id=actors.customer.id,
                    source_transaction_id=tx.id, level=1, percent=Decimal("1"),
                    amount=Decimal("0.01"), status="pending",
                )
            elif kind == "campaigns":
                row = NotificationCampaign(
                    **timestamped, name=f"Pagination campaign {index}", status="draft",
                    created_by_admin_id=actors.context.account.id, segment={},
                    message={"title": "Synthetic", "body": "List fixture; never sent"},
                )
            elif kind == "promos":
                row = PromoCode(
                    **timestamped, code=f"PAGE_{item_id.hex}".upper(), reward_amount=Decimal("0"),
                    partner_user_id=actors.partner.id,
                )
            elif kind == "documents":
                row = CmsDocument(**timestamped, slug=f"page-{item_id.hex}", title=f"Document {index}")
            elif kind == "prompts":
                row = PromptLibraryItem(
                    **timestamped, title=f"Prompt {index}", prompt="Synthetic private prompt",
                    status="pending", created_by_user_id=actors.customer.id,
                )
            elif kind == "trends":
                row = AdminTrend(
                    **timestamped, title=f"Trend {index}", payload={"model_id": "nano-banana", "tags": []},
                    is_active=True, created_by_admin_id=actors.context.account.id,
                )
            else:
                row = AdminSession(
                    **common, admin_id=actors.context.account.id, token_hash=uuid.uuid4().hex,
                    last_seen_at=stamp, expires_at=now + timedelta(hours=1),
                    idle_expires_at=now + timedelta(hours=1), mfa_verified=True, session_version=1,
                )
            rows.append(row)

        if kind == "rewards":
            for partner_id, status in [(actors.other_partner.id, "pending"), (actors.partner.id, "accrued")]:
                tx = WalletTransaction(
                    id=uuid.uuid4(), user_id=actors.customer.id, kind="payment",
                    amount=Decimal("1"), balance_before=Decimal("0"), balance_after=Decimal("1"),
                )
                session.add(tx)
                await session.flush()
                ledger_ids.append(tx.id)
                extras.append(ReferralReward(
                    id=uuid.uuid4(), partner_user_id=partner_id, source_user_id=actors.customer.id,
                    source_transaction_id=tx.id, level=1, percent=Decimal("1"),
                    amount=Decimal("0.01"), status=status, created_at=stamp,
                ))
        elif kind == "prompts":
            extras.append(PromptLibraryItem(
                id=uuid.uuid4(), title="Filtered prompt", prompt="Synthetic", status="rejected",
                created_at=stamp, updated_at=stamp,
            ))
        elif kind == "trends":
            extras.append(AdminTrend(
                id=uuid.uuid4(), title="Inactive trend", payload={}, is_active=False,
                created_by_admin_id=actors.context.account.id, created_at=stamp, updated_at=stamp,
            ))
        elif kind == "sessions":
            for reason in ("revoked", "expired", "idle"):
                extras.append(AdminSession(
                    id=uuid.uuid4(), admin_id=actors.context.account.id, token_hash=uuid.uuid4().hex,
                    created_at=stamp, last_seen_at=stamp, mfa_verified=True, session_version=1,
                    revoked_at=now if reason == "revoked" else None,
                    expires_at=now - timedelta(hours=1) if reason == "expired" else now + timedelta(hours=1),
                    idle_expires_at=now - timedelta(hours=1) if reason == "idle" else now + timedelta(hours=1),
                ))
        session.add_all([*rows, *extras])
        await session.commit()
        ids = sorted([row.id for row in rows], reverse=True)
        all_ids = [row.id for row in [*rows, *extras]]
    try:
        yield SimpleNamespace(ids=[str(value) for value in ids], rows=rows, extras=extras,
                              total=baseline + count, params=params)
    finally:
        async with SessionFactory() as session:
            await session.execute(delete(model).where(model.id.in_(all_ids)))
            if ledger_ids:
                await session.execute(delete(WalletTransaction).where(WalletTransaction.id.in_(ledger_ids)))
            await session.commit()


@pytest.mark.parametrize("kind,path,permission,default_limit", CASES)
async def test_admin_pages_reach_older_entities_with_stable_order_and_filtered_totals(
    admin_client, kind, path, permission, default_limit,
):
    client, actors = admin_client
    count = 205 if path == "/api/v1/admin/promocodes" else 5
    async with seeded(kind, actors, count=count) as data:
        first_raw = await client.get(path, params={**data.params, "limit": 2, "offset": 0})
        second_raw = await client.get(path, params={**data.params, "limit": 2, "offset": 2})
        assert first_raw.status_code == second_raw.status_code == 200
        first_ids = {item["id"] for item in first_raw.json()["items"]}
        second_ids = {item["id"] for item in second_raw.json()["items"]}
        assert first_ids.isdisjoint(second_ids), "The second page repeats the first page"

        async def page(offset, limit):
            response = await client.get(path, params={**data.params, "limit": limit, "offset": offset})
            assert response.status_code == 200, response.text
            result = response.json()
            assert result["total"] == data.total
            assert result["limit"] == limit and result["offset"] == offset
            assert result["has_more"] is (offset + len(result["items"]) < data.total)
            return [item["id"] for item in result["items"]]

        assert await page(0, 2) == data.ids[:2]
        assert await page(2, 2) == data.ids[2:4]
        assert await page(4, 1) == data.ids[4:5]
        if count > 200:
            assert await page(200, 3) == data.ids[200:203]
        assert await page(data.total, 2) == []
        default = await client.get(path, params=data.params)
        assert default.status_code == 200
        payload = default.json()
        assert payload["limit"] == default_limit and payload["offset"] == 0
        assert len(payload["items"]) == min(default_limit, data.total)
        assert [item["id"] for item in payload["items"][:count]] == data.ids[:default_limit]


@pytest.mark.parametrize("kind,path,permission,default_limit", CASES)
async def test_admin_pagination_preserves_server_read_permissions(
    admin_client, kind, path, permission, default_limit,
):
    client, actors = admin_client
    actors.context.account.permission_overrides = {"deny": [permission]}
    response = await client.get(path, params={"limit": 2, "offset": 2})
    assert response.status_code == 403, response.text


@pytest.mark.parametrize("path", ["/api/v1/admin/promocodes", "/api/v1/admin/control/promocodes"])
async def test_promo_exact_lookup_remains_distinct_from_paged_list(admin_client, path):
    client, actors = admin_client
    async with seeded("promos", actors) as data:
        row = data.rows[0]
        response = await client.get(path, params={"q": row.code.lower(), "limit": 2, "offset": 4})
        assert response.status_code == 200, response.text
        assert response.json()["item"]["id"] == str(row.id)
        assert "items" not in response.json()
        missing = await client.get(path, params={"q": f"MISSING_{uuid.uuid4().hex}"})
        assert missing.status_code == 404


async def test_trend_search_filters_the_complete_set_without_searching_private_prompts(admin_client):
    client, actors = admin_client
    async with seeded("trends", actors) as data:
        marker = uuid.uuid4().hex
        needle = f"{marker}needle"
        async with SessionFactory() as session:
            values = [
                (f"{needle} portrait", {"model_id": "alpha", "tags": []}),
                ("Plain one", {"model_id": f"{needle}-model", "tags": []}),
                ("Plain two", {"model_id": "gamma", "tags": [needle, "Платье"]}),
                (f"{marker} 100%_safe", {"model_id": None, "tags": "legacy scalar"}),
                ("Other", {"tags": None, "prompt": f"{needle}-private-only"}),
            ]
            for row, (title, payload) in zip(data.rows, values, strict=True):
                stored = await session.get(AdminTrend, row.id)
                stored.title, stored.payload = title, payload
            inactive = await session.get(AdminTrend, data.extras[0].id)
            inactive.title = f"{needle} inactive"
            await session.commit()
        expected = sorted([str(row.id) for row in data.rows[:3]], reverse=True)
        first = await client.get("/api/v1/admin/trends", params={
            "q": needle, "is_active": "true", "limit": 2, "offset": 0,
        })
        assert first.status_code == 200, first.text
        assert [item["id"] for item in first.json()["items"]] == expected[:2]
        assert first.json()["total"] == 3
        second = await client.get("/api/v1/admin/trends", params={
            "q": needle, "is_active": "true", "limit": 2, "offset": 2,
        })
        assert [item["id"] for item in second.json()["items"]] == expected[2:]
        assert second.json()["has_more"] is False
        for query, expected_ids in [
            (f"{needle} ПЛАТЬЕ", [str(data.rows[2].id)]),
            (f"{marker} 100%_safe", [str(data.rows[3].id)]),
            (f"{needle}-private-only", []),
        ]:
            response = await client.get("/api/v1/admin/trends", params={"q": query, "is_active": "true"})
            assert response.status_code == 200, response.text
            assert response.json()["total"] == len(expected_ids)
            assert [item["id"] for item in response.json()["items"]] == expected_ids
        inactive = await client.get("/api/v1/admin/trends", params={"q": needle, "is_active": "false"})
        assert inactive.json()["total"] == 1
        assert inactive.json()["items"][0]["id"] == str(data.extras[0].id)


async def test_existing_user_pages_are_stable_when_many_rows_share_created_at(admin_client):
    client, _actors = admin_client
    marker = f"pageorder{uuid.uuid4().hex}"
    prefix = uuid.uuid4().int & ~255
    ids = [uuid.UUID(int=prefix + index) for index in range(6)]
    now = datetime.now(UTC)
    async with SessionFactory() as session:
        latest = await session.scalar(select(func.max(User.created_at)))
        stamp = max(now, latest or now) + timedelta(seconds=1)
        session.add_all([
            User(
                id=ids[index],
                telegram_id=9_000_000_000_000 + uuid.uuid4().int % 10**12,
                first_name=marker, created_at=stamp, updated_at=stamp,
            )
            for index in (2, 5, 1, 4, 0, 3)
        ])
        await session.commit()
    try:
        observed = []
        for offset in (0, 2, 4):
            response = await client.get("/api/v1/admin/users", params={
                "q": marker, "limit": 2, "offset": offset,
            })
            assert response.status_code == 200, response.text
            observed.extend(item["id"] for item in response.json()["items"])
        expected = [str(item) for item in reversed(ids)]
        assert observed == expected
        assert len(set(observed)) == len(ids)
    finally:
        async with SessionFactory() as session:
            await session.execute(delete(User).where(User.id.in_(ids)))
            await session.commit()
