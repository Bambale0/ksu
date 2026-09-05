from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from app.services.pinterest_repeat import PinterestRepeatError, PinterestRepeatService


ROOT = Path(__file__).resolve().parents[1]


def test_build_request_keeps_scene_and_identity_roles_separate() -> None:
    request = PinterestRepeatService.build_request(
        scene_reference_url="https://cdn.example.com/scene.jpg",
        identity_reference_urls=[
            "https://cdn.example.com/me-front.jpg",
            "https://cdn.example.com/me-side.jpg",
        ],
        height_cm=165,
        weight_kg=55,
        expression="спокойная уверенность",
    )

    assert request.model_id == "nano-banana-pro"
    assert request.parameters == {
        "image_input": [
            "https://cdn.example.com/scene.jpg",
            "https://cdn.example.com/me-front.jpg",
            "https://cdn.example.com/me-side.jpg",
        ],
        "aspect_ratio": "auto",
        "resolution": "2K",
        "output_format": "png",
    }
    assert "IMAGE 1 = SCENE_REFERENCE" in request.prompt
    assert "IMAGES 2-3 = PERSON_IDENTITY" in request.prompt
    assert "165 cm" in request.prompt
    assert "55 kg" in request.prompt
    assert "спокойная уверенность" in request.prompt
    assert "DO NOT copy the face or personal identity" in request.prompt


def test_build_request_accepts_scene_plus_five_identity_photos() -> None:
    identities = [f"https://cdn.example.com/me-{index}.jpg" for index in range(5)]
    request = PinterestRepeatService.build_request(
        scene_reference_url="https://cdn.example.com/scene.jpg",
        identity_reference_urls=identities,
        height_cm=170,
        weight_kg=70,
    )

    assert request.parameters["image_input"] == [
        "https://cdn.example.com/scene.jpg",
        *identities,
    ]
    assert "IMAGES 2-6 = PERSON_IDENTITY" in request.prompt


def test_build_request_rejects_more_than_five_identity_photos() -> None:
    with pytest.raises(PinterestRepeatError, match="не больше 5"):
        PinterestRepeatService.build_request(
            scene_reference_url="https://cdn.example.com/scene.jpg",
            identity_reference_urls=[f"https://cdn.example.com/me-{index}.jpg" for index in range(6)],
            height_cm=170,
            weight_kg=70,
        )


@pytest.mark.asyncio
async def test_resolve_reference_follows_only_pinterest_redirects_and_reads_og_image() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "pin.it":
            return httpx.Response(
                302,
                headers={"location": "https://www.pinterest.com/pin/123/"},
                request=request,
            )
        return httpx.Response(
            200,
            text=(
                '<html><head><meta property="og:image" '
                'content="https://i.pinimg.com/originals/aa/bb/cc/photo.jpg"></head></html>'
            ),
            headers={"content-type": "text/html"},
            request=request,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        resolved = await PinterestRepeatService.resolve_reference(
            "https://pin.it/example",
            client=client,
        )

    assert resolved.source_url == "https://www.pinterest.com/pin/123/"
    assert resolved.reference_url == "https://i.pinimg.com/originals/aa/bb/cc/photo.jpg"


@pytest.mark.asyncio
async def test_resolve_reference_blocks_redirect_outside_pinterest() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            302,
            headers={"location": "https://127.0.0.1/private"},
            request=request,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(PinterestRepeatError, match="pinterest.com и pin.it"):
            await PinterestRepeatService.resolve_reference(
                "https://pin.it/example",
                client=client,
            )


@pytest.mark.asyncio
async def test_resolve_reference_rejects_oversized_pinterest_page() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"x" * (PinterestRepeatService.MAX_PINTEREST_HTML_BYTES + 1),
            request=request,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(PinterestRepeatError, match="слишком большая"):
            await PinterestRepeatService.resolve_reference(
                "https://www.pinterest.com/pin/123/",
                client=client,
            )


@pytest.mark.asyncio
async def test_download_reference_image_accepts_only_pinimg_images() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"fake-image-bytes",
            headers={"content-type": "image/jpeg"},
            request=request,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        downloaded = await PinterestRepeatService.download_reference_image(
            "https://i.pinimg.com/originals/aa/bb/photo.jpg",
            client=client,
        )

    assert downloaded.content == b"fake-image-bytes"
    assert downloaded.content_type == "image/jpeg"
    assert downloaded.filename == "photo.jpg"


@pytest.mark.asyncio
async def test_download_reference_image_blocks_redirect_outside_pinimg() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            302,
            headers={"location": "https://example.com/redirected.jpg"},
            request=request,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(PinterestRepeatError, match="неподдерживаемую ссылку"):
            await PinterestRepeatService.download_reference_image(
                "https://i.pinimg.com/originals/aa/bb/photo.jpg",
                client=client,
            )


@pytest.mark.asyncio
async def test_download_reference_image_rejects_non_image_payload() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text="<html>not an image</html>",
            headers={"content-type": "text/html"},
            request=request,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(PinterestRepeatError, match="формат изображения"):
            await PinterestRepeatService.download_reference_image(
                "https://i.pinimg.com/originals/aa/bb/photo.jpg",
                client=client,
            )


def test_pinterest_repeat_surface_is_wired_into_catalog_and_api() -> None:
    catalog = (ROOT / "frontend/mini-app/components/catalog-feature-hub.tsx").read_text(
        encoding="utf-8"
    )
    page = (ROOT / "frontend/mini-app/app/pinterest-repeat/page.tsx").read_text(encoding="utf-8")
    api = (ROOT / "frontend/mini-app/lib/pinterest-repeat-api.ts").read_text(encoding="utf-8")
    router = (ROOT / "app/api/router.py").read_text(encoding="utf-8")
    endpoint = (ROOT / "app/api/v1/pinterest_repeat.py").read_text(encoding="utf-8")

    assert 'id: "pinterest-repeat"' in catalog
    assert 'href: "/mini-app/pinterest-repeat/"' in catalog
    assert 'title="Повтори фото с Pinterest"' in page
    assert "identityPhotos.length <= 5" in page
    assert 'accept="image/*,.heic,.heif"' in page
    assert '"/api/v1/pinterest-repeat/resolve"' in api
    assert '"/api/v1/pinterest-repeat/quote"' in api
    assert '"/api/v1/pinterest-repeat/run"' in api
    assert "api_router.include_router(pinterest_repeat.router)" in router
    assert "ReferenceStaticStorage.persist_stream" in endpoint
    assert 'source="pinterest_repeat"' in endpoint
