from __future__ import annotations

import base64
import itertools
import json
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, Response

app = FastAPI(title="ROXY E2E fake provider")
_counter = itertools.count(1)
_tasks: dict[str, dict[str, Any]] = {}
_invoices: dict[str, dict[str, Any]] = {}

_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def _task(prefix: str, payload: dict[str, Any]) -> str:
    task_id = f"{prefix}-{next(_counter)}"
    _tasks[task_id] = payload
    return task_id


@app.get("/health")
async def health() -> dict[str, bool]:
    return {"ok": True}


@app.get("/media/result.png")
async def image_result() -> Response:
    return Response(_PNG, media_type="image/png")


@app.get("/media/result.mp3")
async def audio_result() -> Response:
    # A tiny deterministic payload is enough for browser/network and media URL checks.
    return Response(b"ID3\x04\x00\x00\x00\x00\x00\x00", media_type="audio/mpeg")


@app.get("/checkout/{payment_id}")
async def checkout(payment_id: str) -> HTMLResponse:
    return HTMLResponse(f"<html><body><h1>E2E checkout {payment_id}</h1></body></html>")


@app.post("/api/v1/jobs/createTask")
async def create_task(request: Request) -> dict[str, Any]:
    payload = await request.json()
    task_id = _task("job", payload)
    return {"code": 200, "msg": "success", "data": {"taskId": task_id}}


@app.get("/api/v1/jobs/recordInfo")
async def task_info(taskId: str) -> dict[str, Any]:  # noqa: N803 - provider contract
    payload = _tasks.get(taskId, {})
    model = str(payload.get("model") or "")
    media_url = "http://127.0.0.1:18081/media/result.png"
    if "video" in model.lower() or "kling" in model.lower() or "wan/" in model.lower():
        # The application accepts provider URLs independently from MIME inference.
        # Keeping the PNG endpoint makes the fake provider dependency-free.
        media_url = "http://127.0.0.1:18081/media/result.png"
    return {
        "code": 200,
        "msg": "success",
        "data": {
            "taskId": taskId,
            "state": "success",
            "resultJson": json.dumps({"resultUrls": [media_url]}),
        },
    }


@app.post("/api/v1/veo/generate")
async def create_veo(request: Request) -> dict[str, Any]:
    payload = await request.json()
    task_id = _task("veo", payload)
    return {"code": 200, "msg": "success", "data": {"taskId": task_id}}


@app.get("/api/v1/veo/record-info")
async def veo_info(taskId: str) -> dict[str, Any]:  # noqa: N803 - provider contract
    return {
        "code": 200,
        "msg": "success",
        "data": {
            "taskId": taskId,
            "successFlag": 1,
            "response": {
                "resultUrls": ["http://127.0.0.1:18081/media/result.png"],
            },
        },
    }


@app.post("/api/v1/generate")
async def create_music(request: Request) -> dict[str, Any]:
    payload = await request.json()
    task_id = _task("music", payload)
    return {"code": 200, "msg": "success", "data": {"taskId": task_id}}


@app.get("/api/v1/generate/record-info")
async def music_info(taskId: str) -> dict[str, Any]:  # noqa: N803 - provider contract
    return {
        "code": 200,
        "msg": "success",
        "data": {
            "taskId": taskId,
            "status": "SUCCESS",
            "response": {
                "sunoData": [
                    {
                        "id": f"track-{taskId}",
                        "audioUrl": "http://127.0.0.1:18081/media/result.mp3",
                        "streamAudioUrl": "http://127.0.0.1:18081/media/result.mp3",
                        "title": "ROXY E2E Track",
                        "modelName": "V5_5",
                        "duration": 12,
                    }
                ]
            },
        },
    }


@app.post("/api/createInvoice")
async def crypto_create(request: Request) -> dict[str, Any]:
    payload = await request.json()
    invoice_id = str(next(_counter))
    row = {
        "invoice_id": invoice_id,
        "status": "active",
        "payload": str(payload.get("payload") or ""),
        "mini_app_invoice_url": f"http://127.0.0.1:18081/checkout/crypto-{invoice_id}",
    }
    _invoices[invoice_id] = row
    return {"ok": True, "result": row}


@app.get("/api/getInvoices")
async def crypto_get(invoice_ids: str | None = None, count: int = 1000, offset: int = 0) -> dict[str, Any]:
    del count, offset
    rows = list(_invoices.values())
    if invoice_ids:
        wanted = {item.strip() for item in invoice_ids.split(",")}
        rows = [row for row in rows if str(row["invoice_id"]) in wanted]
    return {"ok": True, "result": rows}


@app.post("/v2/Init")
async def tbank_init(request: Request) -> dict[str, Any]:
    payload = await request.json()
    payment_id = str(next(_counter))
    return {
        "Success": True,
        "PaymentId": payment_id,
        "OrderId": str(payload.get("OrderId") or ""),
        "Status": "NEW",
        "PaymentURL": f"http://127.0.0.1:18081/checkout/tbank-{payment_id}",
    }


@app.post("/v2/GetState")
async def tbank_state(request: Request) -> dict[str, Any]:
    payload = await request.json()
    return {"Success": True, "PaymentId": payload.get("PaymentId"), "Status": "NEW"}


@app.post("/v2/CheckOrder")
async def tbank_check(request: Request) -> dict[str, Any]:
    payload = await request.json()
    return {"Success": True, "OrderId": payload.get("OrderId"), "Payments": []}


@app.post("/v3/payments")
async def yookassa_create(request: Request) -> dict[str, Any]:
    payload = await request.json()
    payment_id = f"yk-{next(_counter)}"
    return {
        "id": payment_id,
        "status": "pending",
        "amount": payload.get("amount"),
        "confirmation": {
            "type": "redirect",
            "confirmation_url": f"http://127.0.0.1:18081/checkout/{payment_id}",
        },
    }


@app.get("/v3/payments/{payment_id}")
async def yookassa_get(payment_id: str) -> dict[str, Any]:
    return {"id": payment_id, "status": "pending", "paid": False}
