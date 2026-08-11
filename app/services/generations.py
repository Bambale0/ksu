import json
import uuid
from decimal import Decimal
from typing import Any

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Generation
from app.services.wallet import WalletService


class GenerationService:
    QUEUE_KEY = "queue:generations"
    PRICES = {
        "text_to_image": Decimal("10"),
        "image_to_image": Decimal("15"),
        "text_to_video": Decimal("50"),
        "image_to_video": Decimal("60"),
    }

    @classmethod
    def price_for(cls, kind: str) -> Decimal:
        try:
            return cls.PRICES[kind]
        except KeyError as exc:
            raise ValueError(f"Unsupported generation kind: {kind}") from exc

    @classmethod
    async def create(
        cls,
        session: AsyncSession,
        redis: Redis,
        *,
        user_id: uuid.UUID,
        kind: str,
        prompt: str,
        cost_rox: Decimal,
        input_url: str | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> Generation:
        generation = Generation(
            user_id=user_id,
            kind=kind,
            prompt=prompt,
            input_url=input_url,
            cost_rox=cost_rox,
            parameters=parameters or {},
            status="queued",
        )
        session.add(generation)
        await session.flush()

        await WalletService.debit(
            session,
            user_id=user_id,
            amount=cost_rox,
            kind="generation",
            reference_type="generation",
            reference_id=str(generation.id),
            idempotency_key=f"generation:{generation.id}:charge",
        )
        await session.commit()

        payload = json.dumps({"generation_id": str(generation.id)}, separators=(",", ":"))
        await redis.rpush(cls.QUEUE_KEY, payload)
        return generation
