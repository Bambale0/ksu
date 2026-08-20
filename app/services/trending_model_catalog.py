from __future__ import annotations

from typing import Any

from app.services import model_catalog as catalog

# Product-selection baseline imported from Bambale0/banano_kling:tanyapi on
# 2026-08-20. KSU keeps its stricter provider adapters and current callable Kie
# contracts; this list controls which products are offered for NEW customer work.
# Historical specs remain registered so old generation rows can still be rendered
# and provider snapshots can still be reconciled without silently remapping them.
TRENDING_PUBLIC_MODEL_ORDER: tuple[str, ...] = (
    # Photo — mirrors Tanya's current Mini App choices, adapted to KSU's split
    # T2I/I2I runtime products where one Tanya card covers both operations.
    "nano-banana-2-lite",
    "seedream-5-pro-t2i",
    "seedream-5-pro-i2i",
    "nano-banana-pro",
    "nano-banana-2",
    "seedream-4.5-edit",
    "gpt-image-2-t2i",
    "gpt-image-2-i2i",
    "wan-2.7-image-pro",
    "grok-image-i2i",

    # Video — Tanya's current trend set plus Seedance 2.5, which is already a
    # current, provider-verified KSU contract and is present in Tanya's capability
    # registry as an admin preview. One KSU product can expose several Tanya
    # variants through server-driven fields (for example Veo 3.1 and Kling 3.0).
    "kling-3.0",
    "kling-2.5-turbo-pro-t2v",
    "kling-2.5-turbo-pro-i2v",
    "grok-video-i2v",
    "grok-video-1.5",
    "seedance-2.0",
    "seedance-2.5",
    "gemini-omni-video",
    "veo-3.1",
    "kling-motion-2.6",
    "kling-motion-3.0",
    "kling-avatar-standard",
    "kling-avatar-pro",
)

TRENDING_PUBLIC_MODEL_IDS = frozenset(TRENDING_PUBLIC_MODEL_ORDER)

# Current result-follow-up operations are intentionally callable but are not
# top-level model-picker products. They operate on an existing provider task.
CURRENT_UTILITY_MODEL_IDS = frozenset(
    {
        "grok-video-upscale",
        "grok-video-extend",
    }
)

ACTIVE_NEW_WORK_MODEL_IDS = TRENDING_PUBLIC_MODEL_IDS | CURRENT_UTILITY_MODEL_IDS


def is_trending_public_model(model_id: str) -> bool:
    return str(model_id) in TRENDING_PUBLIC_MODEL_IDS


def is_active_new_work_model(model_id: str) -> bool:
    return str(model_id) in ACTIVE_NEW_WORK_MODEL_IDS


def install_trending_model_catalog() -> None:
    """Expose Tanya's trend set while preserving read/recovery compatibility.

    `ModelCatalog.get()` deliberately remains an internal/history lookup over all
    registered specs. `list()` is the customer catalog. `prepare()` is the new-work
    admission boundary, so a removed legacy ID cannot be quoted/debited/submitted
    even if an old client still knows that identifier.
    """

    if getattr(catalog.ModelCatalog, "_trending_catalog_installed", False):
        return

    original_prepare = catalog.ModelCatalog.prepare

    @classmethod
    def list_trending(cls) -> list[dict[str, Any]]:  # noqa: ARG001
        models: list[dict[str, Any]] = []
        for model_id in TRENDING_PUBLIC_MODEL_ORDER:
            try:
                spec = catalog.ModelCatalog.get(model_id)
            except catalog.UnknownModelError:
                # Current-provider extensions are installed before this module.
                # Fail closed here rather than leaking an unrelated legacy model.
                continue
            models.append(spec.public_dict())
        return models

    @classmethod
    def prepare_active(
        cls,  # noqa: ARG001
        model_id: str,
        parameters: dict[str, Any],
        *,
        billing_seconds: int | None = None,
    ):
        if model_id not in ACTIVE_NEW_WORK_MODEL_IDS:
            raise catalog.UnknownModelError(f"Inactive generation model: {model_id}")
        return original_prepare(
            model_id,
            parameters,
            billing_seconds=billing_seconds,
        )

    catalog.ModelCatalog.list = list_trending
    catalog.ModelCatalog.prepare = prepare_active
    catalog.ModelCatalog.is_trending_public = staticmethod(is_trending_public_model)
    catalog.ModelCatalog.is_active_new_work = staticmethod(is_active_new_work_model)
    catalog.ModelCatalog._trending_catalog_installed = True
