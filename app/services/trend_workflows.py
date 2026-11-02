from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from decimal import Decimal
from typing import Any
from urllib.parse import urlsplit

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.admin_models import AdminTrend
from app.db.media_models import MediaAsset
from app.db.models import Generation
from app.db.trend_workflow_models import TrendWorkflowRun, TrendWorkflowStep
from app.services.aspect_ratio_policy import (
    explicit_aspect_ratio_options,
    is_auto_aspect_ratio,
    requires_explicit_aspect_ratio,
    validate_generation_aspect_ratio,
)
from app.services.billing_access import BillingAccessService
from app.services.credits import InternalCreditService
from app.services.generations import GenerationService
from app.services.media_assets import MediaAssetService, MediaIngestError
from app.services.trend_user_fields import TrendUserFieldSpec, validate_trend_field_value
from app.services.model_capability import ModelCapabilityResolver, MODE_IMAGE_TO_VIDEO
from app.services.model_catalog import ModelCatalog, ModelSpec
from app.core.observability import WORKFLOW_EVENTS

logger = logging.getLogger(__name__)


class TrendWorkflowError(ValueError):
    pass


class TrendWorkflowConflict(TrendWorkflowError):
    pass


_SLOT_TYPES = {"image", "text", "number", "date", "select"}
_BINDABLE_FIELDS = {
    "first_frame_url",
    "first_frame",
    "reference_image",
    "reference_image_urls",
    "image_input",
    "image_urls",
    "input_urls",
}
_IMAGE_FIELDS = ("image_input", "image_urls", "input_urls", "reference_image_urls", "reference_image", "first_frame_url", "first_frame")
_IMAGE_TAG = re.compile(r"@Image(\d+)", re.IGNORECASE)
_WORKFLOW_MEDIA_PREFIX = "ksu-media://"
WORKFLOW_PRICING_SOURCE = "generation_service_catalog"


def _amount(value: Decimal | int | float | str) -> str:
    return format(Decimal(str(value)), ".2f")


def _hash_payload(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _safe_url(value: Any, *, field: str) -> str:
    url = str(value or "").strip()
    parsed = urlsplit(url)
    if not url or len(url) > 4000 or parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise TrendWorkflowError(f"{field} must be a valid HTTP(S) URL")
    return url


def _reference_field(spec: ModelSpec) -> str | None:
    for field in _IMAGE_FIELDS:
        if field in set(spec.known_fields):
            return field
    return None


def _validate_prompt_tags(prompt: str) -> None:
    values = [int(value) for value in _IMAGE_TAG.findall(prompt)]
    if not values:
        return
    expected = list(range(1, max(values) + 1))
    if sorted(set(values)) != expected:
        raise TrendWorkflowError("@ImageN references must be numbered consecutively from @Image1")


def _workflow_media_ref(asset_id: uuid.UUID) -> str:
    return f"{_WORKFLOW_MEDIA_PREFIX}{asset_id}"


def _normalize_slot(raw: Any, *, expected_order: int) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise TrendWorkflowError("Workflow input slots must be objects")
    slot_id = str(raw.get("id") or "").strip()
    label = str(raw.get("label") or "").strip()
    help_text = str(raw.get("help") or "").strip()
    slot_type = str(raw.get("type") or "").strip().lower()
    if not slot_id or not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_-]{0,63}", slot_id):
        raise TrendWorkflowError("Workflow input slot id is invalid")
    if not label or not help_text or len(label) > 120 or len(help_text) > 500:
        raise TrendWorkflowError("Workflow input slot label/help is invalid")
    if slot_type not in _SLOT_TYPES:
        raise TrendWorkflowError("Workflow input slot type is invalid")
    try:
        order = int(raw.get("order"))
    except (TypeError, ValueError) as exc:
        raise TrendWorkflowError("Workflow input slot order is invalid") from exc
    if order != expected_order:
        raise TrendWorkflowError("Workflow input slots must use contiguous order values")
    raw_options = raw.get("options")
    options: list[str] = []
    if slot_type == "select":
        if not isinstance(raw_options, list) or not raw_options:
            raise TrendWorkflowError("Select workflow slots require options")
        options = [str(value).strip() for value in raw_options]
        if any(not value or len(value) > 120 for value in options) or len(set(options)) != len(options):
            raise TrendWorkflowError("Workflow select options are invalid")
    elif raw_options not in (None, []):
        raise TrendWorkflowError("Only select workflow slots may define options")
    return {
        "id": slot_id,
        "label": label,
        "help": help_text,
        "type": slot_type,
        "required": bool(raw.get("required", False)),
        "order": order,
        "options": options,
    }


def _log_lifecycle(event: str, *, workflow_id: uuid.UUID | None = None, step_id: str | None = None,
                   generation_id: uuid.UUID | None = None, request_id: str | None = None,
                   attempt: int | None = None, status: str | None = None,
                   failure_category: str | None = None) -> None:
    safe = {
        "event": event,
        "workflow_id": str(workflow_id) if workflow_id else None,
        "step_id": step_id,
        "generation_id": str(generation_id) if generation_id else None,
        "request_id": request_id,
        "attempt": attempt,
        "status": status,
        "failure_category": failure_category,
    }
    logger.info("trend_workflow_lifecycle %s", {key: value for key, value in safe.items() if value is not None})
    WORKFLOW_EVENTS.labels(event=event, status=status or "unknown", failure_category=failure_category or "none").inc()


