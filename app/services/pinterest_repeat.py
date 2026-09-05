from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx


class PinterestRepeatError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class PinterestRepeatGenerationRequest:
    model_id: str
    prompt: str
    parameters: dict[str, Any]


@dataclass(frozen=True, slots=True)
class PinterestResolvedReference:
    source_url: str
    reference_url: str


class _OpenGraphImageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.image_url: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "meta" or self.image_url:
            return
        values = {key.lower(): value for key, value in attrs if value is not None}
        property_name = (values.get("property") or values.get("name") or "").lower()
        if property_name == "og:image" and values.get("content"):
            self.image_url = values["content"]


class PinterestRepeatService:
    MODEL_ID = "nano-banana-pro"
    MAX_IDENTITY_REFERENCES = 5
    MAX_EXPRESSION_LENGTH = 240
    MAX_REDIRECTS = 5
    MAX_PINTEREST_HTML_BYTES = 2_000_000

    @staticmethod
    def _clean_url(value: str, *, label: str) -> str:
        cleaned = value.strip()
        parsed = urlparse(cleaned)
        if not cleaned or parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise PinterestRepeatError(f"{label} должен быть публичной HTTP(S)-ссылкой")
        return cleaned

    @staticmethod
    def _is_pinterest_host(hostname: str) -> bool:
        host = hostname.lower().rstrip(".")
        return host == "pin.it" or host == "pinterest.com" or host.endswith(".pinterest.com")

    @classmethod
    def validate_pinterest_url(cls, value: str) -> str:
        cleaned = cls._clean_url(value, label="Ссылка Pinterest")
        parsed = urlparse(cleaned)
        if parsed.scheme != "https" or not parsed.hostname or not cls._is_pinterest_host(parsed.hostname):
            raise PinterestRepeatError("Поддерживаются только HTTPS-ссылки pinterest.com и pin.it")
        return cleaned

    @staticmethod
    def _validate_pin_image_url(value: str) -> str:
        cleaned = value.strip()
        parsed = urlparse(cleaned)
        host = (parsed.hostname or "").lower().rstrip(".")
        if parsed.scheme != "https" or not (host == "pinimg.com" or host.endswith(".pinimg.com")):
            raise PinterestRepeatError("Pinterest вернул неподдерживаемую ссылку на изображение")
        return cleaned

    @classmethod
    async def resolve_reference(
        cls,
        value: str,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> PinterestResolvedReference:
        source_url = cls.validate_pinterest_url(value)
        current_url = source_url
        owns_client = client is None
        http_client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(8.0, connect=4.0),
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                    "AppleWebKit/605.1.15 Version/17.0 Mobile/15E148 Safari/604.1"
                ),
                "Accept": "text/html,application/xhtml+xml",
            },
            follow_redirects=False,
        )
        try:
            for _ in range(cls.MAX_REDIRECTS + 1):
                response = await http_client.get(current_url)
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if not location:
                        raise PinterestRepeatError("Pinterest вернул пустой redirect")
                    current_url = cls.validate_pinterest_url(urljoin(current_url, location))
                    continue

                response.raise_for_status()
                content_length = response.headers.get("content-length")
                if content_length:
                    try:
                        if int(content_length) > cls.MAX_PINTEREST_HTML_BYTES:
                            raise PinterestRepeatError("Страница Pinterest слишком большая")
                    except ValueError:
                        pass
                if len(response.content) > cls.MAX_PINTEREST_HTML_BYTES:
                    raise PinterestRepeatError("Страница Pinterest слишком большая")

                parser = _OpenGraphImageParser()
                parser.feed(response.text)
                if not parser.image_url:
                    raise PinterestRepeatError("Не удалось найти фото на странице Pinterest")
                return PinterestResolvedReference(
                    source_url=current_url,
                    reference_url=cls._validate_pin_image_url(parser.image_url),
                )
        except httpx.HTTPStatusError as exc:
            raise PinterestRepeatError(
                f"Pinterest недоступен: HTTP {exc.response.status_code}"
            ) from exc
        except httpx.HTTPError as exc:
            raise PinterestRepeatError("Не удалось загрузить страницу Pinterest") from exc
        finally:
            if owns_client:
                await http_client.aclose()

        raise PinterestRepeatError("Слишком много перенаправлений Pinterest")

    @classmethod
    def build_request(
        cls,
        *,
        scene_reference_url: str,
        identity_reference_urls: list[str],
        height_cm: int,
        weight_kg: int,
        expression: str | None = None,
    ) -> PinterestRepeatGenerationRequest:
        scene = cls._clean_url(scene_reference_url, label="Референс")
        identities = [
            cls._clean_url(value, label="Фото пользователя")
            for value in identity_reference_urls
            if value.strip()
        ]
        if not identities:
            raise PinterestRepeatError("Добавьте хотя бы одно своё фото")
        if len(identities) > cls.MAX_IDENTITY_REFERENCES:
            raise PinterestRepeatError(
                f"Можно добавить не больше {cls.MAX_IDENTITY_REFERENCES} своих фото"
            )
        if not 120 <= height_cm <= 230:
            raise PinterestRepeatError("Рост должен быть от 120 до 230 см")
        if not 30 <= weight_kg <= 250:
            raise PinterestRepeatError("Вес должен быть от 30 до 250 кг")

        expression_text = (expression or "").strip()
        if len(expression_text) > cls.MAX_EXPRESSION_LENGTH:
            raise PinterestRepeatError(
                f"Описание выражения лица — до {cls.MAX_EXPRESSION_LENGTH} символов"
            )
        expression_instruction = (
            f"Expression override: {expression_text}. Use this expression instead of the scene "
            "reference expression."
            if expression_text
            else "Expression: preserve the scene mood when possible without changing the person's identity."
        )

        identity_count = len(identities)
        identity_range = "IMAGE 2" if identity_count == 1 else f"IMAGES 2-{identity_count + 1}"
        prompt = f"""Recreate the supplied reference photo as faithfully as possible while replacing only the person with the identity from the user's photos.

REFERENCE ROLE CONTRACT — follow strictly:
- IMAGE 1 = SCENE_REFERENCE. Copy its pose, body placement, framing, camera angle, lens feel, crop, perspective, lighting direction and softness, environment, styling, wardrobe silhouette, color palette and overall composition. DO NOT copy the face or personal identity of the person in IMAGE 1.
- {identity_range} = PERSON_IDENTITY. These images show the same user. Preserve their facial structure, eyes, nose, mouth, jawline, skin tone, hair, distinctive features and natural body proportions. DO NOT copy backgrounds, camera framing or poses from identity images.

IDENTITY LOCK:
The final person must clearly be the same person shown in PERSON_IDENTITY and must not become a blend with the person from SCENE_REFERENCE. Do not beautify into a different face. Keep age and recognisable facial traits stable.

SCENE LOCK:
Match IMAGE 1 closely: reproduce the same pose, limb placement, head direction, body rotation, subject scale, subject position, camera height, crop, background geometry, lighting and visual mood. Preserve the original aspect ratio/framing rather than inventing a new composition.

BODY PROPORTIONS:
The user is approximately {height_cm} cm tall and {weight_kg} kg. Treat these numbers as soft proportion constraints and prioritise the natural build visible in PERSON_IDENTITY. Do not make the body unnaturally slimmer, larger, taller or shorter.

{expression_instruction}

QUALITY RULES:
Photorealistic, anatomically correct hands and limbs, coherent clothing, no duplicate people, no extra fingers, no face drift, no text, no watermark, no collage. Output one finished image only."""

        return PinterestRepeatGenerationRequest(
            model_id=cls.MODEL_ID,
            prompt=prompt,
            parameters={
                "image_input": [scene, *identities],
                "aspect_ratio": "auto",
                "resolution": "2K",
                "output_format": "png",
            },
        )
