from __future__ import annotations

import random
import uuid

import pytest
from sqlalchemy import select

from app.db.admin_models import AdminTrend
from app.db.models import AdminAccount, User
from app.db.reference_models import UserReference
from app.db.session import SessionFactory
from app.services.model_spec_trusted_media_audit import validate_reference_duration_contracts
from app.services.references import ReferenceService


@pytest.mark.asyncio
async def test_saved_template_audio_survives_personal_pruning_and_deletion():
    """Exercise the former upload -> template -> personal pruning -> run failure."""
    from app.services.template_audio import TemplateAudioService

    async with SessionFactory() as session:
        owner = User(telegram_id=random.randrange(8_000_000_000_000, 8_999_999_999_999))
        session.add(owner)
        await session.commit()
        url = f'https://cdn.example.invalid/{uuid.uuid4()}.mp3'
        personal, _ = await ReferenceService.register(session, user_id=owner.id, source_url=url, kind='audio')
        personal.duration_ms = 10000
        personal.probe_status = 'ready'
        await session.commit()
        # Saving a legacy registered URL promotes metadata into template ownership.
        await TemplateAudioService.pin_recipe(session, {'reference_audio_urls': [url]})
        admin = AdminAccount(user_id=owner.id, role='admin')
        session.add(admin)
        await session.flush()
        template = AdminTrend(title='Audio lifecycle', payload={'parameters': {'reference_audio_urls': [url]}}, is_active=True, created_by_admin_id=admin.id)
        session.add(template)
        await session.commit()
        await ReferenceService.remove(session, user_id=owner.id, reference_id=personal.id)
        for index in range(13):
            await ReferenceService.register(session, user_id=owner.id, source_url=f'https://cdn.example.invalid/{uuid.uuid4()}-{index}.mp3', kind='audio')
        assert await session.scalar(select(UserReference.status).where(UserReference.id == personal.id)) == 'deleted'
        await validate_reference_duration_contracts(session, model_id='seedance-2.5', parameters={'reference_audio_urls': [url]})


@pytest.mark.asyncio
async def test_disposal_retains_hidden_duplicates_and_rejects_reuse_after_discard():
    from app.db.reference_models import TemplateAudioReference
    from app.services.template_audio import TemplateAudioService

    async with SessionFactory() as session:
        owner = User(telegram_id=random.randrange(8_000_000_000_000, 8_999_999_999_999))
        session.add(owner)
        await session.flush()
        admin = AdminAccount(user_id=owner.id, role='admin')
        session.add(admin)
        await session.flush()
        asset = TemplateAudioReference(source_url=f'https://cdn.example.invalid/{uuid.uuid4()}.mp3', duration_ms=10000, probe_status='ready')
        session.add(asset)
        await session.flush()
        params = {'reference_audio_urls': [asset.source_url]}
        original = AdminTrend(title='Original', payload={'parameters': params}, created_by_admin_id=admin.id)
        duplicate = AdminTrend(title='Hidden duplicate', payload={'parameters': params}, is_active=False, created_by_admin_id=admin.id)
        session.add_all([original, duplicate])
        await session.commit()
        asset_id, duplicate_id = asset.id, duplicate.id
        original.payload = {'parameters': {}}
        await session.commit()
        with pytest.raises(ValueError, match='still used'):
            await TemplateAudioService.discard(session, asset_id)
        await session.rollback()
        duplicate = await session.get(AdminTrend, duplicate_id)
        duplicate.payload = {'parameters': {}}
        await session.commit()
        await TemplateAudioService.discard(session, asset_id)
        await session.commit()
        with pytest.raises(ValueError, match='removed'):
            await TemplateAudioService.pin_recipe(session, params)
        await session.rollback()


@pytest.mark.asyncio
async def test_template_upload_classifies_generic_mime_and_stays_outside_personal_memory(monkeypatch, tmp_path):
    from io import BytesIO
    from starlette.datastructures import Headers, UploadFile
    from app.api.v1.uploads import upload_template_audio
    from app.services.abuse_protection import AbuseProtectionService
    from app.services.media_probe import MediaProbe
    from app.services.reference_static import ReferenceStaticStorage
    from unittest.mock import AsyncMock

    monkeypatch.setattr(AbuseProtectionService, 'upload_rate_and_bytes', AsyncMock())
    monkeypatch.setattr('app.api.v1.uploads.probe_media_stream', lambda *_: MediaProbe(status='ready', duration_ms=10000, audio_codec='mp3'))
    monkeypatch.setattr(ReferenceStaticStorage, 'persist_stream', lambda *args, **kwargs: (f'/uploads/refs/audio/{kwargs["user_id"]}/test.mp3', tmp_path / 'test.mp3', 5))
    async with SessionFactory() as session:
        owner = User(telegram_id=random.randrange(8_000_000_000_000, 8_999_999_999_999))
        session.add(owner)
        await session.flush()
        session.add(AdminAccount(user_id=owner.id, role='admin'))
        await session.commit()
        for mime in ['', 'application/octet-stream', 'binary/octet-stream']:
            result = await upload_template_audio(owner, AsyncMock(), session, UploadFile(BytesIO(b'audio'), filename='reference.mp3', headers=Headers({'content-type': mime})))
            assert result['reference']['kind'] == 'audio'
            assert result['duration_ms'] == 10000
            assert await session.scalar(select(UserReference.id).where(UserReference.source_url == result['url'])) is None
            await validate_reference_duration_contracts(session, model_id='seedance-2.5', parameters={'reference_audio_urls': [result['url']]})


@pytest.mark.asyncio
async def test_template_upload_rejects_non_admin_before_storage():
    from io import BytesIO
    from starlette.datastructures import UploadFile
    from fastapi import HTTPException
    from app.api.v1.uploads import upload_template_audio
    from unittest.mock import AsyncMock

    async with SessionFactory() as session:
        owner = User(telegram_id=random.randrange(8_000_000_000_000, 8_999_999_999_999))
        session.add(owner)
        await session.commit()
        with pytest.raises(HTTPException) as error:
            await upload_template_audio(owner, AsyncMock(), session, UploadFile(BytesIO(b'audio'), filename='reference.mp3'))
        assert error.value.status_code == 403
