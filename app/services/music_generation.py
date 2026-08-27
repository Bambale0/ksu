from __future__ import annotations

import logging
import uuid
from decimal import Decimal
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import Generation
from app.services.abuse_protection import AbuseProtectionService, GenerationAdmissionService
from app.services.billing_access import BillingAccessService
from app.services.generation_reliability import GenerationOutboxService
from app.services.model_presentation import music_model_title
from app.services.wallet import WalletService

logger = logging.getLogger(__name__)

# Stable ROXY product id kept for stored drafts/history. The displayed title and
# immutable provider snapshot are derived from MUSIC_GENERATION_MODEL.
MUSIC_MODEL_ID = "suno-v5.5"
MUSIC_FAMILY = "suno"
MUSIC_OPERATION = "text_to_music"
MUSIC_MEDIA_TYPE = "audio"
MAX_MUSIC_GENERATION_QUANTITY = 4
MUSIC_SIMPLE_PROMPT_LIMIT = 500
MUSIC_CUSTOM_PROMPT_LIMIT = 5000
MUSIC_STYLE_LIMIT = 1000
MUSIC_TITLE_LIMIT = 80

_MUSIC_FIELDS = (
    "prompt",
    "customMode",
    "instrumental",
    "style",
    "title",
    "negativeTags",
    "vocalGender",
    "styleWeight",
    "weirdnessConstraint",
    "audioWeight",
    "personaId",
    "personaModel",
    "duration",
)


def _amount(value: Decimal | str | int | float) -> str:
    return format(Decimal(str(value)), ".2f")


def _field(
    name: str,
    label: str,
    control: str,
    group: str,
    *,
    required: bool = False,
    placeholder: str = "",
    suggestions: list[str] | None = None,
    minimum: float | None = None,
    maximum: float | None = None,
    step: float | None = None,
    suffix: str = "",
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "name": name,
        "label": label,
        "control": control,
        "group": group,
        "required": required,
    }
    if placeholder:
        result["placeholder"] = placeholder
    if suggestions:
        result["suggestions"] = suggestions
    if minimum is not None:
        result["min"] = minimum
    if maximum is not None:
        result["max"] = maximum
    if step is not None:
        result["step"] = step
    if suffix:
        result["suffix"] = suffix
    return result


def _normalize_vocal_gender(value: object) -> str | None:
    if value in (None, ""):
        return None
    normalized = str(value).strip().lower()
    aliases = {
        "m": "m",
        "male": "m",
        "man": "m",
        "м": "m",
        "мужской": "m",
        "мужчина": "m",
        "f": "f",
        "female": "f",
        "woman": "f",
        "ж": "f",
        "женский": "f",
        "женщина": "f",
    }
    return aliases.get(normalized)


class MusicGenerationError(ValueError):
    pass


