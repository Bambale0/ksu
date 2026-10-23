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


@pytest.mark.asyncio
async def test_concurrent_disposal_waits_for_template_save():
    import asyncio
    from app.db.reference_models import TemplateAudioReference
    from app.services.template_audio import TemplateAudioService

    async with SessionFactory() as writer, SessionFactory() as cleaner:
        owner = User(telegram_id=random.randrange(8_000_000_000_000, 8_999_999_999_999))
        writer.add(owner)
        await writer.flush()
        admin = AdminAccount(user_id=owner.id, role='admin')
        writer.add(admin)
        await writer.flush()
        asset = TemplateAudioReference(source_url=f'https://cdn.example.invalid/{uuid.uuid4()}.mp3', duration_ms=10000, probe_status='ready')
        writer.add(asset)
        await writer.commit()
        params = {'reference_audio_urls': [asset.source_url]}
        await TemplateAudioService.pin_recipe(writer, params)
        task = asyncio.create_task(TemplateAudioService.discard(cleaner, asset.id))
        try:
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(asyncio.shield(task), timeout=0.2)
            writer.add(AdminTrend(title='Concurrent save', payload={'parameters': params}, created_by_admin_id=admin.id))
            await writer.commit()
            with pytest.raises(ValueError, match='still used'):
                await asyncio.wait_for(task, timeout=5)
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            await cleaner.rollback()


@pytest.mark.asyncio
@pytest.mark.parametrize('mime,filename,probe,expected', [
    ('application/octet-stream', 'bad.exe', None, 415),
    ('image/png', 'bad.mp3', None, 415),
    ('audio/mpeg', 'bad.mp3', {'status': 'ready', 'duration_ms': 10000}, 422),
    ('audio/mpeg', 'bad.mp3', {'status': 'ready', 'duration_ms': 10000, 'audio_codec': 'aac', 'video_codec': 'h264'}, 422),
])
async def test_template_upload_rejects_disallowed_or_disguised_media(monkeypatch, mime, filename, probe, expected):
    from io import BytesIO
    from unittest.mock import AsyncMock, Mock
    from fastapi import HTTPException
    from starlette.datastructures import Headers, UploadFile
    from app.api.v1.uploads import upload_template_audio
    from app.services.abuse_protection import AbuseProtectionService
    from app.services.media_probe import MediaProbe
    from app.services.reference_static import ReferenceStaticStorage

    monkeypatch.setattr('app.api.v1.trends._inline_admin', AsyncMock())
    monkeypatch.setattr(AbuseProtectionService, 'upload_rate_and_bytes', AsyncMock())
    monkeypatch.setattr('app.api.v1.uploads.probe_media_stream', lambda *_: MediaProbe(**(probe or {'status': 'failed'})))
    persist = Mock()
    monkeypatch.setattr(ReferenceStaticStorage, 'persist_stream', persist)
    with pytest.raises(HTTPException) as error:
        await upload_template_audio(User(id=uuid.uuid4()), AsyncMock(), AsyncMock(), UploadFile(BytesIO(b'bad'), filename=filename, headers=Headers({'content-type': mime})))
    assert error.value.status_code == expected
    persist.assert_not_called()


@pytest.mark.asyncio
async def test_generation_history_blocks_disposal_and_uploader_deletion_keeps_metadata():
    from app.db.models import Generation
    from app.db.reference_models import TemplateAudioReference
    from app.services.template_audio import TemplateAudioService

    async with SessionFactory() as session:
        owner = User(telegram_id=random.randrange(8_000_000_000_000, 8_999_999_999_999))
        customer = User(telegram_id=random.randrange(8_000_000_000_000, 8_999_999_999_999))
        session.add_all([owner, customer])
        await session.flush()
        asset = TemplateAudioReference(source_url=f'https://cdn.example.invalid/{uuid.uuid4()}.mp3', uploaded_by=owner.id, duration_ms=10000, probe_status='ready')
        session.add(asset)
        await session.flush()
        asset_id, url = asset.id, asset.source_url
        session.add(Generation(user_id=customer.id, kind='video', prompt='audio', cost_rox=0, parameters={'reference_audio_urls': [url]}, status='succeeded'))
        await session.commit()
        await session.delete(owner)
        await session.commit()
        await session.refresh(asset)
        assert asset.uploaded_by is None
        await validate_reference_duration_contracts(session, model_id='seedance-2.5', parameters={'reference_audio_urls': [url]})
        with pytest.raises(ValueError, match='still used'):
            await TemplateAudioService.discard(session, asset_id)


@pytest.mark.asyncio
async def test_migration_preserves_pruned_audio_in_hidden_template(monkeypatch):
    import runpy
    from sqlalchemy import text
    from app.db.reference_models import TemplateAudioReference

    statements = []
    migration = runpy.run_path('alembic/versions/0043_template_audio.py')
    monkeypatch.setattr(migration['op'], 'execute', statements.append)
    migration['backfill_existing_audio']()
    async with SessionFactory() as session:
        owner = User(telegram_id=random.randrange(8_000_000_000_000, 8_999_999_999_999))
        session.add(owner)
        await session.flush()
        admin = AdminAccount(user_id=owner.id, role='admin')
        session.add(admin)
        await session.flush()
        url = f'https://cdn.example.invalid/{uuid.uuid4()}.mp3'
        session.add(UserReference(user_id=owner.id, kind='audio', status='deleted', source_url=url, duration_ms=10000, probe_status='ready'))
        session.add(AdminTrend(title='Hidden old template', payload={'parameters': {'reference_audio_urls': [url]}}, is_active=False, created_by_admin_id=admin.id))
        await session.flush()
        for _ in range(2):
            for statement in statements:
                await session.execute(text(statement))
        assert await session.scalar(select(TemplateAudioReference.duration_ms).where(TemplateAudioReference.source_url == url)) == 10000
        await validate_reference_duration_contracts(session, model_id='seedance-2.5', parameters={'reference_audio_urls': [url]})
