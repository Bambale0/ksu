# Admin contour audit: static web admin removal

Date: 2026-08-21
Branch: `fix/remove-web-admin-audit-admin`

## Decision

The static `/admin-app/` web admin surface is retired. ROXY keeps the admin contour as:

- Telegram operator menu: `/admin`;
- authenticated admin API: `/api/v1/admin/*`;
- internal signed admin API: `/internal/admin/*`;
- durable workers: payments, notifications, admin campaigns, creator partnership, media and generation workers;
- database-backed audit/idempotency/policy state.

## Why the web admin was removed

The static web admin had become a separate operational surface with its own JS, UI state and auth assumptions. It increased maintenance and testing surface, while the actual production admin domain already lived in backend services and Telegram operator flows.

Observed risk areas:

1. `/admin-app/` was mounted as static files beside the customer mini app.
2. The Telegram admin menu exposed a WebApp button that could send operators into a stale/broken web surface.
3. CI validated JavaScript syntax, not whether admin domain operations actually worked.
4. The web layer duplicated admin capabilities instead of being the source of authority.

## Runtime changes

- Removed `/admin-app` static mount from `app/main.py`.
- Removed `app/web/admin_app/*` static assets.
- Added a Telegram compatibility handler for old inline buttons with `callback_data="admin:web"`.
- Patched Telegram admin keyboard at dispatcher creation so the web-admin button is not shown to current operators.
- Replaced the `Admin Console` workflow with `Admin Contour`, which runs backend/admin contract tests.

## Admin contour that remains supported

### Telegram admin

- `/admin` remains operator-only.
- Admin access still requires an active `AdminAccount` bound to a real user.
- Existing Telegram actions continue to use backend admin services.

### Admin HTTP APIs

- `/api/v1/admin/auth/*` for authenticated admin sessions, MFA and step-up.
- `/api/v1/admin/users`, operations, payments, accounts, audit, capabilities, control and creator partnership routes remain mounted.
- `/internal/admin/*` remains HMAC-signed for internal/operator integrations.

### Write safety

Sensitive writes must preserve:

- `Idempotency-Key`;
- confirmation header or Telegram confirmation phrase;
- step-up for sensitive actions;
- permission checks via `AdminPolicy`;
- durable audit/idempotency records.

## Release acceptance

This change is acceptable only if:

- `/mini-app` still mounts;
- `/admin-app` does not mount;
- `app/web/admin_app` does not ship;
- old `admin:web` callbacks do not open a web app;
- admin API routers still mount;
- admin write contracts still require idempotency/confirmation/step-up;
- CI runs `Admin Contour`, `ROXY Release Gate`, `Batch Generation` and full backend regression green before merge.

## Remaining operator note

If a future web admin is needed again, build it as a first-class maintained product with a current auth model, tests and deployment acceptance. Do not reintroduce static admin files beside the customer mini app as a quick patch.
