from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest

from app.providers.kie import KieTask
from app.providers.kie_pinterest_quality import KiePinterestQualityClient
from app.services.generation_provider import GenerationProviderService
from app.services.pinterest_quality_gate import PinterestRepeatQualityGate


class FakeSession:
    def __init__(self, scalar_result=None) -> None:
        self.scalar_result = scalar_result
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1

    async def scalar(self, _statement):
        return self.scalar_result


def generation(*, retry_count: int = 0):
    params = {
        "_model_id": "nano-banana-pro",
        "image_input": [
            "https://roxy.example/scene.jpg",
            "https://roxy.example/me-front.jpg",
            "https://roxy.example/me-side.jpg",
        ],
    }
    if retry_count:
        params["_quality_retry_count"] = retry_count
    return SimpleNamespace(
        id=uuid4(),
        user_id=uuid4(),
        action_type="pinterest_repeat",
        status="generating",
        prompt="ORIGINAL RECIPE PROMPT",
        parameters=params,
        external_id="task-initial",
        result_url=None,
        error=None,
        updated_at=None,
        cost_rox=12,
        source_feed_gen_id=None,
    )


def evaluation(*, passed: bool, overall: float, anatomy_ok: bool = True):
    return {
        "model": "gemini-2.5-pro",
        "scene_match_score": 90 if passed else 60,
        "identity_match_score": 92 if passed else 70,
        "pose_match_score": 88 if passed else 55,
        "composition_match_score": 89 if passed else 60,
        "anatomy_ok": anatomy_ok,
        "overall_score": overall,
        "passed": passed,
        "issues": [] if passed else ["pose drift"],
        "retry_instruction": "Match the reference pose and crop more closely.",
    }


@pytest.mark.asyncio
async def test_quality_provider_sends_scene_identity_and_candidate_roles() -> None:
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.update(request.read() and __import__("json").loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": {
                                "scene_match_score": 91,
                                "identity_match_score": 93,
                                "pose_match_score": 89,
                                "composition_match_score": 90,
                                "anatomy_ok": True,
                                "issues": [],
                                "retry_instruction": "No correction needed.",
                            }
                        }
                    }
                ]
            },
            request=request,
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.kie.test",
    ) as http_client:
        client = KiePinterestQualityClient("", client=http_client)
        result = await client.evaluate(
            scene_url="https://cdn.example/scene.jpg",
            identity_urls=["https://cdn.example/me-1.jpg", "https://cdn.example/me-2.jpg"],
            candidate_url="https://cdn.example/result.jpg",
        )

    assert result.model == "gemini-2.5-pro"
    content = captured["messages"][1]["content"]
    image_urls = [part["image_url"]["url"] for part in content if part.get("type") == "image_url"]
    assert image_urls == [
        "https://cdn.example/scene.jpg",
        "https://cdn.example/me-1.jpg",
        "https://cdn.example/me-2.jpg",
        "https://cdn.example/result.jpg",
    ]
    assert captured["response_format"]["json_schema"]["strict"] is True


def test_quality_thresholds_are_strict_and_bounded() -> None:
    passed = PinterestRepeatQualityGate.normalize_evaluation(
        {
            "scene_match_score": 80,
            "identity_match_score": 90,
            "pose_match_score": 80,
            "composition_match_score": 80,
            "anatomy_ok": True,
            "issues": [],
            "retry_instruction": "",
        },
        model="gemini-2.5-pro",
    )
    assert passed["passed"] is True
    assert passed["overall_score"] >= PinterestRepeatQualityGate.MIN_OVERALL_SCORE

    failed = PinterestRepeatQualityGate.normalize_evaluation(
        {
            "scene_match_score": 100,
            "identity_match_score": 100,
            "pose_match_score": 100,
            "composition_match_score": 100,
            "anatomy_ok": False,
            "issues": ["broken hand"],
            "retry_instruction": "fix anatomy",
        },
        model="gemini-2.5-pro",
    )
    assert failed["passed"] is False


@pytest.mark.asyncio
async def test_first_kie_success_stages_quality_instead_of_terminal_success(monkeypatch) -> None:
    gen = generation()
    session = FakeSession()
    requeued = []

    async def fake_requeue(_session, generation_id, *, reason=""):
        requeued.append((generation_id, reason))

    monkeypatch.setattr(
        "app.services.generation_provider.GenerationOutboxService.requeue_generation",
        fake_requeue,
    )
    await GenerationProviderService.apply_kie_task(
        session,
        gen,
        KieTask(
            task_id="task-initial",
            state="success",
            result_urls=["https://cdn.example/initial.png"],
        ),
    )

    assert gen.status == "retry"
    assert gen.result_url is None
    assert gen.parameters["_quality_pending"] is True
    assert gen.parameters["_quality_candidate_result_urls"] == ["https://cdn.example/initial.png"]
    assert requeued and requeued[0][0] == gen.id


