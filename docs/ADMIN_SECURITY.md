# KSU admin security runbook

The admin API is a separate privileged security domain. It does not reuse a normal user's Telegram WebApp authorization as an admin bearer session.

The implementation is designed around OWASP ASVS 5.0.0, OWASP API Security Top 10 (especially API1/BOLA, API3/BOPLA and API5/BFLA), and the OWASP Authorization, Session Management, MFA, and Logging cheat sheets.

## Production bootstrap

1. Generate a dedicated random secret of at least 32 characters and set `ADMIN_SECURITY_KEY`.
2. Put only the initial owner's Telegram ID in `ADMIN_BOOTSTRAP_TELEGRAM_IDS`.
3. Keep `ADMIN_REQUIRE_MFA=true`.
4. Start the backend and open the admin client from Telegram so it can obtain fresh signed Telegram `initData`.
5. Call `POST /api/v1/admin/auth/login` with `X-Telegram-Init-Data`. The first allowlisted owner receives a restricted session because MFA is not enrolled yet.
6. Call `POST /api/v1/admin/auth/mfa/setup` with the bearer session and fresh `X-Telegram-Init-Data`.
7. Add the returned TOTP secret to a trusted authenticator and confirm it through `POST /api/v1/admin/auth/mfa/confirm`.
8. Store the returned recovery codes securely. They are shown once and are stored by the backend only as HMAC hashes.
9. Remove the owner's ID from `ADMIN_BOOTSTRAP_TELEGRAM_IDS` after successful enrollment and redeploy/reload configuration.
10. Create all additional admins through the owner-only `/api/v1/admin/admins` endpoint after a fresh MFA step-up.

Never reuse `BOT_TOKEN`, Kie credentials, payment credentials, database passwords, or any other provider secret as `ADMIN_SECURITY_KEY`.

## Admin client token handling

`POST /api/v1/admin/auth/login` returns an opaque bearer token. The database stores only an HMAC-SHA256 token hash.

For a browser admin UI:

- prefer a same-origin backend-for-frontend that keeps the admin bearer token server-side, or keep the token only in application memory;
- do not persist the token in `localStorage`, `sessionStorage`, IndexedDB, analytics state, logs, crash reports, URLs, query strings, or browser history;
- send it only in the `Authorization: Bearer ...` header over HTTPS;
- clear it immediately on logout/401;
- do not place third-party scripts on the privileged admin origin unless explicitly reviewed.

The current API deliberately does not use authentication cookies, so cookie-based CSRF is not part of this transport. If a future admin UI changes authentication to cookies, add `Secure`, `HttpOnly`, appropriate `SameSite`, origin checks, and a CSRF token strategy before deploying that change.

## Session controls

Defaults:

- absolute session TTL: 480 minutes;
- idle timeout: 30 minutes;
- sensitive-action MFA step-up window: 10 minutes;
- login rate limit: 5 attempts/minute per hashed source IP;
- admin request rate limit: 120 requests/minute per session;
- temporary lock after 5 invalid MFA login attempts for 15 minutes.

A user-agent fingerprint change revokes the admin session. A source-IP change does not hard-lock a roaming admin, but it clears the step-up window and creates an audit event.

Changing an administrator's role, active status, or permission overrides increments `session_version` and revokes all of that administrator's existing sessions.

## Roles

Roles are deny-by-default. `owner` is the only wildcard role. Explicit `deny` overrides win over role grants.

- `owner`: full access, including creation and modification of administrators.
- `admin`: broad operational access to users, wallet adjustments, content, payments, support, withdrawals, promos, referrals, audit, and session security; cannot create/manage admin accounts by default.
- `support`: user lookup, notes, generation/payment context, support ticket management.
- `finance`: user/PII lookup, wallet adjustments, payments, withdrawals, referral accounting, audit.
- `moderator`: user restrictions/notes and generation moderation context.
- `auditor`: read-only operational/security visibility.

The backend performs permission checks on every protected endpoint. Hiding a button in the UI is never treated as authorization.

## Sensitive step-up actions

The following require a recently completed MFA step-up in addition to the normal authenticated admin session:

- wallet adjustments;
- withdrawal status changes;
- administrator creation/update and privilege changes.

`POST /api/v1/admin/auth/step-up` requires both fresh Telegram `initData` and a valid TOTP/recovery code.

## Main API groups

Authentication:

- `POST /api/v1/admin/auth/login`
- `GET /api/v1/admin/auth/me`
- `POST /api/v1/admin/auth/mfa/setup`
- `POST /api/v1/admin/auth/mfa/confirm`
- `POST /api/v1/admin/auth/step-up`
- `GET /api/v1/admin/auth/sessions`
- `DELETE /api/v1/admin/auth/sessions/{session_id}`
- `POST /api/v1/admin/auth/logout`

Operations:

- `GET /api/v1/admin/dashboard`
- `GET /api/v1/admin/users`
- `GET /api/v1/admin/users/{user_id}`
- `GET /api/v1/admin/users/{user_id}/history`
- `PATCH /api/v1/admin/users/{user_id}/status`
- `POST /api/v1/admin/users/{user_id}/wallet-adjustments`
- `POST /api/v1/admin/users/{user_id}/notes`
- `GET /api/v1/admin/generations`
- `POST /api/v1/admin/generations/{generation_id}/reconcile`
- `GET /api/v1/admin/payments`
- support ticket read/reply/status endpoints
- withdrawal list/status endpoints
- promo-code list/create/update endpoints
- referral reward list endpoint

Security administration:

- `GET /api/v1/admin/roles`
- `GET /api/v1/admin/admins`
- `POST /api/v1/admin/admins`
- `PATCH /api/v1/admin/admins/{admin_id}`
- `GET /api/v1/admin/audit`
- `GET /api/v1/admin/security/overview`
- `GET /api/v1/admin/security/sessions`
- `DELETE /api/v1/admin/security/sessions/{session_id}`

## Audit guarantees and limitations

Every privileged mutation and important authentication/authorization event records an application audit entry with:

- admin/session IDs;
- action and outcome;
- resource type/id;
- reason where required;
- request correlation ID;
- keyed hashes of source IP and user-agent instead of raw values;
- sanitized metadata;
- HMAC integrity hash.

Secrets, bearer/session tokens, Telegram `initData`, passwords, payment requisites, and provider responses are redacted by the central sanitizer.

The HMAC field detects application/database tampering when verified with an uncompromised `ADMIN_SECURITY_KEY`; it is not equivalent to an external append-only/WORM logging system. For higher-assurance deployments, additionally ship audit events to a separately controlled SIEM/object store with retention controls and alerts.

## Deployment controls

- expose the admin client/API only through HTTPS;
- keep FastAPI Swagger/ReDoc disabled in production (already the application default);
- restrict database and Redis ports to private networking;
- do not expose Redis to the public internet;
- use a secret manager for production credentials;
- back up PostgreSQL and test restoration;
- alert on repeated denied auth, active admins without MFA, unexpected role changes, large wallet adjustments, and withdrawal changes;
- periodically review active admin accounts and sessions;
- rotate `ADMIN_SECURITY_KEY` only with a planned procedure: rotating it invalidates existing bearer-token verification and makes old encrypted MFA secrets unreadable unless they are re-enrolled/migrated first.
