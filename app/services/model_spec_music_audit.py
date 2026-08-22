from __future__ import annotations

from typing import Any

_INSTALLED = False


def _strict_optional_bool(raw: dict[str, Any], key: str) -> None:
    if key not in raw:
        return
    value = raw[key]
    if not isinstance(value, bool):
        from app.services.music_generation import MusicGenerationError

        raise MusicGenerationError(f"{key} должен быть boolean")


def install_model_spec_music_audit() -> None:
    """Harden Suno input typing before the legacy normalizer coerces values.

    JSON clients must send real booleans. Python's bool("false") is True, so
    allowing arbitrary scalar coercion could switch Simple Mode into Custom Mode
    and change which fields Kie requires. Validate the public contract first, then
    let the existing music service perform conditional field normalization.
    """

    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    from app.services import music_generation as music

    previous_prepare = music.MusicGenerationService.prepare

    @classmethod
    def audited_prepare(
        cls: type[music.MusicGenerationService],
        parameters: dict[str, Any],
        prompt: str = "",
    ) -> tuple[dict[str, Any], Any]:
        raw = dict(parameters or {})
        _strict_optional_bool(raw, "customMode")
        _strict_optional_bool(raw, "instrumental")

        custom_mode = raw.get("customMode", False)
        text = str(raw.get("prompt") or prompt or "").strip()
        if custom_mode is False and len(text) > 500:
            raise music.MusicGenerationError(
                "В простом режиме Suno промпт должен быть не длиннее 500 символов"
            )

        clean, price = previous_prepare(parameters, prompt)

        # The previous service already validates Custom Mode's conditional
        # requirements and ranges. Assert normalized booleans remain booleans so
        # later provider submission cannot observe ambiguous scalar values.
        for key in ("customMode", "instrumental"):
            if not isinstance(clean.get(key), bool):
                raise music.MusicGenerationError(f"{key} должен быть boolean")
        return clean, price

    music.MusicGenerationService.prepare = audited_prepare