@pytest.mark.asyncio
async def test_low_quality_queues_exactly_one_corrective_retry_without_mutating_recipe(monkeypatch) -> None:
    gen = generation()
    gen.status = "retry"
    gen.parameters.update(
        {
            "_quality_pending": True,
            "_quality_candidate_task_id": "task-initial",
            "_quality_candidate_result_urls": ["https://cdn.example/initial.png"],
        }
    )
    original_prompt = gen.prompt
    session = FakeSession()

    async def fake_evaluate(*_args, **_kwargs):
        return evaluation(passed=False, overall=62.0)

    monkeypatch.setattr(PinterestRepeatQualityGate, "_evaluate", fake_evaluate)
    outcome = await PinterestRepeatQualityGate.process_pending(session, object(), gen)

    assert outcome == "retry_generation"
    assert gen.status == "retry"
    assert gen.external_id is None
    assert gen.prompt == original_prompt
    assert gen.parameters["_quality_retry_count"] == 1
    assert gen.parameters["_quality_retry_instruction"]
    assert gen.parameters["_quality_rejected_task_ids"] == ["task-initial"]
    assert gen.parameters["_quality_initial_result_urls"] == ["https://cdn.example/initial.png"]


@pytest.mark.asyncio
async def test_second_candidate_chooses_best_and_never_schedules_third_retry(monkeypatch) -> None:
    gen = generation(retry_count=1)
    gen.status = "retry"
    gen.external_id = "task-retry"
    gen.parameters.update(
        {
            "_quality_pending": True,
            "_quality_candidate_task_id": "task-retry",
            "_quality_candidate_result_urls": ["https://cdn.example/retry.png"],
            "_quality_initial_task_id": "task-initial",
            "_quality_initial_result_urls": ["https://cdn.example/initial.png"],
            "_quality_initial_evaluation": evaluation(passed=False, overall=68.0),
        }
    )
    session = FakeSession()

    async def fake_evaluate(*_args, **_kwargs):
        return evaluation(passed=False, overall=72.0)

    async def fake_enqueue(_session, _generation, _urls):
        return None

    async def fake_terminal(_session, _generation_id, *, failed, error=""):
        assert failed is False

    monkeypatch.setattr(PinterestRepeatQualityGate, "_evaluate", fake_evaluate)
    monkeypatch.setattr(
        "app.services.pinterest_quality_gate.MediaAssetService.enqueue_results",
        fake_enqueue,
    )
    monkeypatch.setattr(
        "app.services.pinterest_quality_gate.GenerationOutboxService.mark_generation_terminal",
        fake_terminal,
    )
    outcome = await PinterestRepeatQualityGate.process_pending(session, object(), gen)

    assert outcome == "finalized"
    assert gen.status == "succeeded"
    assert gen.result_url == "https://cdn.example/retry.png"
    assert gen.parameters["_quality_gate"]["selected"] == "retry"
    assert gen.parameters["_quality_gate"]["retry_count"] == 1
    assert "_quality_retry_instruction" not in gen.parameters


def test_corrective_instruction_changes_only_provider_prompt(monkeypatch) -> None:
    gen = generation(retry_count=1)
    gen.parameters["_quality_retry_instruction"] = "Move the right arm and match the crop."
    monkeypatch.setattr(
        "app.services.generation_provider.ReferenceResolver.generation_context",
        lambda _generation: SimpleNamespace(
            provider_input={
                "prompt": "ORIGINAL RECIPE PROMPT",
                "image_input": ["scene", "identity"],
            }
        ),
    )

    provider_input = GenerationProviderService._input_for(gen)

    assert gen.prompt == "ORIGINAL RECIPE PROMPT"
    assert provider_input["prompt"].startswith("ORIGINAL RECIPE PROMPT")
    assert "CORRECTIVE RETRY" in provider_input["prompt"]
    assert "Move the right arm" in provider_input["prompt"]


def test_stale_rejected_provider_task_cannot_rebind_corrective_generation() -> None:
    gen = generation(retry_count=1)
    gen.parameters["_quality_rejected_task_ids"] = ["task-initial"]
    gen.external_id = None
    gen.status = "retry"

    assert GenerationProviderService._is_rejected_quality_task(gen, "task-initial") is True
    assert GenerationProviderService._is_rejected_quality_task(gen, "task-retry") is False


@pytest.mark.asyncio
async def test_corrective_provider_failure_falls_back_without_wallet_refund(monkeypatch) -> None:
    gen = generation(retry_count=1)
    gen.parameters.update(
        {
            "_quality_initial_result_urls": ["https://cdn.example/initial.png"],
            "_quality_initial_task_id": "task-initial",
            "_quality_initial_evaluation": evaluation(passed=False, overall=67.0),
        }
    )
    session = FakeSession(scalar_result=gen)

    async def fake_enqueue(_session, _generation, _urls):
        return None

    async def fake_terminal(_session, _generation_id, *, failed, error=""):
        assert failed is False

    async def wallet_must_not_be_called(*_args, **_kwargs):
        raise AssertionError("corrective retry must not create a wallet refund/debit")

    monkeypatch.setattr(
        "app.services.generation_provider.MediaAssetService.enqueue_results",
        fake_enqueue,
    )
    monkeypatch.setattr(
        "app.services.generation_provider.GenerationOutboxService.mark_generation_terminal",
        fake_terminal,
    )
    monkeypatch.setattr(
        "app.services.generation_provider.WalletService.credit",
        wallet_must_not_be_called,
    )

    await GenerationProviderService.fail_and_refund(session, gen.id, "corrective provider failed")

    assert gen.status == "succeeded"
    assert gen.result_url == "https://cdn.example/initial.png"
    assert gen.parameters["_quality_gate"]["status"] == "retry_failed"
    assert gen.parameters["_quality_gate"]["selected"] == "initial"
