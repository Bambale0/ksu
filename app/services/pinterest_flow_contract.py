from __future__ import annotations

from typing import Any, Iterable

PINTEREST_SERVICE_TAGS = frozenset({"pinterest", "pinterest-repeat", "repeat-pinterest"})
PINTEREST_MIN_REFERENCES = 2
PINTEREST_MAX_REFERENCES = 7
PINTEREST_MIN_HEIGHT_CM = 120
PINTEREST_MAX_HEIGHT_CM = 230
PINTEREST_MIN_WEIGHT_KG = 30
PINTEREST_MAX_WEIGHT_KG = 250


class PinterestFlowError(ValueError):
    pass


def _clean_tags(value: Any) -> set[str]:
    if not isinstance(value, (list, tuple, set, frozenset)):
        return set()
    return {str(item or "").strip().lower() for item in value if str(item or "").strip()}


def is_pinterest_trend(title: str, payload: dict[str, Any] | None) -> bool:
    clean_title = str(title or "").strip().lower()
    tags = _clean_tags((payload or {}).get("tags"))
    return "pinterest" in clean_title or bool(tags.intersection(PINTEREST_SERVICE_TAGS))


def validate_pinterest_flow(
    *,
    reference_urls: Iterable[str],
    height_cm: int,
    weight_kg: int,
    confirmed: bool,
) -> list[str]:
    refs = [str(url or "").strip() for url in reference_urls if str(url or "").strip()]
    if not PINTEREST_MIN_REFERENCES <= len(refs) <= PINTEREST_MAX_REFERENCES:
        raise PinterestFlowError(
            f"Pinterest Flow requires {PINTEREST_MIN_REFERENCES}..{PINTEREST_MAX_REFERENCES} reference images"
        )
    if len(set(refs)) != len(refs):
        raise PinterestFlowError("Pinterest Flow reference images must be unique")
    if not PINTEREST_MIN_HEIGHT_CM <= int(height_cm) <= PINTEREST_MAX_HEIGHT_CM:
        raise PinterestFlowError(
            f"Height must be between {PINTEREST_MIN_HEIGHT_CM} and {PINTEREST_MAX_HEIGHT_CM} cm"
        )
    if not PINTEREST_MIN_WEIGHT_KG <= int(weight_kg) <= PINTEREST_MAX_WEIGHT_KG:
        raise PinterestFlowError(
            f"Weight must be between {PINTEREST_MIN_WEIGHT_KG} and {PINTEREST_MAX_WEIGHT_KG} kg"
        )
    if confirmed is not True:
        raise PinterestFlowError("Pinterest Flow requires confirmation that the identity references belong to the user")
    return refs


def build_pinterest_prompt(
    base_prompt: str,
    *,
    height_cm: int,
    weight_kg: int,
    reference_count: int,
) -> str:
    extra_count = max(0, int(reference_count) - 2)
    return (
        "PINTEREST FLOW — STRICT REFERENCE ROLE CONTRACT.\n"
        "Image 1 is SCENE REFERENCE only: preserve its composition, camera angle, pose, crop, lighting, "
        "environment, wardrobe concept and overall visual direction. Never copy the identity from Image 1.\n"
        "Image 2 is PRIMARY IDENTITY REFERENCE: use this person's face, body identity and stable appearance "
        "as the identity master for the generated subject.\n"
        f"Images 3..{reference_count} are SUPPORTING IDENTITY ANGLES ({extra_count} supplied): use them only "
        "to resolve the same person's facial/body geometry and appearance across angles. They must not replace "
        "the scene, pose or composition from Image 1.\n"
        f"User anthropometrics: height {int(height_cm)} cm; weight {int(weight_kg)} kg. Respect realistic body "
        "proportions consistent with these values without exaggeration.\n"
        "Priority order: scene/composition from Image 1; identity from Image 2 plus supporting identity angles; "
        "then the curated trend instructions below. Do not merge identities and do not treat Image 1 as an identity reference.\n\n"
        "CURATED TREND INSTRUCTIONS:\n"
        f"{str(base_prompt or '').strip()}"
    ).strip()