class MusicGenerationService:
    WAKE_KEY = "wake:generations"

    @staticmethod
    def is_music_model(model_id: str) -> bool:
        return model_id == MUSIC_MODEL_ID

    @classmethod
    def public_model(cls) -> dict[str, Any]:
        price = Decimal(settings.music_generation_price_rox)
        provider_model = str(settings.music_generation_model)
        fields = [
            _field(
                "prompt",
                "Промпт / текст песни",
                "textarea",
                "prompt",
                placeholder="Опиши музыку — стиль, жанр, настроение. В режиме «Свой текст» вставь [Verse] / [Chorus].",
            ),
            _field(
                "title",
                "Название (опционально)",
                "text",
                "prompt",
                placeholder="Например: Lo-fi для занятий",
            ),
            _field("customMode", "Свой текст", "toggle", "mode"),
            _field("instrumental", "Инструментал", "toggle", "mode"),
            _field(
                "style",
                "Стиль / жанр / настроение",
                "textarea",
                "mode",
                placeholder="Например: cinematic synthwave, female vocal, 120 BPM",
            ),
            _field(
                "vocalGender",
                "Голос",
                "combobox",
                "mode",
                suggestions=["m", "f"],
            ),
            _field(
                "styleWeight",
                "Сила стиля",
                "number",
                "advanced",
                minimum=0,
                maximum=1,
                step=0.05,
            ),
            _field(
                "weirdnessConstraint",
                "Странность",
                "number",
                "advanced",
                minimum=0,
                maximum=1,
                step=0.05,
            ),
            _field(
                "audioWeight",
                "Баланс вокал / музыка",
                "number",
                "advanced",
                minimum=0,
                maximum=1,
                step=0.05,
            ),
            _field(
                "negativeTags",
                "Исключить теги",
                "text",
                "advanced",
                placeholder="Например: heavy metal, screamo",
            ),
            _field(
                "duration",
                "Длительность (только V5.5), сек.",
                "number",
                "advanced",
                minimum=1,
                step=1,
            ),
            _field(
                "personaId",
                "Persona ID",
                "text",
                "advanced",
                placeholder="Необязательно · только Custom Mode",
            ),
            _field(
                "personaModel",
                "Persona model",
                "text",
                "advanced",
                placeholder="Например: style_persona",
            ),
        ]
        return {
            "id": MUSIC_MODEL_ID,
            "title": music_model_title(provider_model),
            "family": MUSIC_FAMILY,
            "kie_model": provider_model,
            "media_type": MUSIC_MEDIA_TYPE,
            "operation": MUSIC_OPERATION,
            "known_fields": list(_MUSIC_FIELDS),
            # Prompt requirements are conditional: Custom+Instrumental may omit it.
            "required_fields": [],
            "price_mode": "flat",
            "price_rox": _amount(price),
            "price_credits": _amount(price),
            "price_rub": _amount(price),
            "min_seconds": None,
            "max_seconds": None,
            "notes": [
                "Один запрос может вернуть несколько вариантов трека.",
                "В Simple Mode нужен только промпт; дополнительные поля применяются в Custom Mode.",
                "Результаты Kie сохраняются в хранилище ROXY после генерации.",
            ],
            "ui_schema": {
                "version": 1,
                "groups": [
                    {"id": "prompt", "title": "Промпт"},
                    {"id": "mode", "title": "Режим"},
                    {"id": "advanced", "title": "Расширенные настройки", "collapsible": True},
                ],
                "fields": fields,
                "defaults": {
                    "customMode": False,
                    "instrumental": False,
                    "vocalGender": "f",
                    "styleWeight": 0.7,
                    "weirdnessConstraint": 0.3,
                    "audioWeight": 0.6,
                },
                "summary_fields": [
                    "customMode",
                    "instrumental",
                    "style",
                    "title",
                    "vocalGender",
                    "styleWeight",
                    "weirdnessConstraint",
                    "audioWeight",
                    "duration",
                ],
            },
        }

    @classmethod
    def prepare(cls, parameters: dict[str, Any], prompt: str = "") -> tuple[dict[str, Any], Decimal]:
        raw = {key: value for key, value in dict(parameters or {}).items() if key in _MUSIC_FIELDS}
        if prompt and not raw.get("prompt"):
            raw["prompt"] = prompt

        custom_mode = bool(raw.get("customMode", False))
        instrumental = bool(raw.get("instrumental", False))
        raw["customMode"] = custom_mode
        raw["instrumental"] = instrumental

        text = str(raw.get("prompt") or "").strip()
        if custom_mode:
            if not instrumental and not text:
                raise MusicGenerationError("Для песни с вокалом в Custom Mode нужен текст / промпт")
            if len(text) > MUSIC_CUSTOM_PROMPT_LIMIT:
                raise MusicGenerationError(f"Промпт длиннее {MUSIC_CUSTOM_PROMPT_LIMIT} символов")
            if text:
                raw["prompt"] = text
            else:
                raw.pop("prompt", None)
        else:
            if not text:
                raise MusicGenerationError("Опишите музыку или добавьте текст песни")
            if len(text) > MUSIC_SIMPLE_PROMPT_LIMIT:
                raise MusicGenerationError(f"Промпт длиннее {MUSIC_SIMPLE_PROMPT_LIMIT} символов")
            raw["prompt"] = text

        if custom_mode:
            style = str(raw.get("style") or "").strip()
            title = str(raw.get("title") or "").strip()
            if not style:
                raise MusicGenerationError("В расширенном режиме укажите стиль музыки")
            if len(style) > MUSIC_STYLE_LIMIT:
                raise MusicGenerationError(f"Стиль длиннее {MUSIC_STYLE_LIMIT} символов")
            if len(title) > MUSIC_TITLE_LIMIT:
                raise MusicGenerationError(f"Название длиннее {MUSIC_TITLE_LIMIT} символов")
            raw["style"] = style
            if title:
                raw["title"] = title
            else:
                raw.pop("title", None)
        else:
            # Kie Simple Mode requires prompt only; all custom-only options stay empty.
            for key in (
                "style",
                "title",
                "negativeTags",
                "vocalGender",
                "styleWeight",
                "weirdnessConstraint",
                "audioWeight",
                "personaId",
                "personaModel",
                "duration",
            ):
                raw.pop(key, None)

        gender = _normalize_vocal_gender(raw.get("vocalGender"))
        if raw.get("vocalGender") not in (None, "") and not gender:
            raise MusicGenerationError("vocalGender должен быть m или f")
        if gender:
            raw["vocalGender"] = gender
        else:
            raw.pop("vocalGender", None)

        for key in ("styleWeight", "weirdnessConstraint", "audioWeight"):
            if raw.get(key) in (None, ""):
                raw.pop(key, None)
                continue
            try:
                value = float(raw[key])
            except (TypeError, ValueError) as exc:
                raise MusicGenerationError(f"Некорректное значение {key}") from exc
            if not 0 <= value <= 1:
                raise MusicGenerationError(f"{key} должен быть в диапазоне 0..1")
            raw[key] = round(value, 2)

        if raw.get("negativeTags") is not None:
            raw["negativeTags"] = str(raw["negativeTags"]).strip()[:1000]
            if not raw["negativeTags"]:
                raw.pop("negativeTags", None)

        for key in ("personaId", "personaModel"):
            if raw.get(key) is None:
                continue
            value = str(raw[key]).strip()
            if value:
                raw[key] = value
            else:
                raw.pop(key, None)

        if raw.get("duration") not in (None, ""):
            if str(settings.music_generation_model).upper() != "V5_5":
                raise MusicGenerationError("duration поддерживается только моделью V5_5")
            try:
                duration = int(raw["duration"])
            except (TypeError, ValueError) as exc:
                raise MusicGenerationError("duration должен быть целым числом секунд") from exc
            if duration <= 0:
                raise MusicGenerationError("duration должен быть больше 0")
            raw["duration"] = duration
        else:
            raw.pop("duration", None)

        price = Decimal(settings.music_generation_price_rox).quantize(Decimal("0.01"))
        if price <= 0:
            raise MusicGenerationError("Цена генерации музыки не опубликована")
        return raw, price

    @staticmethod
    def _generation_parameters(
        *,
        clean: dict[str, Any],
        provider_model: str,
        retail_cost_rox: Decimal,
        admin_free: bool,
        batch_id: uuid.UUID | None = None,
        batch_index: int = 1,
        batch_size: int = 1,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            **clean,
            "_model_id": MUSIC_MODEL_ID,
            "_model_title": music_model_title(provider_model),
            "_model_family": MUSIC_FAMILY,
            "_media_type": MUSIC_MEDIA_TYPE,
            "_operation": MUSIC_OPERATION,
            "_provider_api": "suno_music",
            "_kie_model": provider_model,
            "_provider_model": provider_model,
            "_billing_mode": "flat",
            "_billing_seconds": None,
            "_unit_price_rox": str(retail_cost_rox),
            "_retail_cost_rox": str(retail_cost_rox),
            "_admin_free": admin_free,
            **(
                {"_admin_free_generation": True, "_quoted_cost_rox": str(retail_cost_rox)}
                if admin_free
                else {}
            ),
        }
        if batch_id is not None and batch_size > 1:
            params.update(
                {
                    "_batch_id": str(batch_id),
                    "_batch_index": batch_index,
                    "_batch_size": batch_size,
                }
            )
        return params

    @classmethod
    async def create_many(
        cls,
        session: AsyncSession,
        redis: Redis,
        *,
        user_id: uuid.UUID,
        prompt: str,
        parameters: dict[str, Any],
        quantity: int = 1,
    ) -> list[Generation]:
        requested = int(quantity)
        if requested < 1 or requested > MAX_MUSIC_GENERATION_QUANTITY:
            raise MusicGenerationError(
                f"Количество генераций должно быть от 1 до {MAX_MUSIC_GENERATION_QUANTITY}"
            )

        clean, retail_cost_rox = cls.prepare(parameters, prompt)
        billing = await BillingAccessService.decision(
            session,
            user_id=user_id,
            retail_cost=retail_cost_rox,
        )
        charge_rox = billing.effective_cost
        total_charge_rox = (charge_rox * Decimal(requested)).quantize(Decimal("0.01"))
        await AbuseProtectionService.generation_rate(redis, user_id, amount=requested)
        await GenerationAdmissionService.enforce(
            session,
            user_id=user_id,
            next_cost=total_charge_rox,
            quantity=requested,
        )

        provider_model = str(settings.music_generation_model)
        batch_id = uuid.uuid4() if requested > 1 else None
        generations: list[Generation] = []
        for index in range(1, requested + 1):
            generation = Generation(
                user_id=user_id,
                kind="music",
                prompt=str(clean.get("prompt") or ""),
                cost_rox=charge_rox,
                provider="kie",
                status="queued",
                parameters=cls._generation_parameters(
                    clean=clean,
                    provider_model=provider_model,
                    retail_cost_rox=billing.retail_cost,
                    admin_free=billing.admin_free,
                    batch_id=batch_id,
                    batch_index=index,
                    batch_size=requested,
                ),
                publication_scope="private",
                is_public_feed=False,
                is_profile_visible=False,
                feed_prompt_visible=False,
                feed_references_visible=False,
            )
            session.add(generation)
            generations.append(generation)

        await session.flush()

        for generation in generations:
            GenerationOutboxService.add(session, generation.id)
            if charge_rox > 0:
                await WalletService.debit(
                    session,
                    user_id=user_id,
                    amount=charge_rox,
                    kind="generation",
                    reference_type="generation",
                    reference_id=str(generation.id),
                    idempotency_key=f"generation:{generation.id}:charge",
                )
        await session.commit()

        try:
            await redis.rpush(cls.WAKE_KEY, *[str(generation.id) for generation in generations])
        except RedisError:
            logger.warning("Redis wake-up failed for %s music generation(s)", len(generations))
        return generations

    @classmethod
    async def create(
        cls,
        session: AsyncSession,
        redis: Redis,
        *,
        user_id: uuid.UUID,
        prompt: str,
        parameters: dict[str, Any],
    ) -> Generation:
        generations = await cls.create_many(
            session,
            redis,
            user_id=user_id,
            prompt=prompt,
            parameters=parameters,
            quantity=1,
        )
        return generations[0]

    @staticmethod
    def public_settings(parameters: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value
            for key, value in dict(parameters or {}).items()
            if key in _MUSIC_FIELDS and key != "prompt" and not key.startswith("_")
        }

    @staticmethod
    def reusable_parameters(parameters: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value
            for key, value in dict(parameters or {}).items()
            if key in _MUSIC_FIELDS and key != "prompt" and not key.startswith("_")
        }
