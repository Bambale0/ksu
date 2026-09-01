from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

AiReferenceScenario = Literal["create", "hd", "edit"]
AiReferenceSubject = Literal["adult", "child", "pet"]


class AiReferenceError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AiReferenceGenerationRequest:
    model_id: str
    prompt: str
    parameters: dict[str, Any]


class AiReferenceService:
    """Server-owned generation recipes for the AI REFERENCE entry point."""

    MODEL_ID = "nano-banana-pro"
    MAX_CREATE_REFERENCES = 4
    MAX_INSTRUCTION_LENGTH = 1200

    _CREATE_PROMPTS: dict[AiReferenceSubject, str] = {
        "adult": (
            "Create a clean photorealistic identity reference of the same adult person shown in the uploaded photos. "
            "Preserve facial identity, face geometry, age, skin tone, eye color, hair color, body proportions and distinctive features. "
            "Use a natural neutral expression, realistic skin texture, soft studio light and a plain neutral background. "
            "Center the person in a clear head-and-shoulders composition. Do not beautify, stylize, change ethnicity, age or body features. "
            "If the references differ, prioritize the clearest frontal face."
        ),
        "child": (
            "Create a clean photorealistic identity reference of the same child shown in the uploaded photos. "
            "Preserve the child's exact facial identity, age, skin tone, eye color, hair color, proportions and distinctive features. "
            "Use a natural neutral expression, realistic skin texture, soft studio light, age-appropriate neutral clothing and a plain neutral background. "
            "Center the child in a clear head-and-shoulders composition. Do not add makeup, glamour styling, adult features or change age or body proportions. "
            "If the references differ, prioritize the clearest frontal face."
        ),
        "pet": (
            "Create a clean photorealistic identity reference of the same animal shown in the uploaded photos. "
            "Preserve species, breed traits, face shape, coat color and pattern, eye color, markings, proportions and distinctive features. "
            "Use a calm natural pose, soft studio light and a plain neutral background. Center the animal clearly and keep realistic fur detail. "
            "Do not stylize, humanize or change breed traits. If the references differ, prioritize the clearest frontal view."
        ),
    }

    _HD_PROMPT = (
        "Enhance the technical image quality only. Preserve the original identity, facial geometry, age, body proportions, pose, clothing, colors, "
        "composition, background and perspective. Reduce compression artifacts and noise, restore natural fine detail, improve sharpness and clarity, "
        "and produce a clean high-resolution result. Do not retouch the face, smooth skin, add makeup, change hairstyle, invent details or alter the style."
    )

    @classmethod
    def _references(cls, values: list[str]) -> list[str]:
        result: list[str] = []
        for value in values:
            item = str(value or "").strip()
            if item and item not in result:
                result.append(item)
        return result

    @classmethod
    def build_request(
        cls,
        *,
        scenario: AiReferenceScenario,
        reference_urls: list[str],
        subject: AiReferenceSubject | None = None,
        instruction: str | None = None,
    ) -> AiReferenceGenerationRequest:
        refs = cls._references(reference_urls)
        if scenario == "create":
            create_prompt = cls._CREATE_PROMPTS.get(subject) if subject is not None else None
            if create_prompt is None:
                raise AiReferenceError("Выберите: взрослый, детский или для животных")
            if not 1 <= len(refs) <= cls.MAX_CREATE_REFERENCES:
                raise AiReferenceError("Для создания референса добавьте от 1 до 4 фотографий")
            return AiReferenceGenerationRequest(
                model_id=cls.MODEL_ID,
                prompt=create_prompt,
                parameters={
                    "image_input": refs,
                    "aspect_ratio": "1:1" if subject == "pet" else "3:4",
                    "resolution": "2K",
                    "output_format": "png",
                },
            )

        if len(refs) != 1:
            raise AiReferenceError("Для этого сценария нужна одна фотография")

        if scenario == "hd":
            return AiReferenceGenerationRequest(
                model_id=cls.MODEL_ID,
                prompt=cls._HD_PROMPT,
                parameters={
                    "image_input": refs,
                    "aspect_ratio": "auto",
                    "resolution": "4K",
                    "output_format": "png",
                },
            )

        if scenario == "edit":
            edit = str(instruction or "").strip()
            if not edit:
                raise AiReferenceError("Опишите, что хотите изменить")
            if len(edit) > cls.MAX_INSTRUCTION_LENGTH:
                raise AiReferenceError("Описание изменений слишком длинное")
            prompt = (
                "Edit the uploaded reference according to the user's request below. Preserve the same person's or animal's identity, facial geometry, age, "
                "skin or coat tone, body proportions, pose and every detail that the user did not ask to change. Change only the requested attributes. "
                "Keep the result photorealistic and suitable as a consistent AI reference. Do not apply unrelated beautification or styling.\n\n"
                f"Requested edit: {edit}"
            )
            return AiReferenceGenerationRequest(
                model_id=cls.MODEL_ID,
                prompt=prompt,
                parameters={
                    "image_input": refs,
                    "aspect_ratio": "auto",
                    "resolution": "2K",
                    "output_format": "png",
                },
            )

        raise AiReferenceError("Неизвестный сценарий AI РЕФЕРЕНС")
