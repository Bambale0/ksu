from __future__ import annotations

import uuid
from typing import Any

_INSTALLED = False


def install_model_spec_reference_size_audit() -> None:
    """Reject oversized product-owned references before wallet debit."""

    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    from app.services.generations import GenerationService
    from app.services.model_routing import resolve_model_request
    from app.services.reference_size_contract import validate_owned_reference_sizes

    previous_create = GenerationService.create

    @classmethod
    async def audited_create(
        cls: type[GenerationService],
        session: Any,
        redis: Any,
        *,
        user_id: uuid.UUID,
        model_id: str,
        prompt: str = "",
        input_url: str | None = None,
        parameters: dict[str, Any] | None = None,
        billing_seconds: int | None = None,
        source_feed_gen_id: uuid.UUID | None = None,
        parent_generation_id: uuid.UUID | None = None,
        action_type: str | None = None,
    ):
        routed = resolve_model_request(model_id, parameters or {}, input_url=input_url)
        await validate_owned_reference_sizes(
            session,
            user_id=user_id,
            spec=routed.spec,
            parameters=routed.parameters,
        )
        return await previous_create(
            session,
            redis,
            user_id=user_id,
            model_id=model_id,
            prompt=prompt,
            input_url=input_url,
            parameters=parameters,
            billing_seconds=billing_seconds,
            source_feed_gen_id=source_feed_gen_id,
            parent_generation_id=parent_generation_id,
            action_type=action_type,
        )

    GenerationService.create = audited_create
