from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import delete, func, select

from app.api.admin_deps import AdminContext, get_verified_admin
from app.api.v1 import admin_creator_partnership
from app.db.creator_partner_models import CreatorPartnershipAgreement, CreatorPartnershipApplication
from app.db.models import AdminAccount, AdminSession, User
from app.db.session import SessionFactory


@asynccontextmanager
async def _creator_pages(kind: str):
    model = CreatorPartnershipApplication if kind == "applications" else CreatorPartnershipAgreement
    selected_status = "pending" if kind == "applications" else "active"
    excluded_status = "rejected" if kind == "applications" else "paused"
    now = datetime.now(UTC)
    ids_base = uuid.uuid4().int & ~0xFFFF
    expected_ids = [str(uuid.UUID(int=ids_base + index)) for index in range(6, 0, -1)]
    async with SessionFactory() as session:
        baseline = int(await session.scalar(
            select(func.count()).select_from(model).where(model.status == selected_status),
        ) or 0)
        newest = await session.scalar(select(func.max(model.created_at)))
        stamp = max(now, newest or now) + timedelta(seconds=1)
        users = [User(
            telegram_id=9_700_000_000_000 + uuid.uuid4().int % 1_000_000_000_000,
            first_name="Synthetic creator pagination",
        ) for _ in range(8)]
        session.add_all(users)
        await session.flush()
        account = AdminAccount(
            user_id=users[0].id, role="owner", permission_overrides={},
            is_active=True, mfa_enabled=True,
        )
        session.add(account)
        await session.flush()
        admin_session = AdminSession(
            admin_id=account.id, token_hash=uuid.uuid4().hex,
            created_at=now, last_seen_at=now,
            expires_at=now + timedelta(hours=1), idle_expires_at=now + timedelta(hours=1),
            mfa_verified=True, session_version=account.session_version,
        )
        session.add(admin_session)
        applications, agreements = [], []
        # Insertion order deliberately differs from both ascending and descending UUID order.
        for position, index in enumerate((2, 6, 1, 5, 3, 4, 7), start=1):
            target_id = uuid.UUID(int=ids_base + index)
            row_stamp = stamp if index <= 6 else stamp + timedelta(seconds=1)
            application = CreatorPartnershipApplication(
                id=target_id if kind == "applications" else uuid.uuid4(),
                user_id=users[position].id, idempotency_key=f"creator-page:{uuid.uuid4()}",
                channel_name="Synthetic creator", channel_url="https://example.invalid/creator",
                audience_size=100, cooperation_format="Synthetic cooperation", message="Fixture",
                status=(
                    selected_status if index <= 6 else excluded_status
                ) if kind == "applications" else "approved",
                created_at=row_stamp, updated_at=row_stamp,
            )
            applications.append(application)
            session.add(application)
            await session.flush()
            if kind == "agreements":
                agreement = CreatorPartnershipAgreement(
                    id=target_id, application_id=application.id, user_id=users[position].id,
                    status=selected_status if index <= 6 else excluded_status,
                    terms_summary="Synthetic agreement", monthly_rox=Decimal("1"), terms={},
                    starts_on=now.date(), approved_by_admin_id=account.id, approved_at=now,
                    created_at=row_stamp, updated_at=row_stamp,
                )
                agreements.append(agreement)
                session.add(agreement)
        await session.commit()
        context = AdminContext(account=account, session=admin_session, user=users[0])

    app = FastAPI()
    app.include_router(admin_creator_partnership.router, prefix="/api/v1")

    async def verified():
        return context

    app.dependency_overrides[get_verified_admin] = verified
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test",
        ) as client:
            yield client, expected_ids, baseline + 6, selected_status
    finally:
        async with SessionFactory() as session:
            if agreements:
                await session.execute(delete(CreatorPartnershipAgreement).where(
                    CreatorPartnershipAgreement.id.in_([item.id for item in agreements]),
                ))
            await session.execute(delete(CreatorPartnershipApplication).where(
                CreatorPartnershipApplication.id.in_([item.id for item in applications]),
            ))
            await session.execute(delete(AdminSession).where(AdminSession.admin_id == account.id))
            await session.execute(delete(AdminAccount).where(AdminAccount.id == account.id))
            await session.execute(delete(User).where(User.id.in_([user.id for user in users])))
            await session.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["applications", "agreements"])
async def test_creator_http_pages_have_stable_order_for_equal_creation_times(kind):
    async with _creator_pages(kind) as (client, expected, total, status):
        url = f"/api/v1/admin/creator-partnership/{kind}"
        observed = []
        for offset in (0, 2, 4):
            response = await client.get(url, params={"status": status, "limit": 2, "offset": offset})
            assert response.status_code == 200, response.text
            page = response.json()
            ids = [item["id"] for item in page["items"]]
            assert ids == expected[offset:offset + 2]
            assert page["total"] == total
            assert page["limit"] == 2 and page["offset"] == offset
            assert all(item["status"] == status for item in page["items"])
            observed.extend(ids)
        assert observed == expected
        assert len(set(observed)) == 6
        repeated = await client.get(url, params={"status": status, "limit": 2, "offset": 2})
        assert [item["id"] for item in repeated.json()["items"]] == expected[2:4]
