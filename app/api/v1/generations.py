from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import CurrentUserDep, RedisDep, SessionDep
from app.services.generations import GenerationService
from app.services.wallet import InsufficientBalanceError

router = APIRouter(prefix="/generations", tags=["generations"])


class CreateGenerationRequest(BaseModel):
    kind: Literal["text_to_image", "image_to_image", "text_to_video", "image_to_video"] = "text_to_image"
    prompt: str = Field(min_length=1, max_length=8000)
    input_url: str | None = Field(default=None, max_length=4000)
    parameters: dict[str, object] = Field(default_factory=dict)


@router.post("", status_code=202)
async def create_generation(
    payload: CreateGenerationRequest,
    user: CurrentUserDep,
    session: SessionDep,
    redis: RedisDep,
) -> dict[str, str]:
    try:
        generation = await GenerationService.create(
            session,
            redis,
            user_id=user.id,
            kind=payload.kind,
            prompt=payload.prompt,
            input_url=payload.input_url,
            cost_rox=GenerationService.price_for(payload.kind),
            parameters=payload.parameters,
        )
    except InsufficientBalanceError as exc:
        raise HTTPException(status_code=409, detail="Insufficient ROX") from exc
    return {"id": str(generation.id), "status": generation.status}
