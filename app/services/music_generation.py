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
from app.services.generation_reliability import GenerationOutboxService
from app.services.wallet import WalletService

logger = logging.getLogger(__name__)

MUSIC_MODEL_ID = "suno-v5.5"
MUSIC_FAMILY = "suno"
MUSIC_OPERATION = "text_to_music"
MUSIC_MEDIA_TYPE = "audio"

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
    return result


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
        fields = [
            _field(
                "prompt",
                "Идея / текст песни",
                "textarea",
                "prompt",
                placeholder="Опиши настроение, сюжет, жанр или вставь текст песни",
            ),
            _field("customMode", "Расширенный режим", "toggle", "output"),
            _field("instrumental", "Без вокала", "toggle", "output"),
            _field(
                "style",
                "Стиль музыки",
                "textarea",
                "output",
                placeholder="Например: cinematic synthwave, female vocal, 120 BPM",
            ),
            _field(
                "title",
                "Название",
                "text",
                "output",
                placeholder="До 80 символов",
            ),
            _field(
                "negativeTags",
                "Исключить стили",
                "text",
                "advanced",
                placeholder="Например: heavy metal, aggressive drums",
            ),
            _field(
                "vocalGender",
                "Вокал",
                "combobox",
                "advanced",
                suggestions=["m", "f"],
            ),
            _field(
                "styleWeight",
                "Вес стиля",
                "number",
                "advanced",
                minimum=0,
                maximum=1,
                step=0.05,
            ),
            _field(
                "weirdnessConstraint",
                "Экспериментальность",
                "number",
                "advanced",
                minimum=0,
                maximum=1,
                step=0.05,
            ),
            _field(
                "audioWeight",
                "Вес аудио",
                "number",
                "advanced",
                minimum=0,
                maximum=1,
                step=0.05,
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
            _field(
                "duration",
                "Длительность V5.5, сек.",
                "number",
                "advanced",
                minimum=1,
                step=1,
            ),
        ]
        return {
            "id": MUSIC_MODEL_ID,
            "title": "Suno V5.5 · Music",
            "family": MUSIC_FAMILY,
            "kie_model": settings.music_generation_model,
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
                    {"id": "prompt", "title": "Идея"},
                    {"id": "output", "title": "Музыка"},
                    {"id": "advanced", "title": "Дополнительно", "collapsible": True},
                ],
                "fields": fields,
                "defaults": {"customMode": False, "instrumental": False},
                "summary_fields": [
                    "customMode",
                    "instrumental",
                    "style",
                    "title",
                    "vocalGender",
                    "personaId",
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
            if len(text) > 5000:
                raise MusicGenerationError("Промпт длиннее 5000 символов")
            if text:
                raw["prompt"] = text
            else:
                raw.pop("prompt", None)
        else:
            if not text:
                raise MusicGenerationError("Опишите музыку или добавьте текст песни")
            if len(text) > 3000:
                raise MusicGenerationError("Промпт длиннее 3000 символов")
            raw["prompt"] = text

        if custom_mode:
            style = str(raw.get("style") or "").strip()
            title = str(raw.get("title") or "").strip()
            if not style:
                raise MusicGenerationError("В расширенном режиме укажите стиль музыки")
            if not title:
                raise MusicGenerationError("В расширенном режиме укажите название")
            if len(style) > 1000:
                raise MusicGenerationError("Стиль длиннее 1000 символов")
            if len(title) > 80:
                raise MusicGenerationError("Название длиннее 80 символов")
            raw["style"] = style
            raw["title"] = title
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

        gender = raw.get("vocalGender")
        if gender not in (None, "", "m", "f"):
            raise MusicGenerationError("vocalGender должен быть m или f")
        if gender == "":
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
        clean, cost_rox = cls.prepare(parameters, prompt)
        await AbuseProtectionService.generation_rate(redis, user_id)
        await GenerationAdmissionService.enforce(session, user_id=user_id, next_cost=cost_rox)

        generation = Generation(
            user_id=user_id,
            kind="music",
            prompt=str(clean.get("prompt") or ""),
            cost_rox=cost_rox,
            provider="kie",
            status="queued",
            parameters={
                **clean,
                "_model_id": MUSIC_MODEL_ID,
                "_model_title": "Suno V5.5 · Music",
                "_family": MUSIC_FAMILY,
                "_media_type": MUSIC_MEDIA_TYPE,
                "_operation": MUSIC_OPERATION,
                "_provider_api": "suno_music",
                "_kie_model": settings.music_generation_model,
                "_billing_mode": "flat",
                "_billing_seconds": None,
                "_unit_price_rox": str(cost_rox),
            },
            publication_scope="private",
            is_public_feed=False,
            is_profile_visible=False,
            feed_prompt_visible=False,
            feed_references_visible=False,
        )
        session.add(generation)
        await session.flush()
        GenerationOutboxService.add(session, generation.id)
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

        try:
            await redis.rpush(cls.WAKE_KEY, str(generation.id))
        except RedisError:
            logger.warning("Redis wake-up failed for music generation %s", generation.id)
        return generation

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
