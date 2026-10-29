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
@pytest.mark.parametrize("personal_action", ["prune", "remove"])
async def test_saved_template_audio_survives_personal_pruning_and_deletion(personal_action):
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
        if personal_action == "remove":
            await ReferenceService.remove(session, user_id=owner.id, reference_id=personal.id)
        for index in range(13):
            await ReferenceService.register(session, user_id=owner.id, source_url=f'https://cdn.example.invalid/{uuid.uuid4()}-{index}.mp3', kind='audio')
        assert await session.scalar(select(UserReference.status).where(UserReference.id == personal.id)) == 'deleted'
        await validate_reference_duration_contracts(session, model_id='seedance-2.5', parameters={'reference_audio_urls': [url]})


@pytest.mark.asyncio
@pytest.mark.parametrize("audio_field", ["reference_audio_urls", "audio_url", "driving_audio_url", "elements"])
async def test_disposal_retains_hidden_duplicates_and_rejects_reuse_after_discard(audio_field):
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
        params = {audio_field: [asset.source_url] if audio_field.endswith('_urls') else asset.source_url}
        if audio_field == 'elements':
            params = {'elements': [{'element_input_audio_urls': [asset.source_url]}]}
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
            await TemplateAudioService.protect_parameters(session, params)
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
    monkeypatch.setattr('app.api.v1.uploads.probe_media_stream', lambda *_: MediaProbe(status='ready', duration_ms=10000, audio_codec='mp3', has_video=False))
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
@pytest.mark.parametrize("parameter_location", ["parameters", "generation_settings"])
async def test_migration_preserves_pruned_audio_in_hidden_template(monkeypatch, parameter_location):
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
        session.add(AdminTrend(title='Hidden old template', payload={parameter_location: {'reference_audio_urls': [url]}}, is_active=False, created_by_admin_id=admin.id))
        await session.flush()
        for _ in range(2):
            for statement in statements:
                await session.execute(text(statement))
        assert await session.scalar(select(TemplateAudioReference.duration_ms).where(TemplateAudioReference.source_url == url)) == 10000
        await validate_reference_duration_contracts(session, model_id='seedance-2.5', parameters={'reference_audio_urls': [url]})


@pytest.mark.asyncio
@pytest.mark.parametrize('owner_id', [None, uuid.uuid4()])
async def test_template_audio_uses_model_size_limit_even_without_personal_owner(owner_id):
    from app.db.reference_models import TemplateAudioReference
    from app.services.model_catalog import InvalidModelParametersError, ModelCatalog
    from app.services.reference_size_contract import validate_reference_sizes

    async with SessionFactory() as session:
        asset = TemplateAudioReference(source_url=f'https://cdn.example.invalid/{uuid.uuid4()}.mp3', duration_ms=10000, probe_status='ready', size_bytes=15 * 1024 * 1024)
        session.add(asset)
        await session.flush()
        params = {'reference_audio_urls': [asset.source_url]}
        await validate_reference_sizes(session, spec=ModelCatalog.get('seedance-2.5'), parameters=params, user_id=owner_id)
        asset.size_bytes += 1
        await session.flush()
        with pytest.raises(InvalidModelParametersError, match='reference_audio_urls reference exceeds 15 MB'):
            await validate_reference_sizes(session, spec=ModelCatalog.get('seedance-2.5'), parameters=params, user_id=owner_id)


@pytest.mark.asyncio
async def test_preset_save_and_disposal_are_serialized_in_both_orders():
    import asyncio
    from app.db.reference_models import TemplateAudioReference
    from app.services.template_audio import TemplateAudioService
    from app.services.user_presets import PresetError, UserPresetService

    async with SessionFactory() as writer, SessionFactory() as cleaner:
        owner = User(telegram_id=random.randrange(8_000_000_000_000, 8_999_999_999_999))
        writer.add(owner)
        await writer.flush()
        asset = TemplateAudioReference(source_url=f'https://cdn.example.invalid/{uuid.uuid4()}.mp3', duration_ms=10000, probe_status='ready')
        writer.add(asset)
        await writer.commit()
        asset_id, owner_id = asset.id, owner.id
        args = dict(user_id=owner_id, name='Audio preset', model_id='seedance-2.5', prompt='Use @Audio1', parameters={'reference_audio_urls': [asset.source_url]}, reference_ids=[])
        await UserPresetService.validate(writer, **args)
        task = asyncio.create_task(TemplateAudioService.discard(cleaner, asset_id))
        try:
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(asyncio.shield(task), timeout=0.2)
            preset = await UserPresetService.create(writer, **args)
            with pytest.raises(ValueError, match='still used'):
                await asyncio.wait_for(task, timeout=5)
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            await cleaner.rollback()
        await UserPresetService.remove(writer, user_id=owner_id, preset_id=preset.id)
        await TemplateAudioService.discard(cleaner, asset_id)
        await cleaner.commit()
        with pytest.raises(PresetError, match='removed'):
            await UserPresetService.create(writer, **args)


@pytest.mark.asyncio
@pytest.mark.parametrize('commit_fails', [False, True])
async def test_disposal_audit_is_attributed_and_only_emitted_after_commit(monkeypatch, caplog, commit_fails):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, Mock
    from fastapi import HTTPException
    from starlette.requests import Request
    from app.api.v1.trends import discard_template_audio
    from app.services.template_audio import TemplateAudioService
    from app.services.reference_static import ReferenceStaticStorage

    actor_id, asset_id = uuid.uuid4(), uuid.uuid4()
    session = AsyncMock()
    session.scalar.return_value = None
    if commit_fails:
        session.commit.side_effect = RuntimeError('commit failed')
    monkeypatch.setattr('app.api.v1.trends._inline_admin', AsyncMock())
    monkeypatch.setattr(TemplateAudioService, 'discard', AsyncMock(return_value=SimpleNamespace(source_url='/uploads/refs/audio/test.mp3')))
    unlink = Mock()
    monkeypatch.setattr(ReferenceStaticStorage, 'remove_url', unlink)
    request = Request({'type': 'http', 'headers': [(b'x-request-id', b'audio-disposal-test')]})
    with caplog.at_level('INFO'):
        if commit_fails:
            with pytest.raises(HTTPException):
                await discard_template_audio(asset_id, request, SimpleNamespace(id=actor_id), session)
        else:
            await discard_template_audio(asset_id, request, SimpleNamespace(id=actor_id), session)
    if commit_fails:
        assert 'template_audio_metadata_discarded' not in caplog.text
        unlink.assert_not_called()
    else:
        assert str(actor_id) in caplog.text
        assert str(asset_id) in caplog.text
        assert 'audio-disposal-test' in caplog.text
        unlink.assert_called_once()
