from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Literal

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import Generation
from app.providers.kie_pinterest_quality import (
    KiePinterestQualityClient,
    PinterestQualityProviderError,
)
from app.services.abuse_protection import AbuseProtectionService
from app.services.generation_reliability import GenerationOutboxService
from app.services.media_assets import MediaAssetService
from app.services.provider_media_transport import (
    ProviderMediaTransport,
    ProviderMediaTransportError,
)

logger = logging.getLogger(__name__)

PinterestQualityOutcome = Literal["finalized", "retry_generation"]


class PinterestQualityGateError(RuntimeError):
    pass


class PinterestRepeatQualityGate:
    MAX_ISSUES = 8
    MAX_ISSUE_LENGTH = 240
    MAX_RETRY_INSTRUCTION = 900
    MIN_SCENE_SCORE = 74
    MIN_IDENTITY_SCORE = 80
    MIN_POSE_SCORE = 72
    MIN_COMPOSITION_SCORE = 72
    MIN_OVERALL_SCORE = 76

    @classmethod
    def is_pending(cls, generation: Generation) -> bool:
        params = generation.parameters or {}
        return generation.action_type == "pinterest_repeat" and bool(params.get("_quality_pending"))

    @classmethod
    def _generation_inputs(cls, generation: Generation) -> tuple[str, list[str], list[str], str]:
        params = generation.parameters or {}
        raw_inputs = params.get("image_input")
        if not isinstance(raw_inputs, list):
            raise PinterestQualityGateError("Pinterest repeat has no image_input for quality gate")
        inputs = [str(item).strip() for item in raw_inputs if str(item).strip()]
        if len(inputs) < 2:
            raise PinterestQualityGateError("Pinterest repeat needs scene and identity references")
        candidate_urls_raw = params.get("_quality_candidate_result_urls")
        if not isinstance(candidate_urls_raw, list):
            raise PinterestQualityGateError("Pinterest repeat has no candidate result")
        candidate_urls = [str(item).strip() for item in candidate_urls_raw if str(item).strip()]
        if not candidate_urls:
            raise PinterestQualityGateError("Pinterest repeat candidate result is empty")
        task_id = str(params.get("_quality_candidate_task_id") or generation.external_id or "").strip()
        return inputs[0], inputs[1:6], candidate_urls, task_id

    @classmethod
    def normalize_evaluation(cls, raw: dict[str, Any], *, model: str) -> dict[str, Any]:
        def score(name: str) -> int:
            try:
                value = int(raw.get(name))
            except (TypeError, ValueError) as exc:
                raise PinterestQualityGateError(f"Quality evaluator returned invalid {name}") from exc
            return max(0, min(100, value))

        scene = score("scene_match_score")
        identity = score("identity_match_score")
        pose = score("pose_match_score")
        composition = score("composition_match_score")
        anatomy_ok = raw.get("anatomy_ok")
        if not isinstance(anatomy_ok, bool):
            raise PinterestQualityGateError("Quality evaluator returned invalid anatomy_ok")

        issues_raw = raw.get("issues")
        if not isinstance(issues_raw, list):
            raise PinterestQualityGateError("Quality evaluator returned invalid issues")
        issues = [
            str(item).strip()[: cls.MAX_ISSUE_LENGTH]
            for item in issues_raw[: cls.MAX_ISSUES]
            if str(item).strip()
        ]
        retry_instruction = str(raw.get("retry_instruction") or "").strip()[: cls.MAX_RETRY_INSTRUCTION]
        overall = round(identity * 0.30 + scene * 0.25 + pose * 0.25 + composition * 0.20, 1)
        passed = bool(
            anatomy_ok
            and scene >= cls.MIN_SCENE_SCORE
            and identity >= cls.MIN_IDENTITY_SCORE
            and pose >= cls.MIN_POSE_SCORE
            and composition >= cls.MIN_COMPOSITION_SCORE
            and overall >= cls.MIN_OVERALL_SCORE
        )
        return {
            "model": model,
            "scene_match_score": scene,
            "identity_match_score": identity,
            "pose_match_score": pose,
            "composition_match_score": composition,
            "anatomy_ok": anatomy_ok,
            "overall_score": overall,
            "passed": passed,
            "issues": issues,
            "retry_instruction": retry_instruction,
        }

    @staticmethod
    def _selection_score(evaluation: dict[str, Any]) -> float:
        score = float(evaluation.get("overall_score") or 0)
        if not bool(evaluation.get("anatomy_ok")):
            score -= 20.0
        return score

    @classmethod
    async def _evaluate(
        cls,
        redis: Redis,
        *,
        scene_url: str,
        identity_urls: list[str],
        candidate_url: str,
    ) -> dict[str, Any]:
        await AbuseProtectionService.provider_submission_gate(redis, "kie-pinterest-repeat-quality")
        prepared = await ProviderMediaTransport.prepare(
            {
                "scene_url": scene_url,
                "identity_urls": identity_urls,
                "candidate_url": candidate_url,
            }
        )
        client = KiePinterestQualityClient(settings.kie_api_key, settings.kie_base_url)
        try:
            result = await client.evaluate(
                scene_url=str(prepared.get("scene_url") or ""),
                identity_urls=[str(item) for item in prepared.get("identity_urls") or []],
                candidate_url=str(prepared.get("candidate_url") or ""),
            )
        finally:
            await client.aclose()
        evaluation = cls.normalize_evaluation(result.payload, model=result.model)
        await AbuseProtectionService.record_provider_success(redis, "kie-pinterest-repeat-quality")
        return evaluation

    @classmethod
    async def _finalize(
        cls,
        session: AsyncSession,
        generation: Generation,
        *,
        result_urls: list[str],
        selected_task_id: str,
        gate_payload: dict[str, Any],
    ) -> PinterestQualityOutcome:
        params = dict(generation.parameters or {})
        params["_result_urls"] = result_urls
        params["_quality_gate"] = gate_payload
        params["_quality_pending"] = False
        for key in (
            "_quality_candidate_result_urls",
            "_quality_candidate_task_id",
            "_quality_retry_instruction",
            "_quality_initial_result_urls",
            "_quality_initial_task_id",
            "_quality_initial_evaluation",
        ):
            params.pop(key, None)
        generation.parameters = params
        generation.status = "succeeded"
        generation.error = None
        generation.result_url = result_urls[0]
        generation.updated_at = datetime.now(timezone.utc)
        await MediaAssetService.enqueue_results(session, generation, result_urls)
        await session.commit()
        await GenerationOutboxService.mark_generation_terminal(
            session,
            generation.id,
            failed=False,
        )
        logger.info(
            "Pinterest quality gate finalized generation=%s selected_task=%s status=%s",
            generation.id,
            selected_task_id,
            gate_payload.get("status"),
        )
        return "finalized"

    @classmethod
    async def _fail_open(
        cls,
        session: AsyncSession,
        generation: Generation,
        *,
        candidate_urls: list[str],
        task_id: str,
        error: str,
    ) -> PinterestQualityOutcome:
        params = generation.parameters or {}
        retry_count = int(params.get("_quality_retry_count") or 0)
        initial_urls = params.get("_quality_initial_result_urls")
        initial_evaluation = params.get("_quality_initial_evaluation")
        if retry_count >= 1 and isinstance(initial_urls, list) and initial_urls:
            # The first candidate has a completed evaluation, while the retry could
            # not be evaluated. Prefer the known candidate instead of an unchecked retry.
            selected_urls = [str(item) for item in initial_urls if str(item)]
            selected_task_id = str(params.get("_quality_initial_task_id") or task_id)
            selected = "initial"
        else:
            selected_urls = candidate_urls
            selected_task_id = task_id
            selected = "candidate"
        return await cls._finalize(
            session,
            generation,
            result_urls=selected_urls,
            selected_task_id=selected_task_id,
            gate_payload={
                "status": "skipped",
                "selected": selected,
                "reason": error[:600],
                "retry_count": retry_count,
                "initial_evaluation": initial_evaluation if isinstance(initial_evaluation, dict) else None,
            },
        )

    @classmethod
    async def process_pending(
        cls,
        session: AsyncSession,
        redis: Redis,
        generation: Generation,
    ) -> PinterestQualityOutcome:
        scene_url, identity_urls, candidate_urls, task_id = cls._generation_inputs(generation)
        params = dict(generation.parameters or {})
        retry_count = int(params.get("_quality_retry_count") or 0)

        try:
            evaluation = await cls._evaluate(
                redis,
                scene_url=scene_url,
                identity_urls=identity_urls,
                candidate_url=candidate_urls[0],
            )
        except Exception as exc:
            if AbuseProtectionService.availability_failure(exc):
                await AbuseProtectionService.record_provider_failure(
                    redis,
                    "kie-pinterest-repeat-quality",
                )
            if not isinstance(exc, (PinterestQualityProviderError, ProviderMediaTransportError)):
                logger.exception("Pinterest quality gate failed for %s", generation.id)
            return await cls._fail_open(
                session,
                generation,
                candidate_urls=candidate_urls,
                task_id=task_id,
                error=str(exc) or "quality evaluator unavailable",
            )

        if retry_count <= 0 and evaluation["passed"]:
            return await cls._finalize(
                session,
                generation,
                result_urls=candidate_urls,
                selected_task_id=task_id,
                gate_payload={
                    "status": "passed",
                    "selected": "initial",
                    "retry_count": 0,
                    "evaluations": [evaluation],
                },
            )

        if retry_count <= 0:
            retry_instruction = str(evaluation.get("retry_instruction") or "").strip()
            if not retry_instruction:
                retry_instruction = (
                    "Correct the visible scene, pose, framing and identity-consistency issues from "
                    "the previous candidate while preserving the supplied PERSON_IDENTITY."
                )
            rejected = [
                str(item)
                for item in params.get("_quality_rejected_task_ids") or []
                if str(item)
            ]
            if task_id and task_id not in rejected:
                rejected.append(task_id)
            params.update(
                {
                    "_quality_pending": False,
                    "_quality_retry_count": 1,
                    "_quality_retry_instruction": retry_instruction,
                    "_quality_initial_result_urls": candidate_urls,
                    "_quality_initial_task_id": task_id,
                    "_quality_initial_evaluation": evaluation,
                    "_quality_rejected_task_ids": rejected[-4:],
                }
            )
            params.pop("_quality_candidate_result_urls", None)
            params.pop("_quality_candidate_task_id", None)
            generation.parameters = params
            generation.external_id = None
            generation.status = "retry"
            generation.error = None
            generation.updated_at = datetime.now(timezone.utc)
            await session.commit()
            logger.info(
                "Pinterest quality gate queued one corrective retry generation=%s score=%s",
                generation.id,
                evaluation.get("overall_score"),
            )
            return "retry_generation"

        initial_urls_raw = params.get("_quality_initial_result_urls")
        initial_eval_raw = params.get("_quality_initial_evaluation")
        initial_urls = (
            [str(item) for item in initial_urls_raw if str(item)]
            if isinstance(initial_urls_raw, list)
            else []
        )
        initial_evaluation = initial_eval_raw if isinstance(initial_eval_raw, dict) else {}
        use_retry = not initial_urls or cls._selection_score(evaluation) >= cls._selection_score(initial_evaluation)
        selected_urls = candidate_urls if use_retry else initial_urls
        selected = "retry" if use_retry else "initial"
        selected_task_id = task_id if use_retry else str(params.get("_quality_initial_task_id") or task_id)
        return await cls._finalize(
            session,
            generation,
            result_urls=selected_urls,
            selected_task_id=selected_task_id,
            gate_payload={
                "status": "best_of_two",
                "selected": selected,
                "retry_count": 1,
                "evaluations": [initial_evaluation, evaluation],
            },
        )
