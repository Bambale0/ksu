"""Verified providers resolve to one wallet, never silently merge accounts."""
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.db.models import Wallet
from app.db.session import SessionFactory
from app.services.wallet import WalletService
from app.services.web_identity import verified_telegram_identity, verified_web_identity


@pytest.mark.asyncio
async def test_verified_email_and_telegram_reuse_one_canonical_wallet():
    email = f"{uuid4().hex}@example.test"
    telegram = {"id": 900_000_000_000 + uuid4().int % 10_000_000_000, "first_name": "QA"}
    async with SessionFactory() as session:
        user = await verified_web_identity(
            session, provider="email", subject=email, display_name="QA", display_email=email,
        )
        owner = user.id
        assert user.telegram_id is None
        await WalletService.credit(
            session, user_id=owner, amount=Decimal("40"), kind="test_credit",
            reference_type="test", reference_id=str(owner), idempotency_key=f"web-test:{owner}",
        )
        await session.commit()
        linked = await verified_telegram_identity(session, verified_user=telegram, link_user_id=owner)
        assert linked.id == owner
        assert (await verified_telegram_identity(session, verified_user=telegram)).id == owner
        assert (await verified_web_identity(
            session, provider="email", subject=email, display_name="QA", display_email=email,
        )).id == owner
        wallet = await session.get(Wallet, owner)
        assert wallet is not None and wallet.balance == Decimal("40.00")


@pytest.mark.asyncio
async def test_identity_collision_does_not_merge_two_wallets():
    emails = [f"{uuid4().hex}@example.test" for _ in range(2)]
    async with SessionFactory() as session:
        users = [
            await verified_web_identity(
                session, provider="email", subject=email, display_name="QA", display_email=email,
            )
            for email in emails
        ]
        assert users[0].id != users[1].id
        with pytest.raises(HTTPException) as conflict:
            await verified_web_identity(
                session, provider="email", subject=emails[0], display_name="QA",
                display_email=emails[0], link_user_id=users[1].id,
            )
        assert conflict.value.status_code == 409
        assert (await session.get(Wallet, users[0].id)).balance == Decimal("0.00")
        assert (await session.get(Wallet, users[1].id)).balance == Decimal("0.00")