class TrendWorkflowService:
    """Durable owner-scoped orchestration for versioned photo -> video trends."""

    @staticmethod
    def merge_admin_payload(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
        """Preserve v2 recipe structure for metadata-only admin edits."""
        if int(existing.get("schema_version", 1) or 1) != 2:
            return dict(incoming)
        if "schema_version" in incoming and int(incoming.get("schema_version") or 0) != 2:
            raise TrendWorkflowError("v2 workflow recipes cannot be downconverted")
        if "workflow_type" in incoming and incoming["workflow_type"] != existing.get("workflow_type"):
            raise TrendWorkflowError("v2 workflow type cannot be changed by metadata editing")
        # PATCH clients may echo their schema marker without resending hidden
        # steps. Preserve every omitted field; explicit steps are still validated.
        return {**existing, **incoming, "schema_version": 2}

    @classmethod
    def normalize_recipe(cls, title: str, payload: dict[str, Any]) -> dict[str, Any]:
        clean_title = str(title or "").strip()
        if not clean_title or len(clean_title) > 80:
            raise TrendWorkflowError("Trend title must contain 1..80 characters")
        if int(payload.get("schema_version", 0) or 0) != 2:
            raise TrendWorkflowError("Workflow recipes require schema_version=2")
        if str(payload.get("workflow_type") or "") != "sequential_photo_video":
            raise TrendWorkflowError("Unsupported workflow_type")
        preview_url = payload.get("preview_url")
        normalized_preview = _safe_url(preview_url, field="preview_url") if preview_url else None
        raw_steps = payload.get("steps")
        if not isinstance(raw_steps, list) or len(raw_steps) != 2:
            raise TrendWorkflowError("Sequential photo/video workflows require exactly two steps")

        normalized_steps: list[dict[str, Any]] = []
        ids: set[str] = set()
        for index, raw_step in enumerate(raw_steps):
            if not isinstance(raw_step, dict):
                raise TrendWorkflowError("Workflow steps must be objects")
            step_id = str(raw_step.get("id") or "").strip()
            kind = str(raw_step.get("kind") or "").strip().lower()
            if not step_id or not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_-]{0,63}", step_id) or step_id in ids:
                raise TrendWorkflowError("Workflow step id is invalid or duplicated")
            ids.add(step_id)
            expected_kind = "image" if index == 0 else "video"
            if kind != expected_kind:
                raise TrendWorkflowError("image step must precede video step")
            model_id = str(raw_step.get("model_id") or "").strip()
            spec = ModelCatalog.get(model_id)
            if spec.media_type != kind:
                raise TrendWorkflowError("Workflow step model media type does not match step kind")
            if index == 1 and (
                not ModelCapabilityResolver.supports(spec, MODE_IMAGE_TO_VIDEO)
                or not ModelCapabilityResolver.supports_input(spec, "image")
            ):
                raise TrendWorkflowError("The video step model is not image-to-video capable")
            prompt = str(raw_step.get("prompt") or "").strip()
            if not prompt or len(prompt) > 8000:
                raise TrendWorkflowError("Workflow step prompt must contain 1..8000 characters")
            _validate_prompt_tags(prompt)
            parameters = raw_step.get("parameters") or {}
            if not isinstance(parameters, dict):
                raise TrendWorkflowError("Workflow step parameters must be an object")
            inputs = raw_step.get("inputs") or []
            if not isinstance(inputs, list) or len(inputs) > 16:
                raise TrendWorkflowError("Workflow step inputs must be an array of at most 16 slots")
            slots = [_normalize_slot(value, expected_order=slot_order) for slot_order, value in enumerate(inputs)]
            if len({slot["id"] for slot in slots}) != len(slots):
                raise TrendWorkflowError("Workflow input slot ids must be unique")
            image_slots = [slot for slot in slots if slot["type"] == "image"]
            image_input_mode = (
                "semantic"
                if len(image_slots) > 1
                or any(not slot["required"] for slot in image_slots)
                or [slot["order"] for slot in image_slots] != list(range(len(image_slots)))
                else "ordered"
            )
            normalized: dict[str, Any] = {
                "id": step_id,
                "kind": kind,
                "title": str(raw_step.get("title") or step_id).strip()[:120],
                "instructions": str(raw_step.get("instructions") or "").strip()[:2000],
                "preview_url": (
                    _safe_url(raw_step["preview_url"], field="step preview_url")
                    if raw_step.get("preview_url")
                    else None
                ),
                "model_id": spec.id,
                "model_title": spec.title,
                "prompt": prompt,
                "parameters": dict(parameters),
                "inputs": slots,
                "image_input_mode": image_input_mode,
                "pricing_source": WORKFLOW_PRICING_SOURCE,
            }
            if index == 1:
                raw_bindings = raw_step.get("bindings")
                if not isinstance(raw_bindings, list) or len(raw_bindings) != 1:
                    raise TrendWorkflowError("The video step requires one explicit image output binding")
                binding = raw_bindings[0]
                if not isinstance(binding, dict):
                    raise TrendWorkflowError("Workflow binding must be an object")
                source = str(binding.get("from") or "").strip()
                target = str(binding.get("to") or "").strip()
                if source != f"{normalized_steps[0]['id']}.output_image":
                    raise TrendWorkflowError("Workflow binding must reference step 1 output_image")
                if target not in _BINDABLE_FIELDS or target not in set(spec.known_fields):
                    raise TrendWorkflowError("Workflow binding target is not a supported model image field")
                normalized["bindings"] = [{"from": source, "to": target}]
            image_tags = [int(value) for value in _IMAGE_TAG.findall(prompt)]
            if image_tags:
                expected_tags = list(range(1, (1 if index == 1 else len(image_slots)) + 1))
                if sorted(set(image_tags)) != expected_tags:
                    raise TrendWorkflowError("@ImageN must match the ordered image input slots")
                if any(not slot["required"] for slot in image_slots):
                    first_optional = next(index for index, slot in enumerate(image_slots) if not slot["required"])
                    if any(slot["required"] for slot in image_slots[first_optional + 1:]):
                        raise TrendWorkflowError("optional image slots cannot precede required image slots")
            normalized_steps.append(normalized)

        return {
            "schema_version": 2,
            "workflow_type": "sequential_photo_video",
            "title": clean_title,
            "description": str(payload.get("description") or "").strip()[:240],
            "preview_url": normalized_preview,
            "tags": [str(value).strip().lower() for value in (payload.get("tags") or []) if str(value).strip()][:20],
            "sort_order": int(payload.get("sort_order", 0)),
            "usage_count": max(0, int(payload.get("usage_count", 0))),
            "pricing_source": WORKFLOW_PRICING_SOURCE,
            "steps": normalized_steps,
        }

    @classmethod
    async def validate_recipe(cls, session: AsyncSession, recipe: dict[str, Any]) -> dict[str, Any]:
        for index, step in enumerate(recipe["steps"]):
            spec = ModelCatalog.get(step["model_id"])
            parameters = dict(step["parameters"])
            ref_count = sum(1 for slot in step["inputs"] if slot["type"] == "image")
            if ref_count:
                field = _reference_field(spec)
                if field is None:
                    raise TrendWorkflowError("Image input slot is not supported by the selected model")
                refs = [f"https://example.invalid/workflow-{index + 1}-image-{n}.jpg" for n in range(ref_count)]
                parameters[field] = refs if field.endswith("urls") or field in {"image_input", "image_urls", "input_urls"} else refs[0]
            if index == 1:
                target = recipe["steps"][1]["bindings"][0]["to"]
                parameters[target] = ["https://example.invalid/workflow-step-1.jpg"] if target.endswith("urls") or target in {"image_input", "image_urls", "input_urls"} else "https://example.invalid/workflow-step-1.jpg"
            try:
                await GenerationService.prepare_template_request(
                    session,
                    model_id=spec.id,
                    prompt=step["prompt"],
                    parameters=parameters,
                    billing_seconds=parameters.get(spec.duration_field) if spec.duration_field else None,
                )
            except ValueError as exc:
                raise TrendWorkflowError(f"Workflow step {index + 1} is invalid: {exc}") from exc
        return recipe

    @classmethod
    async def public_trend_view(
        cls,
        session: AsyncSession,
        item: AdminTrend,
        recipe: dict[str, Any],
    ) -> dict[str, Any]:
        steps = []
        for step in recipe["steps"]:
            public_references = [
                f"https://example.invalid/workflow-public-image-{index + 1}.jpg"
                for index, slot in enumerate(step["inputs"])
                if slot["type"] == "image"
            ]
            # Catalog estimates must validate without requiring actual customer
            # values. These synthetic placeholders never enter a paid request.
            placeholder_values = {}
            for slot in step["inputs"]:
                if slot["type"] == "image" or not slot["required"]:
                    continue
                placeholder_values[slot["id"]] = (
                    "1" if slot["type"] == "number" else
                    "2000-01-01" if slot["type"] == "date" else
                    slot["options"][0] if slot["type"] == "select" else "Preview"
                )
            quote_request: dict[str, Any] = {"values": placeholder_values}
            if step.get("image_input_mode") == "semantic":
                quote_request["image_inputs"] = [
                    {"slot_id": slot["id"], "url": url}
                    for slot, url in zip(
                        [slot for slot in step["inputs"] if slot["type"] == "image"],
                        public_references,
                    )
                ]
            else:
                quote_request["reference_urls"] = public_references
            quote = await cls.quote_for_step(
                session,
                recipe,
                step,
                user_id=None,
                request=quote_request,
                check_ready=False,
                structural_preflight=True,
            )
            steps.append({
                "id": step["id"],
                "kind": step["kind"],
                "title": step["title"],
                "instructions": step["instructions"],
                "inputs": step["inputs"],
                **cls._step_presentation(step),
                "quote": quote,
            })
        first_quote = steps[0]["quote"]
        return {
            "id": str(item.id),
            "title": item.title,
            "description": recipe["description"],
            "media_type": "video",
            "preview_url": recipe["preview_url"],
            "workflow_type": recipe["workflow_type"],
            "pricing_source": recipe["pricing_source"],
            "steps": steps,
            "cost_credits": first_quote["cost_credits"],
            "cost_rub": first_quote["cost_rub"],
            "reference_requirements": {"kind": "workflow", "min": 0, "max": 16},
            "tags": recipe["tags"],
            "usage_count": recipe["usage_count"],
            "sort_order": recipe["sort_order"],
            "prompt_hidden": True,
            "prompt_actions_allowed": False,
            "created_at": item.created_at.isoformat(),
        }

    @classmethod
    async def create_or_resume(
        cls,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        trend_id: uuid.UUID,
        command_key: str,
        request: dict[str, Any],
        request_id: str | None = None,
    ) -> TrendWorkflowRun:
        request_hash = _hash_payload(request)
        existing = await session.scalar(
            select(TrendWorkflowRun).where(
                TrendWorkflowRun.user_id == user_id,
                TrendWorkflowRun.trend_id == trend_id,
                TrendWorkflowRun.command_key == command_key,
            )
        )
        if existing is not None:
            if existing.request_hash != request_hash:
                raise TrendWorkflowConflict("Idempotency key was already used with a different request")
            return existing

        item = await session.scalar(select(AdminTrend).where(AdminTrend.id == trend_id, AdminTrend.is_active.is_(True)))
        if item is None:
            raise LookupError("Trend not found")
        recipe = cls.normalize_recipe(item.title, item.payload or {})
        if recipe["schema_version"] != 2:
            raise TrendWorkflowError("This trend is a legacy one-step recipe")
        await cls.validate_recipe(session, recipe)

        locked = await session.scalar(select(AdminTrend).where(AdminTrend.id == trend_id).with_for_update())
        if locked is None or not locked.is_active:
            raise LookupError("Trend not found")
        # Freeze the definition while its publication row is locked. Opening a
        # resumable state is not a generation and must not inflate usage counts.
        recipe = cls.normalize_recipe(locked.title, locked.payload or {})
        await cls.validate_recipe(session, recipe)
        run = TrendWorkflowRun(
            id=uuid.uuid4(),
            user_id=user_id,
            trend_id=trend_id,
            recipe_version=2,
            recipe_snapshot=recipe,
            status="created",
            command_key=command_key,
            request_hash=request_hash,
            usage_incremented=False,
        )
        session.add(run)
        for ordinal, step in enumerate(recipe["steps"]):
            session.add(
                TrendWorkflowStep(
                    id=uuid.uuid4(),
                    workflow_id=run.id,
                    step_key=step["id"],
                    ordinal=ordinal,
                    kind=step["kind"],
                    status="pending",
                )
            )
        _log_lifecycle("create", workflow_id=run.id, status=run.status, attempt=0, request_id=request_id)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            replay = await session.scalar(
                select(TrendWorkflowRun).where(
                    TrendWorkflowRun.user_id == user_id,
                    TrendWorkflowRun.trend_id == trend_id,
                    TrendWorkflowRun.command_key == command_key,
                )
            )
            if replay is None:
                raise TrendWorkflowConflict("Workflow start conflicted; retry with the same command key")
            if replay.request_hash != request_hash:
                raise TrendWorkflowConflict("Idempotency key was already used with a different request")
            return replay
        return run

    @staticmethod
    async def _owned_run(
        session: AsyncSession, *, run_id: uuid.UUID, user_id: uuid.UUID, lock: bool = False
    ) -> TrendWorkflowRun:
        statement = select(TrendWorkflowRun).where(
            TrendWorkflowRun.id == run_id, TrendWorkflowRun.user_id == user_id
        )
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        run = await session.scalar(statement)
        if run is None:
            raise LookupError("Workflow not found")
        return run

    @classmethod
    async def _owned_step(
        cls, session: AsyncSession, *, run_id: uuid.UUID, step_key: str, user_id: uuid.UUID, lock: bool = False
    ) -> tuple[TrendWorkflowRun, TrendWorkflowStep]:
        # A consistent run -> step lock order also serializes photo redo against
        # starting video, not just two requests for the same step.
        run = await cls._owned_run(session, run_id=run_id, user_id=user_id, lock=lock)
        statement = select(TrendWorkflowStep).where(
            TrendWorkflowStep.workflow_id == run.id,
            TrendWorkflowStep.step_key == step_key,
        )
        if lock:
            statement = statement.with_for_update()
        step = await session.scalar(statement)
        if step is None:
            raise LookupError("Workflow step not found")
        return run, step

    @classmethod
    async def _ready_step1_asset(
        cls, session: AsyncSession, *, run: TrendWorkflowRun, selected_asset_id: uuid.UUID | None = None
    ) -> MediaAsset:
        first_step = await session.scalar(
            select(TrendWorkflowStep).where(TrendWorkflowStep.workflow_id == run.id, TrendWorkflowStep.ordinal == 0)
        )
        if first_step is None or first_step.generation_id is None:
            raise TrendWorkflowError("Step 2 requires a completed photo generation")
        generation = await session.get(Generation, first_step.generation_id)
        if generation is None or generation.user_id != run.user_id or generation.status != "succeeded":
            raise TrendWorkflowError("Step 2 requires a completed photo generation")
        statement = select(MediaAsset).where(
            MediaAsset.user_id == run.user_id,
            MediaAsset.generation_id == generation.id,
            MediaAsset.status == "ready",
            MediaAsset.object_key.is_not(None),
            MediaAsset.bucket.is_not(None),
        )
        # An omitted source on retry must retain the photo the user reviewed.
        # If that asset is unavailable, fail closed rather than animate another
        # output with a different face, outfit or inscription.
        if selected_asset_id is None:
            selected_asset_id = first_step.media_asset_id
        if selected_asset_id is None:
            # Earlier workflow revisions recorded the reviewed source only on
            # the video step. Preserve that choice when resuming such a run.
            selected_asset_id = await session.scalar(
                select(TrendWorkflowStep.media_asset_id).where(
                    TrendWorkflowStep.workflow_id == run.id,
                    TrendWorkflowStep.ordinal == 1,
                )
            )
        if selected_asset_id is not None:
            statement = statement.where(MediaAsset.id == selected_asset_id)
        asset = await session.scalar(statement.order_by(MediaAsset.ordinal.asc()))
        if asset is None or not str(asset.content_type or "").lower().startswith("image/"):
            raise TrendWorkflowError("Step 2 requires a ready owned image")
        try:
            await MediaAssetService.verify_source_readable(asset)
        except MediaIngestError as exc:
            raise TrendWorkflowError("The prepared image is unavailable; restore it before starting video") from exc
        return asset

    @classmethod
    def _step_request(
        cls,
        recipe: dict[str, Any],
        step: dict[str, Any],
        request: dict[str, Any],
        *,
        input_url: str | None = None,
        structural_preflight: bool = False,
    ) -> tuple[str, dict[str, Any]]:
        values = request.get("values") or {}
        if not isinstance(values, dict):
            raise TrendWorkflowError("Workflow values must be an object")
        allowed = {slot["id"] for slot in step["inputs"]}
        if set(values) - allowed:
            raise TrendWorkflowError("Unknown workflow input slot")
        parameters = dict(step["parameters"])
        selected_ratio = request.get("aspect_ratio")
        if selected_ratio not in (None, ""):
            options = cls._step_aspect_ratio_options(step)
            if selected_ratio not in options:
                raise TrendWorkflowError("Unsupported aspect ratio")
            parameters["aspect_ratio"] = selected_ratio
        if not structural_preflight:
            try:
                validate_generation_aspect_ratio(step["model_id"], parameters)
            except ValueError as exc:
                raise TrendWorkflowError(str(exc)) from exc
        raw_image_inputs = request.get("image_inputs")
        if step["kind"] == "video" and (raw_image_inputs is not None or request.get("reference_urls")):
            raise TrendWorkflowError("Step 2 accepts only the selected ready workflow image")
        if raw_image_inputs is not None and request.get("reference_urls"):
            raise TrendWorkflowError("Use image_inputs or reference_urls, not both")
        image_urls = request.get("reference_urls") or []
        if not isinstance(image_urls, list):
            raise TrendWorkflowError("reference_urls must be an array")
        image_slots = [slot for slot in step["inputs"] if slot["type"] == "image"]
        if image_slots and step.get("image_input_mode") == "semantic" and raw_image_inputs is None:
            raise TrendWorkflowError("image_inputs with slot_id are required for this image layout")
        if raw_image_inputs is not None:
            if not isinstance(raw_image_inputs, list):
                raise TrendWorkflowError("image_inputs must be an array")
            by_id = {slot["id"]: slot for slot in image_slots}
            provided: dict[str, str] = {}
            for item in raw_image_inputs:
                if not isinstance(item, dict):
                    raise TrendWorkflowError("image_inputs must contain objects")
                slot_id = str(item.get("slot_id") or "").strip()
                if slot_id not in by_id or slot_id in provided:
                    raise TrendWorkflowError("image_inputs contains an unknown or duplicate slot")
                provided[slot_id] = _safe_url(item.get("url"), field="image_input.url")
            missing = [slot["id"] for slot in image_slots if slot["required"] and slot["id"] not in provided]
            if missing:
                raise TrendWorkflowError("Required workflow image inputs are missing")
            image_urls = [provided[slot["id"]] for slot in image_slots if slot["id"] in provided]
        else:
            image_urls = [_safe_url(url, field="reference_url") for url in image_urls]
        required_images = sum(1 for slot in image_slots if slot["required"])
        if len(image_urls) > len(image_slots) or len(image_urls) < required_images:
            raise TrendWorkflowError("Required workflow image inputs are missing")
        if len(image_urls) < len(image_slots) and any(
            slot["required"] for slot in image_slots[len(image_urls):]
        ):
            raise TrendWorkflowError("Optional image slots cannot silently shift ordered inputs")
        if image_urls:
            field = _reference_field(ModelCatalog.get(step["model_id"]))
            if field is None:
                raise TrendWorkflowError("Selected model does not accept image inputs")
            parameters[field] = image_urls if field.endswith("urls") or field in {"image_input", "image_urls", "input_urls"} else image_urls[0]
        validated: dict[str, str] = {}
        text_slots = [slot for slot in step["inputs"] if slot["type"] != "image"]
        for slot in text_slots:
            value = validate_trend_field_value(
                TrendUserFieldSpec(
                    key=slot["id"], label=slot["label"],
                    field_type="text" if slot["type"] == "select" else slot["type"],
                    required=slot["required"],
                ),
                values.get(slot["id"]),
            )
            if value and slot["type"] == "select" and value not in slot["options"]:
                raise TrendWorkflowError(f"Workflow input option is invalid: {slot['id']}")
            validated[slot["id"]] = value
        # Callable substitution never treats user backslashes as replacement
        # syntax and never expands a second placeholder inside the user's text.
        prompt = re.sub(
            r"\{\{([^{}]+)\}\}",
            lambda match: validated.get(match.group(1).strip(), match.group(0)),
            step["prompt"],
        )
        extra_values = [
            f"{slot['label']}: {validated[slot['id']]}"
            for slot in text_slots
            if validated[slot["id"]] and "{{" + slot["id"] + "}}" not in step["prompt"]
        ]
        if extra_values:
            prompt += "\n\nUser personalization:\n" + "\n".join(extra_values)
        if input_url is not None:
            binding = step.get("bindings") or []
            if len(binding) != 1:
                raise TrendWorkflowError("Workflow step has no valid output binding")
            target = binding[0]["to"]
            parameters[target] = [input_url] if target.endswith("urls") or target in {"image_input", "image_urls", "input_urls"} else input_url
        return prompt, parameters

    @classmethod
    async def quote_for_step(
        cls,
        session: AsyncSession,
        recipe: dict[str, Any],
        step: dict[str, Any],
        *,
        user_id: uuid.UUID | None,
        request: dict[str, Any],
        check_ready: bool,
        run: TrendWorkflowRun | None = None,
        structural_preflight: bool = False,
    ) -> dict[str, Any]:
        input_url = None
        if step["kind"] == "video":
            if check_ready and run is not None:
                asset = await cls._ready_step1_asset(session, run=run, selected_asset_id=request.get("media_asset_id"))
                input_url = _workflow_media_ref(asset.id)
            else:
                input_url = "https://example.invalid/workflow-step-1.jpg"
        prompt, parameters = cls._step_request(
            recipe, step, request, input_url=input_url,
            structural_preflight=structural_preflight,
        )
        prepare = (
            GenerationService.prepare_template_request
            if structural_preflight else GenerationService.prepare_request
        )
        _spec, _clean, retail, seconds, _unit = await prepare(
            session,
            model_id=step["model_id"],
            prompt=prompt,
            parameters=parameters,
            billing_seconds=None,
        )
        effective = retail
        admin_free = False
        if user_id is not None:
            decision = await BillingAccessService.decision(session, user_id=user_id, retail_cost=retail)
            effective = decision.effective_cost
            admin_free = decision.admin_free
        return {
            "cost_credits": _amount(effective),
            "cost_rox": _amount(effective),
            "cost_rub": _amount(InternalCreditService.rubles_for(effective)),
            "retail_cost_rox": _amount(retail),
            "admin_free": admin_free,
            "billing_seconds": seconds,
            "quoted_cost_rox": _amount(effective),
            "pricing_source": recipe.get("pricing_source", WORKFLOW_PRICING_SOURCE),
        }

    @classmethod
    async def quote_step(
        cls, session: AsyncSession, *, run_id: uuid.UUID, step_key: str, user_id: uuid.UUID,
        request: dict[str, Any], request_id: str | None = None,
    ) -> dict[str, Any]:
        run, _step_row = await cls._owned_step(session, run_id=run_id, step_key=step_key, user_id=user_id)
        recipe_step = next((step for step in run.recipe_snapshot["steps"] if step["id"] == step_key), None)
        if recipe_step is None:
            raise LookupError("Workflow step not found")
        quote = await cls.quote_for_step(session, run.recipe_snapshot, recipe_step, user_id=user_id, request=request, check_ready=recipe_step["kind"] == "video", run=run)
        _log_lifecycle("quote", workflow_id=run.id, step_id=step_key, request_id=request_id, status="quoted")
        return quote

    @staticmethod
    def _require_quoted_cost(request: dict[str, Any]) -> None:
        value = request.get("quoted_cost_rox")
        if value is None or str(value).strip() == "":
            raise TrendWorkflowError("quoted_cost_rox is required; request a fresh quote")
        try:
            amount = Decimal(str(value))
            if not amount.is_finite() or amount < 0:
                raise ValueError
        except (ArithmeticError, ValueError) as exc:
            raise TrendWorkflowError("quoted_cost_rox must be a non-negative amount") from exc

    @staticmethod
    async def _reconcile_reserved_generation(
        session: AsyncSession, *, run: TrendWorkflowRun, step: TrendWorkflowStep
    ) -> bool:
        reserved_id = getattr(step, "reserved_generation_id", None)
        if reserved_id is None or step.generation_id is not None:
            return True
        generation = await session.get(Generation, reserved_id)
        if generation is None:
            return False
        if generation.user_id != run.user_id:
            raise TrendWorkflowConflict("Generation reservation ownership could not be verified")
        step.generation_id = generation.id
        step.reserved_generation_id = None
        step.status = "failed" if generation.status == "failed" else "queued"
        if generation.status == "failed":
            step.last_error = generation.error
        await session.commit()
        return True

    @classmethod
    async def run_step(
        cls,
        session: AsyncSession,
        redis: Redis,
        *,
        run_id: uuid.UUID,
        step_key: str,
        user_id: uuid.UUID,
        command_key: str,
        request: dict[str, Any],
        request_id: str | None = None,
    ) -> TrendWorkflowStep:
        cls._require_quoted_cost(request)
        run, step_row = await cls._owned_step(session, run_id=run_id, step_key=step_key, user_id=user_id, lock=True)
        payload_hash = _hash_payload(request)
        if getattr(step_row, "reserved_generation_id", None) is not None and step_row.generation_id is None:
            if not await cls._reconcile_reserved_generation(session, run=run, step=step_row):
                raise TrendWorkflowConflict("A previous generation reservation is unresolved; reconcile it before retrying")
        if step_row.command_key == command_key:
            if step_row.payload_hash != payload_hash:
                raise TrendWorkflowConflict("Step idempotency key was already used with a different request")
            return step_row
        for previous in getattr(step_row, "attempt_history", None) or []:
            if isinstance(previous, dict) and previous.get("command_key") == command_key:
                if previous.get("payload_hash") != payload_hash:
                    raise TrendWorkflowConflict("Step idempotency key was already used with a different request")
                raise TrendWorkflowConflict("Cannot replay a previous attempt; use its stored result or a new retry key")
        existing_generation = (
            await session.get(Generation, step_row.generation_id)
            if step_row.generation_id is not None
            else None
        )
        if existing_generation is not None:
            if existing_generation.status in {"queued", "submitting", "generating", "retry"}:
                return step_row
            if existing_generation.status == "succeeded" and not request.get("retry"):
                return step_row
            if existing_generation.status == "failed":
                if request.get("retry") is not True:
                    raise TrendWorkflowConflict("A failed attempt requires explicit retry=true and a fresh quote")
                step_row.status = "failed"
                step_row.last_error = existing_generation.error
                await session.flush()
        recipe_step = next((step for step in run.recipe_snapshot["steps"] if step["id"] == step_key), None)
        if recipe_step is None:
            raise LookupError("Workflow step not found")
        if recipe_step["kind"] == "image" and request.get("retry"):
            next_step = await session.scalar(
                select(TrendWorkflowStep)
                .where(TrendWorkflowStep.workflow_id == run.id, TrendWorkflowStep.ordinal == 1)
                .with_for_update()
            )
            if next_step is not None and (next_step.generation_id is not None or next_step.status != "pending"):
                raise TrendWorkflowConflict("Photo redo conflicts with the existing video attempt")
        asset = None
        if recipe_step["kind"] == "video":
            asset = await cls._ready_step1_asset(session, run=run, selected_asset_id=request.get("media_asset_id"))
            # Persist the reviewed choice in the same transaction as the video
            # debit so reload/retry cannot switch back to the first image.
            photo_step = await session.scalar(
                select(TrendWorkflowStep).where(
                    TrendWorkflowStep.workflow_id == run.id, TrendWorkflowStep.ordinal == 0
                ).with_for_update()
            )
            if photo_step is None:
                raise TrendWorkflowConflict("Prepared photo step is unavailable")
            photo_step.media_asset_id = asset.id
        prompt, parameters = cls._step_request(
            run.recipe_snapshot,
            recipe_step,
            request,
            input_url=_workflow_media_ref(asset.id) if asset is not None else None,
        )
        generation_id = uuid.uuid4()
        history = list(getattr(step_row, "attempt_history", None) or [])
        if existing_generation is not None:
            history.append(
                {
                    "generation_id": str(existing_generation.id),
                    "command_key": step_row.command_key,
                    "payload_hash": step_row.payload_hash,
                    "status": existing_generation.status,
                    "attempt": step_row.attempts,
                    "media_asset_id": str(step_row.media_asset_id) if step_row.media_asset_id else None,
                }
            )
        step_row.attempt_history = history
        step_row.command_key = command_key
        step_row.payload_hash = payload_hash
        step_row.generation_id = None
        step_row.reserved_generation_id = generation_id
        step_row.media_asset_id = asset.id if recipe_step["kind"] == "video" and asset is not None else None
        step_row.status = "queued"
        step_row.attempts = max(0, step_row.attempts) + 1
        run.status = "running"
        await session.flush()
        try:
            generation = await GenerationService.create(
                session,
                redis,
                user_id=user_id,
                model_id=recipe_step["model_id"],
                prompt=prompt,
                parameters=parameters,
                action_type="trend",
                generation_id=generation_id,
                expected_cost_rox=request.get("quoted_cost_rox"),
                commit=False,
                wake=False,
            )
        except Exception as exc:
            _log_lifecycle(
                "failure",
                workflow_id=run.id,
                step_id=step_key,
                generation_id=generation_id,
                attempt=step_row.attempts,
                status="failed",
                failure_category=type(exc).__name__,
                request_id=request_id,
            )
            raise
        step_row.generation_id = generation.id
        step_row.reserved_generation_id = None
        generation.parameters = {
            **(generation.parameters or {}),
            "_trend_workflow_id": str(run.id),
            "_trend_id": str(run.trend_id),
            "_trend_workflow_step": step_key,
        }
        if not run.usage_incremented:
            trend = await session.scalar(
                select(AdminTrend).where(AdminTrend.id == run.trend_id).with_for_update()
            )
            if trend is None:
                raise TrendWorkflowConflict("The workflow template is unavailable")
            payload = dict(trend.payload or {})
            payload["usage_count"] = max(0, int(payload.get("usage_count", 0))) + 1
            trend.payload = payload
            run.usage_incremented = True
        _log_lifecycle(
            "retry" if step_row.attempts > 1 else "run",
            workflow_id=run.id,
            step_id=step_key,
            generation_id=generation.id,
            attempt=step_row.attempts,
            status=step_row.status,
            request_id=request_id,
        )
        await session.commit()
        await GenerationService.wake(redis, [generation.id])
        return step_row

    @staticmethod
    def _historical_media(
        item: dict[str, Any], kind: str, ready_assets: dict[uuid.UUID, list[MediaAsset]]
    ) -> dict[str, Any] | None:
        assets = ready_assets.get(uuid.UUID(str(item["generation_id"])), [])
        if not assets:
            return None
        selected = (
            next((asset for asset in assets if str(asset.id) == str(item.get("media_asset_id"))), None)
            if kind == "image" else None
        ) or assets[0]
        return MediaAssetService.public_view(selected, server_route=False)

    @staticmethod
    def _step_aspect_ratio_options(step: dict[str, Any]) -> list[str]:
        model_id = str(step.get("model_id") or "")
        # Kling's I2V contract derives dimensions from its input frame and
        # rejects any aspect_ratio. All workflow video steps bind a frame.
        if model_id == "kling-3.0" and step.get("kind") == "video":
            return []
        return explicit_aspect_ratio_options(model_id)

    @staticmethod
    def _step_presentation(
        step: dict[str, Any], *, generation: Generation | None = None,
    ) -> dict[str, Any]:
        """Only customer-safe snapshot metadata, never provider settings/prompts."""
        model_id = str(step.get("model_id") or "")
        title = str(step.get("model_title") or model_id)
        settings = dict(step.get("parameters") or {})
        if generation is not None:
            actual_parameters = generation.parameters or {}
            if "aspect_ratio" in actual_parameters:
                settings["aspect_ratio"] = actual_parameters["aspect_ratio"]
            else:
                settings.pop("aspect_ratio", None)
        summary = {
            key: settings[key]
            for key in ("duration", "resolution", "aspect_ratio")
            if key in settings and isinstance(settings[key], (str, int, float))
            and not (key == "aspect_ratio" and is_auto_aspect_ratio(settings[key]))
        }
        options = TrendWorkflowService._step_aspect_ratio_options(step)
        current_ratio = settings.get("aspect_ratio")
        required = bool(options) and (
            requires_explicit_aspect_ratio(model_id) or is_auto_aspect_ratio(current_ratio)
        )
        return {
            "model": {"id": model_id, "title": title},
            "settings_summary": summary,
            "preview_url": step.get("preview_url"),
            "aspect_ratio_options": options,
            "aspect_ratio_required": required,
            "default_aspect_ratio": current_ratio if current_ratio in options else None,
        }

    @classmethod
    async def latest_owned_view(
        cls, session: AsyncSession, *, trend_id: uuid.UUID, user_id: uuid.UUID
    ) -> dict[str, Any]:
        # Existing paid work belongs to the owner even if the live template is hidden.
        run = await session.scalar(
            select(TrendWorkflowRun).where(
                TrendWorkflowRun.trend_id == trend_id, TrendWorkflowRun.user_id == user_id
            ).order_by(TrendWorkflowRun.created_at.desc(), TrendWorkflowRun.id.desc()).limit(1)
        )
        if run is None:
            raise LookupError("Workflow not found")
        return await cls.public_view(session, run_id=run.id, user_id=user_id)

    @classmethod
    async def public_view(cls, session: AsyncSession, *, run_id: uuid.UUID, user_id: uuid.UUID) -> dict[str, Any]:
        run = await cls._owned_run(session, run_id=run_id, user_id=user_id)
        rows = list((await session.scalars(select(TrendWorkflowStep).where(TrendWorkflowStep.workflow_id == run.id).order_by(TrendWorkflowStep.ordinal))).all())
        reconcile_required: set[uuid.UUID] = set()
        for row in rows:
            if getattr(row, "reserved_generation_id", None) is None or row.generation_id is not None:
                continue
            reserved = await session.get(Generation, row.reserved_generation_id)
            if reserved is None:
                reconcile_required.add(row.id)
                continue
            if reserved.user_id != user_id:
                reconcile_required.add(row.id)
                continue
            row.generation_id = reserved.id
            row.reserved_generation_id = None
            row.status = "failed" if reserved.status == "failed" else "queued"
            if reserved.status == "failed":
                row.last_error = reserved.error
            await session.commit()
        generations = {
            row.generation_id: await session.get(Generation, row.generation_id)
            for row in rows
            if row.generation_id is not None
        }
        historical_generation_ids = [
            uuid.UUID(str(item["generation_id"]))
            for row in rows
            for item in (getattr(row, "attempt_history", None) or [])
            if isinstance(item, dict) and item.get("generation_id")
        ]
        ready_assets = await MediaAssetService.ready_assets_for_generations(
            session,
            user_id=user_id,
            generation_ids=list(dict.fromkeys([*generations, *historical_generation_ids])),
        )
        output_steps = []
        for row in rows:
            recipe_step = next(step for step in run.recipe_snapshot["steps"] if step["id"] == row.step_key)
            generation = generations.get(row.generation_id)
            status = row.status
            assets = ready_assets.get(row.generation_id, []) if row.generation_id else []
            selected = (assets[0] if assets else None) if row.kind == "video" else (
                next((asset for asset in assets if asset.id == row.media_asset_id), None)
                or (assets[0] if assets else None)
            )
            if generation is not None:
                if generation.status == "failed":
                    status = "failed"
                elif generation.status == "succeeded":
                    status = "ready" if selected is not None else "awaiting_media"
                else:
                    status = "running"
            media = None
            if selected is not None:
                media = MediaAssetService.public_view(selected, server_route=False)
            output_steps.append({
                "id": row.step_key,
                "kind": row.kind,
                "title": recipe_step["title"],
                "instructions": recipe_step["instructions"],
                "inputs": recipe_step["inputs"],
                **cls._step_presentation(recipe_step, generation=generation),
                "status": status,
                "generation_id": str(row.generation_id) if row.generation_id else None,
                # Owner-only receipt: distinguish a delayed retry from the old
                # failed generation without exposing its input or payload hash.
                "command_id": row.command_key,
                "media_asset_id": str(selected.id) if selected is not None else None,
                "media": media,
                "media_options": [MediaAssetService.public_view(asset, server_route=False) for asset in assets],
                "attempts": row.attempts,
                "reconcile_required": row.id in reconcile_required,
                "attempt_history": [
                    {
                        "generation_id": str(item.get("generation_id")),
                        "command_id": item.get("command_key"),
                        "status": str(item.get("status")),
                        "attempt": int(item.get("attempt") or 0),
                        "media_asset_id": str(item.get("media_asset_id")) if item.get("media_asset_id") else None,
                        "media": cls._historical_media(item, row.kind, ready_assets),
                        "media_options": [
                            MediaAssetService.public_view(asset, server_route=False)
                            for asset in ready_assets.get(uuid.UUID(str(item["generation_id"])), [])
                        ],
                    }
                    for item in (getattr(row, "attempt_history", None) or [])
                    if isinstance(item, dict)
                ],
            })
        current_status = run.status
        if reconcile_required:
            current_status = "reconciling"
        elif output_steps and output_steps[-1]["status"] == "ready":
            current_status = "completed"
        elif output_steps and output_steps[0]["status"] == "ready":
            current_status = "step1_ready"
        from app.services.trends import TrendService

        preview_url = run.recipe_snapshot.get("preview_url")
        return {
            "id": str(run.id),
            "trend_id": str(run.trend_id),
            "title": str(run.recipe_snapshot.get("title") or "Photo to video"),
            "description": str(run.recipe_snapshot.get("description") or ""),
            "preview_url": preview_url,
            "preview_thumbnail_url": TrendService.preview_thumbnail_url(run.trend_id, preview_url),
            "status": current_status,
            "recipe_version": run.recipe_version,
            "workflow_type": "sequential_photo_video",
            "steps": output_steps,
        }
