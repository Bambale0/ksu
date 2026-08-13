# Visual admin operations console

The privileged operator UI is a separate Telegram Mini App mounted at:

```text
/admin-app/
```

It deliberately does not share the user Mini App navigation or authentication state.

## Launch

Active administrators may use the bot command:

```text
/admin
```

The bot only returns a WebApp button to `/admin-app/`. The button is **not** an authorization mechanism. The page still requires signed Telegram `initData`, a separate server-created admin session and the backend MFA policy.

Deployment requirements remain the existing admin configuration:

```text
PUBLIC_BASE_URL=https://...
ADMIN_SECURITY_KEY=<dedicated random secret>
ADMIN_BOOTSTRAP_TELEGRAM_IDS=<temporary comma separated bootstrap allow-list>
ADMIN_REQUIRE_MFA=true
```

The first allow-listed owner is bootstrapped by the existing `/api/v1/admin/auth/login` flow. There is no second bootstrap database path in the console.

## Authentication and browser secret boundary

The console uses the existing endpoints:

```text
POST /api/v1/admin/auth/login
POST /api/v1/admin/auth/mfa/setup
POST /api/v1/admin/auth/mfa/confirm
POST /api/v1/admin/auth/step-up
GET  /api/v1/admin/auth/me
POST /api/v1/admin/auth/logout
```

Telegram raw signed `Telegram.WebApp.initData` is sent only where the backend admin-auth contract requires it.

The returned admin bearer token exists only in the JavaScript runtime variable `state.token`. It is never written to:

- `localStorage`;
- `sessionStorage`;
- IndexedDB;
- cookies created by the client.

Closing/reloading the page therefore requires a fresh admin login. Recovery codes returned after MFA enrollment are rendered once and removed from the DOM when the administrator confirms they have saved them.

All API-provided prompt/support/audit/user strings are rendered with DOM `textContent`/text nodes. The SPA does not use `innerHTML`, `eval`, or dynamic Function construction.

## Step-up safety

Sensitive backend operations continue to rely on backend RBAC and MFA step-up. The UI does not assume that a visible button grants permission.

For operations such as wallet adjustment, refunds, partner-withdrawal processing and administrator access changes, the console uses a two-stage interaction:

1. administrator explicitly chooses the business action;
2. step-up dialog verifies fresh OTP/recovery code;
3. the UI shows that MFA is confirmed but **does not execute the mutation yet**;
4. administrator explicitly clicks `Выполнить действие`;
5. only then is the original mutation sent.

This prevents submitting a high-impact business operation merely by entering an MFA code.

## Permission-driven navigation

The console loads effective permissions from:

```text
GET /api/v1/admin/auth/me
```

Navigation and action buttons are filtered from that server response. The backend remains authoritative and independently re-checks every endpoint.

Current operational views map to existing backend domains:

- Dashboard — users, jobs, support, withdrawals, payment metrics;
- Users — search, safe/PII-aware detail, unified activity history, active status, internal notes, wallet adjustments;
- Generations — filters and Kie reconciliation;
- Payments — filters, provider reconciliation and refund requests;
- Support — queue, thread, reply and status changes;
- Partner withdrawals — queue and allowed transitions;
- Promo codes — list/create/update activation state;
- Referral rewards — partner/source/line/status inspection;
- Security / Audit — security KPIs, admin sessions and tamper-evident audit records;
- Administrators — roles, MFA state, activation/access changes;
- My sessions — current administrator session inspection/revocation.

PII elevation is never implemented client-side. If the backend masks a Telegram ID or other field because the current account lacks `users.pii`, the console displays that masked value unchanged.

## Session revocation RBAC correction

During the visual-console audit, the pre-existing endpoint:

```text
DELETE /api/v1/admin/security/sessions/{session_id}
```

was found to use the `security.read` dependency even though it mutates another administrator's session. That allowed read-only security roles such as auditors to revoke sessions.

The endpoint now requires:

```text
sessions.manage
```

while security session listing remains protected by `security.read`. The existing audit record for session revocation remains authoritative.

## Static application boundary

FastAPI serves the privileged UI separately from the user product:

```text
/mini-app/   user Mini App
/admin-app/  privileged operations console
```

Files:

```text
app/web/admin_app/index.html
app/web/admin_app/admin.css
app/web/admin_app/admin.js
```

The UI is responsive down to mobile Telegram WebView size, but desktop/tablet remains the primary operations layout.

## CI contract

The normal repository CI still executes the full PostgreSQL/Alembic/Python regression suite, including `tests/test_admin_console.py`.

A dedicated lightweight workflow additionally runs:

```text
node --check app/web/admin_app/admin.js
```

Static regression tests assert the most important privilege boundaries: in-memory token only, signed Telegram login, no HTML injection primitive, permission-driven navigation, separate explicit step-up execute action, correct session response shape and `sessions.manage` for privileged session revocation.
