# Visual admin operations console

**Status:** synchronized with shipped runtime on **2026-08-27**.

ROXY has two admin-facing surfaces with different purposes:

1. `/admin-app/` — the separate privileged operations console with its own admin session, MFA/step-up and permission-driven modules;
2. inline curated-Trends controls inside `/mini-app/` — a convenience UX for active admins, authenticated by signed Telegram Mini App data and re-authorized server-side with `AdminAccount` + `social.moderate`.

The inline controls do **not** replace the privileged Admin Console and frontend visibility never grants permission.

## Launch and authentication

Active administrators may use `/admin`. The returned WebApp button is only a launcher; authorization still requires signed Telegram `initData`, a server-created admin session and the backend MFA policy.

Production security settings include:

```text
ADMIN_SECURITY_KEY=<dedicated random secret>
ADMIN_BOOTSTRAP_TELEGRAM_IDS=<temporary bootstrap allow-list>
ADMIN_REQUIRE_MFA=true
```

Admin auth surfaces include login, MFA setup/confirm, step-up, current-session inspection and logout. The browser admin token is held only in JavaScript runtime state and is not persisted to localStorage, sessionStorage, IndexedDB or client-created cookies.

## Permission-driven operations

The console renders capabilities from the server-confirmed admin identity. UI visibility never replaces backend RBAC. Current operational domains include:

- Dashboard;
- Users and wallet adjustments;
- Generations and provider reconciliation;
- Payments/refunds;
- Support;
- Partner withdrawals;
- Promo codes;
- Referral rewards;
- Tariffs/pricing;
- curated Trends;
- Security/audit;
- Administrators and sessions.

PII masking/elevation remains server-owned.

## Sensitive-action step-up

High-impact actions use the existing two-stage pattern:

1. choose/preview the operation;
2. perform fresh MFA step-up;
3. UI marks the step-up satisfied but does not mutate yet;
4. operator explicitly executes/confirm-publishes;
5. backend rechecks permission, confirmation and step-up before mutation.

This pattern applies to money/security-sensitive operations and generation tariff publishing.

## Generation pricing / Admin Tariffs

The Tariffs contour publishes `generation_pricing` overrides for the full customer generation catalog, including image, video and music/Suno products.

### Runtime contract

- a published tariff version is persisted in PostgreSQL and is the canonical operator override;
- API workers refresh the latest published generation-pricing version before serving model pricing, quotes and generation-create pricing decisions, so multi-worker deployments do not rely on process-local mutation;
- catalog/model cards, `POST /api/v1/generations/quote` and actual wallet debit use the same pricing resolver;
- model IDs/price modes/tier parameters are validated against the server catalog and pricing capabilities;
- parameter-tier overrides are accepted only for supported pricing dimensions (for example Kling Motion resolution tiers);
- music/Suno no longer uses a separate admin pricing island: it participates in `generation_pricing` and the same publish/audit lifecycle;
- publish requires `pricing.manage`, explicit confirmation and fresh MFA step-up;
- restart/redeploy restores the latest published tariff from PostgreSQL.

The Mini App must not hardcode displayed model prices. Family-variant cards consume the backend `price_rox` metadata and present a visible **Цена / N ROX** block for every variant.

### Public baseline vs live price

Documentation examples are not a billing authority. The live effective price is always the combination of the current backend catalog and latest published admin tariff. Common baseline products include Nano Banana, WAN, GPT Image, Seedream, Seedance, Kling, Veo, Grok, Gemini and music/Suno; flat/per-second/tiered modes differ by model.

For exact production values use:

```text
GET  /api/v1/generations/models
POST /api/v1/generations/quote
```

### Operator verification after a pricing publish

1. Reload/read the published tariff version in Admin Tariffs.
2. Query `/api/v1/generations/models` and confirm the affected public price metadata.
3. Request quotes for each changed model and, for tiered models, each changed tier.
4. Run a controlled generation on a test wallet and verify debit equals the quote.
5. Verify another API worker/process observes the same published version without a client deploy.
6. Restart a non-production/staging API process or perform the release restart procedure and verify the same price is restored.
7. Check the admin audit trail for actor, request/command ID and tariff version.

Rollback is performed by publishing a corrected/previous-value tariff version rather than editing historical audit records.

## Inline Trend management in ROXY

For an authenticated customer Mini App user with `me.is_admin=true`, the **Тренды → Готовые сценарии** section exposes `＋ Добавить` / `Управлять трендами`.

The manager supports:

- create a curated image/video trend;
- choose a model from the live generation catalog;
- upload an image/video preview from the device;
- persist the preview in ROXY-owned durable storage through the existing upload pipeline;
- set public title/description, hidden model prompt, reference requirements, duration, tags, sort priority and advanced model parameters;
- edit or duplicate an existing recipe;
- soft-hide and restore a trend.

Security/runtime rules:

- signed Telegram `initData` resolves the user;
- backend resolves an active `AdminAccount` linked to that user;
- `social.moderate` is authorized server-side for every mutation;
- `TrendService.validate_recipe` validates the model/recipe before persistence;
- `AdminCommandLedger` provides idempotent/audited writes;
- the hidden prompt/provider parameters are never serialized in public trend DTOs;
- ordinary users never receive the inline admin controls and cannot gain permission by crafting the request manually.

The separate `/admin-app/trends.html` manager remains an operator surface using the hardened admin session. Both paths operate on the same curated `AdminTrend` store; there is no second trends database.

## Separate static boundary

FastAPI serves:

```text
/mini-app/   customer ROXY application (+ inline admin conveniences after server authorization)
/admin-app/  privileged operations console
```

Admin application files live under `app/web/admin_app/`.

## Security notes

- Do not persist bearer tokens in browser storage.
- Do not render untrusted API data through HTML injection primitives.
- Do not infer permission from a visible button or `me.is_admin` alone; mutations must re-authorize on the backend.
- Session revocation of privileged sessions requires `sessions.manage`; read-only security access must not imply mutation rights.
- Pricing values are money-adjacent configuration and must go through the same audit/confirmation/step-up discipline as other high-impact operator changes.

## CI contract

CI syntax-checks the Admin Console and executes admin security/console regressions. Pricing regressions verify default pricing, published overrides, tier resolution, quote/debit parity, music/Suno inclusion and PostgreSQL restoration/worker synchronization. The Mini App Playwright release gate additionally verifies inline Trend visibility/permissions/CRUD across the system-risk viewport matrix.
