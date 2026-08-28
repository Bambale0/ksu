# Visual admin operations console

**Status:** synchronized with shipped runtime on 2026-08-20.

The privileged operator UI is a separate Telegram Mini App mounted at:

```text
/admin-app/
```

It does not share the customer Mini App navigation or authorization state.

## Launch and authentication

Active administrators may use `/admin`. The returned WebApp button is only a launcher; authorization still requires signed Telegram `initData`, a server-created admin session and the backend MFA policy.

Production security settings include:

```text
ADMIN_SECURITY_KEY=<dedicated random secret>
ADMIN_BOOTSTRAP_TELEGRAM_IDS=<temporary bootstrap allow-list>
ADMIN_REQUIRE_MFA=true
```

Admin auth surfaces include login, MFA setup/confirm, step-up, current-session inspection and logout. The browser admin token is held only in the JavaScript runtime state and is not persisted to localStorage, sessionStorage, IndexedDB or client-created cookies.

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

The Tariffs contour can publish `generation_pricing` overrides for the generation catalog.

### Runtime contract

- model IDs must exist in the backend generation catalog;
- override shape must match the model price mode (`flat` or `per_second`);
- parameter-tier overrides are accepted only for model parameters supported by the server pricing resolver;
- currently used tiered pricing includes Kling Motion resolution tiers;
- publish requires `pricing.manage` plus explicit confirmation and fresh MFA step-up;
- after publish, the current API runtime uses the new generation prices immediately;
- the latest published generation tariff is persisted and restored from PostgreSQL when the application starts/restarts;
- `POST /api/v1/generations/quote` and the actual wallet debit use the same resolver, so an admin price cannot be display-only.

### Current public baseline

```text
Nano Banana PRO            25 ROX
WAN 2.7 photo              20 ROX
GPT Image 2                20 ROX
Nano Banana 2              25 ROX
Nano Banana 2 Lite         25 ROX
Seedream 4.5               20 ROX
Seedream 5 Pro             20 ROX
Seedance 2.0 480p          40 ROX/s
Seedance 2.0 720p          50 ROX/s
Seedance 2.0 1080p         60 ROX/s
Seedance 2.5 480p          50 ROX/s
Seedance 2.5 720p          60 ROX/s
Seedance 2.5 1080p         70 ROX/s
Seedance 2.5 4K            90 ROX/s, reserved until callable provider support is exposed
Kling 2.5 Turbo Pro 5s     40 ROX
Kling 2.5 Turbo Pro 10s    80 ROX
Kling AI Avatar Standard   100 ROX/s
Kling AI Avatar Pro        150 ROX/s
Kling 3.0                  30 ROX/s
Veo 3.1                    35 ROX/s
Grok                        15 ROX/s
Grok Imagine 1.5           30 ROX/s
Gemini Omni                from 30 ROX/s
Kling Motion 2.6 720p      20 ROX/s
Kling Motion 2.6 1080p     30 ROX/s
Kling Motion 3.0 720p      60 ROX/s
Kling Motion 3.0 1080p     80 ROX/s
```

The live published tariff and runtime `/generations/models`/quote output override this documentation if they differ.

### Operator verification after a pricing publish

1. Reload/read the published tariff version in Admin Tariffs.
2. Query `/api/v1/generations/models` and confirm the affected public price metadata.
3. Request quotes for each changed model and, for tiered models, each changed tier (e.g. 720p and 1080p).
4. Run a controlled generation on a test wallet and verify debit equals the quote.
5. Restart a non-production/staging API process or perform the release restart procedure and verify the same published price is restored.
6. Check the admin audit trail for actor, request/command ID and tariff version.

Rollback is performed by publishing a corrected/previous-value tariff version rather than editing historical audit records.

## Separate static boundary

FastAPI serves:

```text
/mini-app/   customer ROXY application
/admin-app/  privileged operations console
```

Admin application files live under `app/web/admin_app/`.

## Security notes

- Do not persist bearer tokens in browser storage.
- Do not render untrusted API data through HTML injection primitives.
- Do not infer permission from a visible button.
- Session revocation of privileged sessions requires `sessions.manage`; read-only security access must not imply mutation rights.
- Pricing values are money-adjacent configuration and must go through the same audit/confirmation/step-up discipline as other high-impact operator changes.

## CI contract

CI syntax-checks the admin JavaScript and executes admin security/console regressions. Generation pricing regressions additionally verify default pricing, admin overrides, quality tiers, quote/debit parity and restart restoration of the latest published tariff.
