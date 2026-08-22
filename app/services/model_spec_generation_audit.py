from __future__ import annotations

from typing import Any

_INSTALLED = False


def install_model_spec_generation_audit() -> None:
    """Remove obsolete bypasses and freeze only target-model provider fields."""

    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    from app.services.generations import GenerationService

    # Older Seedance 2 docs were interpreted as permitting temporal frames plus
    # multimodal references. The current Kie forms explicitly make these modes
    # mutually exclusive. Returning an empty stash lets ModelCatalog validate the
    # user's exact request before quote/debit instead of hiding refs temporarily.
    GenerationService._seedance20_hybrid_references = staticmethod(
        lambda model_id, parameters: {}
    )

    previous_prepare_request = GenerationService.prepare_request

    @classmethod
    async def audited_prepare_request(
        cls: type[GenerationService],
        session: Any,
        *,
        model_id: str,
        prompt: str,
        input_url: str | None = None,
        parameters: dict[str, Any] | None = None,
        billing_seconds: int | None = None,
    ):
        spec, clean, cost_rox, seconds, unit_price = await previous_prepare_request(
            session,
            model_id=model_id,
            prompt=prompt,
            input_url=input_url,
            parameters=parameters,
            billing_seconds=billing_seconds,
        )

        # ModelCatalog historically preserved arbitrary non-internal keys. That is
        # unsafe for auto-routing and old drafts: a field valid for the requested
        # product can be invalid for the resolved provider contract and otherwise
        # reach Kie's createTask after the wallet debit. Freeze only fields the
        # resolved ModelSpec declares. Historical queued generations are untouched.
        allowed = set(spec.known_fields)
        clean = {key: value for key, value in clean.items() if key in allowed}
        return spec, clean, cost_rox, seconds, unit_price

    GenerationService.prepare_request = audited_prepare_request
