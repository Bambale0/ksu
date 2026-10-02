from __future__ import annotations

import json

import httpx
import pytest

from app.providers.neironych_errors import NeironychProviderError, error_disposition
from app.providers.neironych_submission import freeze_submission, saved_body
from app.providers.neironych_video import NeironychVideoClient
from app.services.model_catalog import ModelCatalog
from app.services.model_ui_contract import build_public_model_ui_schema


@pytest.mark.parametrize(
    "code,status,expected",
    [
        ("request_already_submitted", 409, "uncertain"),
        ("idempotency_conflict", 409, "reject"),
        ("capability_mismatch", 409, "fallback"),
        ("media_asset_not_ready", 409, "reject"),
        ("invalid_request_contract", 422, "reject"),
        ("provider_rejected_request", 503, "reject"),
        ("submission_outcome_unknown", 503, "uncertain"),
        ("provider_response_invalid", 503, "uncertain"),
        ("provider_temporarily_unavailable", 503, "uncertain"),
        ("insufficient_balance", 402, "fallback"),
        ("provider_rate_limited", 429, "fallback"),
    ],
)
def test_error_disposition_uses_documented_semantics(code, status, expected):
    exc = NeironychProviderError(code, status_code=status, error_code=code)
    assert error_disposition(exc) == expected


def test_policy_never_bypasses_provider():
    exc = NeironychProviderError(
        "moderation rejection", status_code=402, error_code="insufficient_balance"
    )
    assert error_disposition(exc) == "reject"


def test_snapshot_binds_wire_body_model_key_and_origin():
    payload = {"prompt": "Scene", "duration": 4, "aspect_ratio": "9:16"}
    snapshot = freeze_submission(
        model="seedance-2.5", payload=payload, key="request-key-001", base_url="https://api.example"
    )
    original = saved_body(
        snapshot, model="seedance-2.5", key="request-key-001", base_url="https://api.example"
    )
    payload["prompt"] = "changed"
    assert json.loads(original)["prompt"] == "Scene"
    with pytest.raises(ValueError):
        saved_body(
            snapshot, model="seedance-2.5", key="request-key-002", base_url="https://api.example"
        )
    with pytest.raises(ValueError):
        saved_body(
            snapshot, model="seedance-2.5", key="request-key-001", base_url="https://other.example"
        )
    corrupt = {**snapshot, "body_json": original + " "}
    with pytest.raises(ValueError):
        saved_body(
            corrupt, model="seedance-2.5", key="request-key-001", base_url="https://api.example"
        )


@pytest.mark.asyncio
async def test_video_replay_sends_saved_bytes_without_new_normalization(monkeypatch):
    received = []

    def handler(request):
        received.append((request.content, request.headers["Idempotency-Key"]))
        return httpx.Response(202, json={"request_id": "accepted-original-id"})

    body = '{"model":"seedance-2.5","prompt":"original","duration":4,"aspect_ratio":"16:9"}'

    def changed_normalizer(*args):
        raise AssertionError("replay must not use a new normalizer")

    monkeypatch.setattr(
        "app.providers.neironych_video.normalize_neironych_video_input", changed_normalizer
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://api.example"
    ) as http:
        client = NeironychVideoClient("test", "https://api.example", client=http)
        for _ in range(2):
            assert (
                await client.create_video(
                    model="seedance-2.5",
                    payload={},
                    idempotency_key="request-key-001",
                    request_body=body,
                )
                == "accepted-original-id"
            )
    assert received == [(body.encode(), "request-key-001")] * 2


def test_nano_pro_schema_omits_auto_without_changing_nano2():
    for model, has_auto in [("nano-banana-pro", False), ("nano-banana-2", True)]:
        ui = build_public_model_ui_schema(ModelCatalog.get(model).public_dict())
        field = next(item for item in ui["fields"] if item["name"] == "aspect_ratio")
        assert ("auto" in field["suggestions"]) is has_auto


@pytest.mark.parametrize(
    "code,status",
    [("content_policy_violation", 403), ("content_filter", 403), ("unrecognized_error", 403)],
)
def test_unknown_or_policy_403_never_bypasses_to_fallback(code, status):
    assert (
        error_disposition(
            NeironychProviderError("Request rejected", status_code=status, error_code=code)
        )
        == "reject"
    )


def test_admin_retry_cannot_poll_faster_than_provider_contract(monkeypatch):
    from app.core.config import settings
    from app.services.seedance_admin_tasks import _retry_delay

    monkeypatch.setattr(settings, "nexus_test_retry_max_seconds", 3)
    assert _retry_delay(1) >= 10
