from __future__ import annotations

import asyncio
from pathlib import Path

from app.providers.kie_prompt_tools import KiePromptToolsClient, PromptToolProviderResult
from app.providers.tanyapi_photo_prompt import PRIMARY_MODEL, build_photo_prompt
from app.providers.tanyapi_video_prompt import (
    VIDEO_MODEL,
    _download_video_bytes,
    build_video_prompt,
)
from app.services.feed_static import FeedStaticStorage
from app.services.photo_analysis_media import image_source_to_analysis_input
from app.services.reference_static import ReferenceStaticStorage
from app.services.video_prompt_media import probe_video_duration_seconds

_INSTALLED = False


def _local_media(value: str) -> bool:
    return ReferenceStaticStorage.is_local_url(value) or FeedStaticStorage.is_local_url(value)


def _local_media_path(value: str) -> Path | None:
    return ReferenceStaticStorage.path_for_url(value) or FeedStaticStorage.path_for_url(value)


def install_tanyapi_prompt_contract() -> None:
    """Port tanyapi's working photo/video prompt providers without changing ROXY shell."""

    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    from app.services import prompt_tools as prompt_module

    original_safe_media_url = prompt_module.PromptToolService._safe_media_url
    original_build_prompt = KiePromptToolsClient.build_prompt

    def safe_media_url(value: str, *, kind: str) -> str:
        clean = str(value or "").strip()
        if _local_media(clean):
            path = _local_media_path(clean)
            if path is None or not path.is_file() or path.stat().st_size <= 0:
                raise ValueError(f"Stored {kind} reference is missing")
            return clean
        return original_safe_media_url(clean, kind=kind)

    async def analyze_image(
        self: KiePromptToolsClient,
        *,
        image_url: str,
        instruction: str = "",
    ) -> PromptToolProviderResult:
        prepared = image_source_to_analysis_input(image_url)
        if not prepared:
            raise ValueError("image_url is required")
        return await build_photo_prompt(
            self._client,
            image_url=prepared,
            instruction=instruction,
        )

    async def build_prompt(
        self: KiePromptToolsClient,
        *,
        text: str,
        image_url: str | None = None,
        audio_url: str | None = None,
    ) -> PromptToolProviderResult:
        if image_url and not audio_url:
            prepared = image_source_to_analysis_input(image_url)
            if not prepared:
                raise ValueError("image_url is required")
            return await build_photo_prompt(
                self._client,
                image_url=prepared,
                instruction=text,
            )
        return await original_build_prompt(
            self,
            text=text,
            image_url=image_url,
            audio_url=audio_url,
        )

    async def build_video(
        self: KiePromptToolsClient,
        *,
        video_url: str,
        instruction: str = "",
        duration_seconds: int | None = None,
    ) -> PromptToolProviderResult:
        # Telegram supplied trusted media duration in tanyapi. Mini App uploads do
        # not, so inspect the actual provider transport before GPT-5.5. This also
        # enforces the 30 MB source limit up front and lets the frame fallback reuse
        # the same bytes instead of downloading the clip a second time.
        video_bytes = await _download_video_bytes(self._client, video_url)
        actual_duration = await asyncio.to_thread(
            probe_video_duration_seconds,
            video_bytes,
        )
        return await build_video_prompt(
            self._client,
            video_url=video_url,
            instruction=instruction,
            duration_seconds=actual_duration,
            video_bytes=video_bytes,
        )

    prompt_module.PromptToolService._safe_media_url = staticmethod(safe_media_url)  # type: ignore[method-assign]
    prompt_module._TOOL_MODEL["image_analysis"] = PRIMARY_MODEL
    prompt_module._TOOL_MODEL["video_prompt"] = VIDEO_MODEL
    KiePromptToolsClient.analyze_image = analyze_image  # type: ignore[method-assign]
    KiePromptToolsClient.build_prompt = build_prompt  # type: ignore[method-assign]
    KiePromptToolsClient.build_video_prompt = build_video  # type: ignore[method-assign]
