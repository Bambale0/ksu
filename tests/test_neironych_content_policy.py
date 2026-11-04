import httpx
import pytest

from app.providers.neironych_errors import NeironychProviderError, error_disposition, safe_user_error_message
from app.providers.neironych_image import NeironychImageClient


async def test_content_policy_rejection_is_terminal_with_safe_user_copy():
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(422, json={"error": {
            "type": "content_policy_violation",
            "message": "private prompt https://private.example/ref?token=secret-value",
        }})

    async with httpx.AsyncClient(base_url="https://provider.test", transport=httpx.MockTransport(respond)) as http:
        client = NeironychImageClient("test-key", "https://provider.test", client=http)
        with pytest.raises(NeironychProviderError) as caught:
            await client.create_image(model="seedream-5.0-pro", prompt="Cup", aspect_ratio="3:4",
                                      resolution="1k", image_urls=[], idempotency_key="policy-regression-test")
    assert len(calls) == 1
    assert error_disposition(caught.value) == "reject"
    assert safe_user_error_message(caught.value) == (
        "Запрос не прошёл проверку содержимого. Измените описание или выберите другое фото."
    )
