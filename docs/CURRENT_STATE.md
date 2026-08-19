# Current production documentation state

Snapshot date: **2026-08-20**.

This file is the short cross-domain status companion to `docs/README.md`.

## Shipped

- ROXY customer Mini App at `/mini-app/`.
- Privileged Admin Console at `/admin-app/` with RBAC, MFA/step-up and audit controls.
- Separate Photo and Video Create flows backed by one schema-driven generation builder.
- WAN 2.7 photo generation/editing plus current image/video model families exposed by the backend catalog.
- Server-side flat/per-second generation pricing with parameter-aware tiers.
- Live Admin Tariffs generation pricing, quote/debit parity and PostgreSQL restore after restart.
- 1 ROX = 1 RUB public denomination and current ROXY referral/bonus economy.
- Durable generation outbox/workers, product-owned media ingestion, payment reconciliation and operational telemetry.
- Repository-owned approved promo slide assets and documentation mirrors.

## Authoritative runtime checks

```text
GET  /api/v1/generations/models
POST /api/v1/generations/quote
GET  /health/operational
GET  /metrics
```

For generation prices, the latest published admin tariff plus server model catalog are authoritative. For model fields/operations, the server `ui_schema` is authoritative.

## Documentation rule

Historical parity checklists may describe intermediate implementations. Current behavior should be read from `docs/README.md` and the domain docs linked there. When documentation conflicts with a tested runtime contract, fix the documentation and preserve the runtime/audit evidence rather than changing production behavior solely to match stale prose.
