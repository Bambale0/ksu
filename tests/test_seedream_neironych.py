import base64
import json
import uuid

from app.db.models import Generation
from unittest.mock import AsyncMock

import httpx
import pytest

from app.providers.neironych_image import NeironychImageClient
from app.providers.neironych_errors import NeironychProviderError
from app.providers.neironych_submission import SNAPSHOT_KEY
from app.services.generation_provider_routing import route_options


@pytest.mark.parametrize('refs', [[], ['https://example.test/ref.jpg']])
async def test_seedream_http_contract(refs):
    def respond(request):
        assert request.url.path == ('/v1/images/edits' if refs else '/v1/images/generations')
        assert request.headers['Idempotency-Key'] == 'seedream-contract'
        assert json.loads(request.content) == {
            'model': 'seedream-5.0-pro', 'prompt': 'A cup', 'n': 1,
            'response_format': 'b64_json', 'resolution': '2k', 'aspect_ratio': '21:9',
            **({'images': [{'image_url': refs[0]}]} if refs else {}),
        }
        return httpx.Response(200, json={'data': [{'b64_json': base64.b64encode(b'jpeg').decode()}]})
    async with httpx.AsyncClient(base_url='https://example.test', transport=httpx.MockTransport(respond)) as http:
        client = NeironychImageClient('test-key', 'https://example.test', client=http)
        result = await client.create_image(model='seedream-5.0-pro', prompt='A cup',
            aspect_ratio='21:9', resolution='2K', image_urls=refs, idempotency_key='seedream-contract')
    assert result.content == b'jpeg'


@pytest.mark.parametrize('model', ['seedream-5-pro-t2i', 'seedream-5-pro-i2i'])
@pytest.mark.parametrize('quality,resolution', [('basic', '1k'), ('high', '2k')])
async def test_seedream_service_preserves_quality_and_freezes_alias(model, quality, resolution):
    from app.services.neironych_generation_provider import NeironychGenerationProviderService as Service
    generation = Generation(id=uuid.uuid4(), input_url=None, kind='generate', prompt='A cup', parameters={
        '_model_id': model, '_provider_route_index': 0, 'prompt': 'A cup',
        'quality': quality, 'aspect_ratio': '16:9', 'output_format': 'png',
        'image_urls': ['https://example.test/ref.jpg'] if model.endswith('i2i') else [],
    })
    assert Service.handles(generation)
    await Service._freeze_new_submission(AsyncMock(), generation)
    snapshot = generation.parameters[SNAPSHOT_KEY]
    body = json.loads(snapshot['body_json'])
    assert body['model'] == 'seedream-5.0-pro'
    assert body['resolution'] == resolution
    assert body['aspect_ratio'] == '16:9'
    assert 'quality' not in body and 'output_format' not in body
    assert snapshot['output_format'] == 'png'
    assert snapshot['endpoint'] == ('/v1/images/edits' if model.endswith('i2i') else '/v1/images/generations')


@pytest.mark.parametrize('model', ['seedream-5-pro-t2i', 'seedream-5-pro-i2i'])
def test_seedream_routes_allow_primary_and_preserve_previous_reserves(model):
    assert ['neironych', 'kie', 'nexus'] in route_options()[model]
    assert ['neironych', 'nexus', 'kie'] in route_options()[model]
    assert ['kie', 'nexus'] in route_options()[model]
    assert ['nexus', 'kie'] in route_options()[model]


@pytest.mark.parametrize('ratio,resolution,count', [('1:1', '4k', 0), ('5:4', '1k', 0), ('1:1', '2k', 9)])
async def test_seedream_unsupported_input_never_posts(ratio, resolution, count):
    def forbidden(request):
        pytest.fail('Unsupported input made a paid HTTP request')
    async with httpx.AsyncClient(base_url='https://example.test', transport=httpx.MockTransport(forbidden)) as http:
        client = NeironychImageClient('test-key', 'https://example.test', client=http)
        with pytest.raises(NeironychProviderError) as caught:
            await client.create_image(model='seedream-5.0-pro', prompt='A cup', aspect_ratio=ratio,
                resolution=resolution, image_urls=[f'https://example.test/{i}.jpg' for i in range(count)],
                idempotency_key='seedream-contract')
    assert caught.value.local_validation and caught.value.error_code == 'capability_mismatch'


async def test_seedream_eight_references_are_preserved():
    from app.providers.neironych_image import prepare_image_payload
    refs = [f'https://example.test/{i}.jpg' for i in range(8)]
    endpoint, payload = prepare_image_payload(model='seedream-5.0-pro', prompt='A cup',
        aspect_ratio='9:21', resolution='1k', image_urls=refs, idempotency_key='seedream-contract')
    assert endpoint == '/v1/images/edits'
    assert payload['images'] == [{'image_url': url} for url in refs]


@pytest.mark.parametrize('extra', [{'quality': 'ultra'}, {'nsfw_checker': True}])
async def test_seedream_does_not_discard_unsupported_controls(extra):
    from app.services.neironych_generation_provider import NeironychGenerationProviderService as Service
    generation = Generation(id=uuid.uuid4(), input_url=None, kind='generate', prompt='A cup',
        parameters={'_model_id': 'seedream-5-pro-t2i', 'aspect_ratio': '1:1', **extra})
    with pytest.raises(NeironychProviderError) as caught:
        await Service._freeze_new_submission(AsyncMock(), generation)
    assert caught.value.local_validation and caught.value.error_code == 'capability_mismatch'
    assert SNAPSHOT_KEY not in generation.parameters
