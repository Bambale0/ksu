# Current production documentation state

Snapshot date: **2026-08-27**.

This file is the short cross-domain status companion to `docs/README.md`. Runtime `main`, the latest successful exact-SHA production deploy, published PostgreSQL configuration/tariffs and tested API contracts take precedence over historical parity notes.

## Shipped

- ROXY customer Mini App at `/mini-app/` with primary navigation **Студия · Лента · Каталог · Создать · Партнёры · Профиль**.
- Full-screen TikTok-style public feed with `Для вас` / `Подписки`, likes, comments, sharing, author navigation and server-owned Repeat/remix actions.
- Cross-user Repeat works without exposing a hidden source prompt: the server restores the source prompt/settings and the public feed DTO may keep `prompt` empty.
- Feed/profile/referral deep links use Telegram Direct Mini App links only when a real BotFather short name is configured; otherwise the supported fallback is `t.me/<bot>?start=<payload>`, never the invalid synthetic `/app` short name.
- Feed publication sharing returns a usable publication link; after publish the Mini App offers Telegram sharing and WebView-safe copy fallback.
- Catalog model-family sheets show an explicit price for every model variant. Price metadata comes from the backend generation catalog rather than frontend constants.
- Generation pricing has one operator source of truth: the latest published `generation_pricing` tariff in PostgreSQL. API workers refresh it before model catalog, quote and generation-create pricing decisions; quote, displayed price and debit use the same resolver. Music/Suno participates in the same admin pricing contour.
- Privileged Admin Console at `/admin-app/` with RBAC, MFA/step-up and audit controls.
- Active admins can additionally manage curated Trends directly inside the customer Mini App near **Тренды → Готовые сценарии**, following the Tanya-style workflow: create, upload durable preview, edit, duplicate, hide and restore. Backend still rechecks an active `AdminAccount` plus `social.moderate`; frontend visibility is not authorization.
- Trend previews uploaded from the inline manager are persisted through ROXY-owned durable upload/storage; curated prompts and provider parameters remain hidden from customers.
- Separate Photo and Video Create flows backed by one schema-driven generation builder; music generation is part of the same catalog/pricing/runtime contract.
- Server-side flat/per-second generation pricing with parameter-aware tiers.
- 1 ROX = 1 RUB public denomination and current ROXY referral/bonus economy.
- Durable generation outbox/workers, product-owned media ingestion, payment reconciliation and operational telemetry.
- Generation terminal states are monotonic: late/duplicate provider callbacks cannot turn a refunded failure into a success or a completed success into a failure.
- Ambiguous Kie `createTask` outcomes are held in `submitting` for callback/reconciliation recovery instead of blindly resubmitting a potentially accepted paid task. Explicit 429 admission rejection remains retryable; permanent validation/auth 4xx failures fail/refund.
- Unknown submissions have a 900-second recovery timeout by default; active provider work has a configurable hard lifetime (`GENERATION_HARD_TIMEOUT_SECONDS`, default 7200 seconds) with idempotent failure/refund.
- Provider success without usable result media remains recoverable rather than being finalized as a charged empty result.
- Repository-owned approved promo slide assets and documentation mirrors.

## Release / audit contract

The mandatory Mini App browser gate now contains the existing 300 user-scenario matrix plus **150 additional system-risk scenarios** across five viewport classes, for **450 named matrix scenarios**. The same Chromium invocation also runs the repository's focused Playwright specs, so the raw Playwright test count is higher than 450. iPhone/iPad WebKit responsive audits remain a separate mandatory step.

The additional 150 scenarios cover cross-user feed privacy/repeat/share, inline trend-admin permissions and CRUD, dynamic model pricing, create/history/reference recovery, partner deep-link fallback, publication, wallet/payment and navigation integrity. See `SYSTEM_AUDIT_2026-08-27.md` for audit evidence.

## Authoritative runtime checks

```text
GET  /api/v1/generations/models
POST /api/v1/generations/quote
GET  /api/v1/trends
GET  /health/operational
GET  /metrics
GET  /mini-app/release.json
```

For generation prices, the latest published admin tariff plus server model catalog are authoritative. For model fields/operations, the server `ui_schema` is authoritative. For a production rollout, `/mini-app/release.json` must match the exact tested/deployed `main` SHA.

## Documentation rule

Runtime-affecting PRs must update the relevant maintained documentation and configuration examples before merge. Historical parity checklists may describe intermediate implementations; current behavior should be read from `docs/README.md` and the domain docs linked there. When documentation conflicts with a tested runtime contract, fix the documentation and preserve the runtime/audit evidence rather than changing production behavior solely to match stale prose.
