from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.reference_models import UserPreset
from app.services.model_catalog import ModelCatalog
from app.services.references import ReferenceService


class PresetError(ValueError):
    pass


class UserPresetService:
    @staticmethod
    async def validate(
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        name: str,
        model_id: str,
        prompt: str,
        parameters: dict[str, Any],
        billing_seconds: int | None,
        reference_ids: list[uuid.UUID],
    ) -> tuple[str, dict[str, Any], int | None, list[str]]:
        clean_name = name.strip()
        if not clean_name or len(clean_name) > 80:
            raise PresetError("Preset name must contain 1..80 characters")
        if len(prompt) > 8000:
            raise PresetError("Prompt must be at most 8000 characters")
        spec = ModelCatalog.get(model_id)
        unknown = sorted(set(parameters) - set(spec.known_fields))
        if unknown:
            raise PresetError(f"Unsupported preset parameters: {', '.join(unknown)}")
        if billing_seconds is not None:
            if billing_seconds <= 0:
                raise PresetError("billing_seconds must be positive")
            if spec.min_seconds is not None and billing_seconds < spec.min_seconds:
                raise PresetError(f"Minimum duration is {spec.min_seconds} seconds")
            if spec.max_seconds is not None and billing_seconds > spec.max_seconds:
                raise PresetError(f"Maximum duration is {spec.max_seconds} seconds")
        if len(reference_ids) > 16:
            raise PresetError("A preset can contain at most 16 references")
        rows = await ReferenceService.resolve_owned(
            session, user_id=user_id, reference_ids=reference_ids
        )
        return clean_name, dict(parameters), billing_seconds, [str(row.id) for row in rows]

    @staticmethod
    async def list_owned(session: AsyncSession, *, user_id: uuid.UUID) -> list[UserPreset]:
        return list(
            (
                await session.scalars(
                    select(UserPreset)
                    .where(UserPreset.user_id == user_id)
                    .order_by(UserPreset.updated_at.desc())
                    .limit(100)
                )
            ).all()
        )

    @staticmethod
    async def get_owned(
        session: AsyncSession, *, user_id: uuid.UUID, preset_id: uuid.UUID
    ) -> UserPreset:
        row = await session.get(UserPreset, preset_id)
        if row is None or row.user_id != user_id:
            raise LookupError("Preset not found")
        return row

    @classmethod
    async def create(
        cls,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        name: str,
        model_id: str,
        prompt: str,
        parameters: dict[str, Any],
        billing_seconds: int | None,
        reference_ids: list[uuid.UUID],
    ) -> UserPreset:
        clean_name, clean_parameters, clean_seconds, clean_refs = await cls.validate(
            session,
            user_id=user_id,
            name=name,
            model_id=model_id,
            prompt=prompt,
            parameters=parameters,
            billing_seconds=billing_seconds,
            reference_ids=reference_ids,
        )
        row = UserPreset(
            user_id=user_id,
            name=clean_name,
            model_id=model_id,
            prompt=prompt,
            parameters=clean_parameters,
            billing_seconds=clean_seconds,
            reference_ids=clean_refs,
        )
        session.add(row)
        await session.commit()
        return row

    @classmethod
    async def update(
        cls,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        preset_id: uuid.UUID,
        name: str,
        model_id: str,
        prompt: str,
        parameters: dict[str, Any],
        billing_seconds: int | None,
        reference_ids: list[uuid.UUID],
    ) -> UserPreset:
        row = await cls.get_owned(session, user_id=user_id, preset_id=preset_id)
        clean_name, clean_parameters, clean_seconds, clean_refs = await cls.validate(
            session,
            user_id=user_id,
            name=name,
            model_id=model_id,
            prompt=prompt,
            parameters=parameters,
            billing_seconds=billing_seconds,
            reference_ids=reference_ids,
        )
        row.name = clean_name
        row.model_id = model_id
        row.prompt = prompt
        row.parameters = clean_parameters
        row.billing_seconds = clean_seconds
        row.reference_ids = clean_refs
        await session.commit()
        return row

    @classmethod
    async def remove(
        cls, session: AsyncSession, *, user_id: uuid.UUID, preset_id: uuid.UUID
    ) -> None:
        row = await cls.get_owned(session, user_id=user_id, preset_id=preset_id)
        await session.delete(row)
        await session.commit()

    @staticmethod
    def public_view(row: UserPreset) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "name": row.name,
            "model_id": row.model_id,
            "prompt": row.prompt,
            "parameters": row.parameters,
            "billing_seconds": row.billing_seconds,
            "reference_ids": row.reference_ids,
            "created_at": row.created_at.isoformat(),
            "updated_at": row.updated_at.isoformat(),
        }
