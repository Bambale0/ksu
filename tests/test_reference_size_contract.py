import random
from decimal import Decimal

import pytest

from app.db.models import User, Wallet
from app.db.reference_models import UserReference
from app.db.session import SessionFactory
from app.services.generations import GenerationService
from app.services.model_catalog import InvalidModelParametersError
from app.services.wallet import WalletService


class UnexpectedRedis:
    async def eval(self, *_args: object, **_kwargs: object) -> list[int]:
        raise AssertionError("oversized owned references must fail before Redis admission")


@pytest.mark.asyncio
async def test_owned_oversized_reference_is_rejected_before_wallet_debit() -> None:
    async with SessionFactory() as session:
        user = User(
            telegram_id=random.randint(11_000_000_000_000, 11_999_999_999_999),
            first_name="Oversized reference",
        )
        session.add(user)
        await session.flush()
        await WalletService.ensure_wallet(session, user.id)
        await WalletService.credit(
            session,
            user_id=user.id,
            amount=Decimal("100"),
            kind="test_credit",
            idempotency_key=f"reference-size-credit:{user.id}",
        )

        source_url = f"https://cdn.example.invalid/references/{user.id}.png"
        session.add(
            UserReference(
                user_id=user.id,
                kind="image",
                status="ready",
                source_url=source_url,
                source="upload",
                size_bytes=30 * 1024 * 1024 + 1,
            )
        )
        await session.commit()

        with pytest.raises(
            InvalidModelParametersError,
            match=r"image_input reference exceeds 30 MB",
        ):
            await GenerationService.create(
                session,
                UnexpectedRedis(),  # type: ignore[arg-type]
                user_id=user.id,
                model_id="nano-banana-pro",
                prompt="edit this reference",
                parameters={"image_input": [source_url]},
            )

        wallet = await session.get(Wallet, user.id)
        assert wallet is not None
        assert wallet.balance == Decimal("100.00")
