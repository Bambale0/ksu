from __future__ import annotations

import itertools
from typing import Any

from fastapi import FastAPI, Request

app = FastAPI(title="ROXY E2E fake card checkout")
_counter = itertools.count(1)
_invoices: dict[str, dict[str, Any]] = {}


@app.get("/health")
async def health() -> dict[str, bool]:
    return {"ok": True}


@app.post("/api/v3/invoice")
async def create_invoice(request: Request) -> dict[str, Any]:
    payload = await request.json()
    invoice_id = f"card-{next(_counter)}"
    invoice = {
        "id": invoice_id,
        "status": "pending",
        "amount": payload.get("amount"),
        "currency": payload.get("currency"),
        "paymentUrl": f"http://127.0.0.1:18082/checkout/{invoice_id}",
    }
    _invoices[invoice_id] = invoice
    return {"data": invoice}


@app.get("/api/v2/invoices/{invoice_id}")
async def get_invoice(invoice_id: str) -> dict[str, Any]:
    invoice = _invoices.get(invoice_id)
    if invoice is None:
        return {"data": {"id": invoice_id, "status": "pending"}}
    return {"data": invoice}


@app.get("/checkout/{invoice_id}")
async def checkout(invoice_id: str) -> dict[str, str]:
    return {"invoice": invoice_id, "status": "ready"}
