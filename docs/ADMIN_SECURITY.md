# KSU admin security runbook

**Status:** synchronized with the implemented admin API/security domain on 2026-08-11.

The admin API is a separate privileged security domain. A normal Telegram user's WebApp authorization is **not** an admin bearer session.

The implementation is designed around OWASP ASVS 5.0.0 and OWASP guidance for authorization, sessions, MFA and logging. It is not a claim of formal OWASP certification.

Official references:

- https://owasp.org/www-project-application-security-verification-standard/
- https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
- https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
- https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html
- https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html

OWASP ASVS 5.0.0 was released in May 2025 and is the current ASVS version referenced by this runbook.

## 1. What is shipped

Implemented:

- dedicated `admin_accounts` identity records;
- dedicated opaque `admin_sessions`;
- role/permission authorization;
- TOTP MFA and recovery codes;
- step-up reauthentication;
- login/request rate limits and temporary login lock;
- admin security/audit API;
- user/wallet/generation/payment/support/withdrawal/promo/referral administration API;
- admin account/session management;
- application-level tamper-evident audit records.

Not shipped yet:

- a dedicated visual admin web application.

The current repository therefore provides the protected **admin backend/API**. Any browser/Telegram admin UI must be built as a client of this API and preserve the token-handling rules below.

## 2. Core configuration

Required for production admin access:

```dotenv
ADMIN_SECURITY_KEY=<dedicated random secret, at least 32 chars>
ADMIN_BOOTSTRAP_TELEGRAM_IDS=<temporary initial owner Telegram ID>
ADMIN_REQUIRE_MFA=true
ADMIN_SESSION_TTL_MINUTES=480
ADMIN_IDLE_TIMEOUT_MINUTES=30
ADMIN_STEP_UP_MINUTES=10
ADMIN_LOGIN_RATE_LIMIT_PER_MINUTE=5
ADMIN_REQUEST_RATE_LIMIT_PER_MINUTE=120
ADMIN_LOGIN_MAX_FAILURES=5
ADMIN_LOGIN_LOCK_MINUTES=15
```

Never reuse any of these as `ADMIN_SECURITY_KEY`:

- `BOT_TOKEN`;
- Kie credentials;
- Crypto Pay token;
- T-Bank password;
- YooKassa secret;
- database password;
- reverse-proxy secret.

`ADMIN_SECURITY_KEY` currently protects multiple security functions:

- admin bearer-token HMAC hashes;
- client fingerprint hashes;
- audit integrity HMAC;
- recovery-code hashes;
- encryption key derivation for stored MFA secret encryption.

Therefore rotating it is **not** a routine stateless secret rotation. See the rotation section before changing it.

## 3. Admin authentication model

Current identity chain:

```text
fresh signed Telegram initData
        ↓
Telegram user identity
        ↓
active AdminAccount
        ↓
MFA state
        ↓
opaque AdminSession bearer token
        ↓
permission check on each protected endpoint
        ↓
optional fresh step-up for sensitive mutation
```

There is no separate admin password database.

Telegram `initData` is validated by the backend using `BOT_TOKEN`. It must come from `Telegram.WebApp.initData`, not trusted `initDataUnsafe`.

Official Telegram reference: https://core.telegram.org/bots/webapps

## 4. Production bootstrap

### Important current limitation

The repository does **not** yet ship a dedicated admin UI that acquires Telegram `initData` and drives enrollment screens.

For the first bootstrap, use a trusted first-party client/tool that is running inside a valid Telegram Mini App context and can send the raw fresh `Telegram.WebApp.initData` to the admin API. Do not paste raw `initData`, bearer tokens, MFA secrets or recovery codes into chat systems, tickets or logs.

### Bootstrap sequence

1. Generate a dedicated random `ADMIN_SECURITY_KEY` with at least 32 characters.
2. Put **only** the initial owner's Telegram ID in `ADMIN_BOOTSTRAP_TELEGRAM_IDS`.
3. Keep `ADMIN_REQUIRE_MFA=true`.
4. Deploy the backend.
5. Obtain fresh signed Telegram `initData` for that same Telegram user through a trusted first-party Telegram context.
6. Call `POST /api/v1/admin/auth/login` with `X-Telegram-Init-Data`.
7. Because this is a newly bootstrapped owner without MFA, login returns an opaque restricted session with `mfa_setup_required=true`, `mfa_verified=false` and no effective permissions.
8. Using that bearer session **and fresh Telegram initData**, call `POST /api/v1/admin/auth/mfa/setup`.
9. Add the returned TOTP secret/otpauth URI to a trusted authenticator.
10. Call `POST /api/v1/admin/auth/mfa/confirm` with the current six-digit TOTP code.
11. Store the returned recovery codes offline/separately. They are returned once; the backend stores only hashes.
12. Verify `GET /api/v1/admin/auth/me` now shows `mfa_verified=true` and owner permissions.
13. Remove the owner's ID from `ADMIN_BOOTSTRAP_TELEGRAM_IDS` and redeploy/reload configuration.
14. Create all additional administrators through the owner-only admin API after a fresh MFA step-up.

Do not leave bootstrap IDs configured as a permanent administrator-management mechanism.

## 5. Login behavior

Endpoint:

```http
POST /api/v1/admin/auth/login
X-Telegram-Init-Data: <fresh signed Telegram initData>
Content-Type: application/json
```

Body can contain:

```json
{
  "otp": "123456",
  "recovery_code": null
}
```

For an admin with MFA enabled, a valid TOTP or recovery code is required when MFA enforcement is enabled.

Current brute-force controls:

- login rate limit is keyed by a hashed source IP;
- invalid MFA attempts increment an admin failed-login counter;
- after the configured threshold, the admin account receives a temporary `locked_until` window;
- successful login clears failure/lock state.

## 6. Admin bearer sessions

Login returns an opaque random bearer token.

The raw token is returned to the client only; PostgreSQL stores an HMAC-SHA256 token hash.

Use:

```http
Authorization: Bearer <opaque-token>
```

Session controls:

- absolute expiry;
- sliding idle expiry capped by absolute expiry;
- session version bound to current admin account privilege version;
- explicit revoke/logout;
- user-agent fingerprint binding;
- source-IP change handling;
- per-session request rate limit;
- MFA verification state;
- short step-up window.

### Fingerprint behavior

Current implementation:

- **user-agent fingerprint changes revoke the session**;
- **source IP changes do not revoke the session**, because roaming/mobile networks are expected;
- an IP change updates the stored hashed IP, clears `step_up_until`, and writes an audit event.

This means a network change forces a new step-up before the next sensitive action.

## 7. Browser/admin-client token handling

If a visual admin UI is added:

Preferred designs:

1. same-origin backend-for-frontend that keeps the admin bearer token server-side; or
2. keep the bearer token only in JavaScript/application memory for the current session.

Do **not** persist admin bearer tokens in:

- `localStorage`;
- `sessionStorage`;
- IndexedDB;
- URL/query/fragment;
- browser history;
- analytics state;
- crash reports;
- client/server logs.

Do not reuse the generation Mini App's local draft storage strategy for admin credentials.

The current admin API deliberately uses bearer authentication, not cookies. Therefore cookie-based CSRF is not part of the current auth transport. If a future admin client switches to cookie sessions, add and verify `Secure`, `HttpOnly`, appropriate `SameSite`, origin checking and CSRF protection before deployment.

Avoid third-party scripts on a privileged admin origin unless they are explicitly reviewed.

## 8. MFA enrollment

### Start enrollment

```http
POST /api/v1/admin/auth/mfa/setup
Authorization: Bearer <restricted-or-active-admin-session>
X-Telegram-Init-Data: <fresh initData for same Telegram user>
```

Requirements:

- MFA is not already enabled;
- fresh Telegram identity matches the admin account user.

Response contains the TOTP secret and `otpauth://` URI.

### Confirm enrollment

```http
POST /api/v1/admin/auth/mfa/confirm
Authorization: Bearer <session>
Content-Type: application/json

{"code":"123456"}
```

On success:

- MFA becomes enabled;
- current session becomes MFA verified;
- recovery codes are generated and returned once;
- only recovery-code HMAC hashes are persisted.

Current TOTP verification allows a small adjacent time-step window to tolerate normal clock skew. Keep server/client clocks synchronized.

## 9. Recovery codes

Recovery codes are second-factor credentials.

Rules:

- store them outside the application database in a secure user-controlled place;
- never put them in logs/tickets/chat;
- each successful recovery code is removed from the stored hash list and cannot be reused;
- using recovery code still requires normal Telegram identity/session flow where the endpoint requires it.

There is currently no separate self-service recovery-code regeneration endpoint documented as a supported workflow. Treat loss of all second factors as an owner/security incident rather than bypassing MFA.

## 10. Roles and permissions

Roles are deny-by-default. Unknown roles have no base permission set.

Current roles:

### `owner`

Wildcard full access, including administrator account management.

### `admin`

Broad operational access to:

- dashboard;
- users/PII/user status;
- wallet adjustments;
- user notes;
- generations;
- payment visibility;
- promos;
- support;
- withdrawals;
- referrals;
- audit/security visibility;
- sessions.

By default this role cannot create/manage admin accounts.

### `support`

User lookup/notes plus generation/payment context and support management.

### `finance`

User/PII lookup, wallet adjustments, payments, withdrawals, referrals and audit visibility.

### `moderator`

User restriction/notes, generation management context and support read access.

### `auditor`

Read-only operational/security visibility.

### Permission overrides

Each admin may have explicit allow/deny overrides.

Authorization order:

1. explicit deny wins;
2. role grant/wildcard;
3. explicit allow;
4. otherwise deny.

Every protected endpoint uses an explicit permission dependency. UI button visibility must never be treated as authorization.

This follows OWASP's deny-by-default and validate-permissions-on-every-request recommendations.

## 11. Sensitive step-up actions

Sensitive actions require a recently completed step-up in addition to an authenticated MFA-verified session.

Current step-up endpoint:

```http
POST /api/v1/admin/auth/step-up
Authorization: Bearer <session>
X-Telegram-Init-Data: <fresh initData for the same Telegram user>
Content-Type: application/json
```

Body accepts TOTP or a recovery code.

On success:

```text
step_up_until = now + ADMIN_STEP_UP_MINUTES
```

Current sensitive categories include:

- wallet adjustments;
- withdrawal status changes;
- administrator creation;
- administrator role/status/permission changes.

An IP change clears the active step-up window.

## 12. Privilege/session invalidation

Changing an administrator's role, active status or permission overrides increments the admin `session_version` and invalidates existing sessions for that administrator.

This avoids keeping old elevated sessions alive after a privilege change.

The system also protects critical owner invariants, including safeguards around changing admin users/owners.

## 13. Main API groups

### Authentication/session

```text
POST   /api/v1/admin/auth/login
GET    /api/v1/admin/auth/me
POST   /api/v1/admin/auth/mfa/setup
POST   /api/v1/admin/auth/mfa/confirm
POST   /api/v1/admin/auth/step-up
GET    /api/v1/admin/auth/sessions
DELETE /api/v1/admin/auth/sessions/{session_id}
POST   /api/v1/admin/auth/logout
```

### Operational administration

```text
GET   /api/v1/admin/dashboard
GET   /api/v1/admin/users
GET   /api/v1/admin/users/{user_id}
GET   /api/v1/admin/users/{user_id}/history
PATCH /api/v1/admin/users/{user_id}/status
POST  /api/v1/admin/users/{user_id}/wallet-adjustments
POST  /api/v1/admin/users/{user_id}/notes

GET  /api/v1/admin/generations
POST /api/v1/admin/generations/{generation_id}/reconcile

GET /api/v1/admin/payments

support ticket read/reply/status endpoints
withdrawal list/status endpoints
promo-code list/create/update endpoints
referral reward list endpoint
```

Payment administration is intentionally visibility-focused. The current backend does not expose a generic unsafe `mark payment succeeded` operation that bypasses provider verification.

### Security administration

```text
GET    /api/v1/admin/roles
GET    /api/v1/admin/admins
POST   /api/v1/admin/admins
PATCH  /api/v1/admin/admins/{admin_id}

GET    /api/v1/admin/audit
GET    /api/v1/admin/security/overview
GET    /api/v1/admin/security/sessions
DELETE /api/v1/admin/security/sessions/{session_id}
```

## 14. User/PII handling

Admin API response DTOs are intentionally explicit rather than generic ORM serialization.

PII exposure is permission-gated. For example, user views can mask Telegram IDs/identity fields when `users.pii` is unavailable.

Do not add generic `model_dump()`/ORM-to-JSON endpoints that expose every database column. New admin endpoints should follow allowlisted response shaping and explicit request models to reduce excessive data exposure and mass assignment risk.

## 15. Wallet adjustments

Manual wallet adjustment is a sensitive admin action.

Current controls include:

- explicit `users.wallet.adjust` permission;
- fresh step-up requirement;
- non-zero amount validation;
- safety amount limit;
- existing immutable wallet ledger path;
- idempotency key based on request ID;
- required human reason;
- audit entry with before/after balance.

Do not add direct SQL/UI balance replacement as a normal admin workflow.

## 16. Audit trail

Privileged mutations and important auth/security events write application audit entries containing fields such as:

```text
admin_id
session_id
action
outcome
resource_type
resource_id
reason
request_id
hashed source IP
hashed user-agent
sanitized metadata
integrity_hash
created_at
```

Central redaction removes or masks sensitive metadata keys/patterns including:

- authorization/cookies;
- passwords;
- secrets/tokens;
- Telegram initData;
- MFA secret/recovery codes;
- payment requisites/provider response fields.

The audit integrity HMAC is **tamper-evident**, not a full external WORM guarantee.

For higher assurance:

- ship audit/security events to a separately controlled SIEM or append-only object store;
- configure retention/alerts outside the application database;
- restrict access to both audit records and `ADMIN_SECURITY_KEY`.

## 17. Security headers / caching

The application applies security headers and gives admin API responses no-store behavior. Production also enables HSTS when `APP_ENV=production`.

Keep admin/API traffic behind HTTPS and do not terminate to plaintext across untrusted networks.

FastAPI Swagger/ReDoc are disabled in production by application configuration.

## 18. Monitoring

Alert/review at minimum:

- repeated admin login failures;
- temporary admin account lockouts;
- authorization denials;
- user-agent session invalidations;
- unusual IP-change frequency;
- active administrators without MFA;
- role/permission changes;
- session revocations;
- large wallet adjustments;
- withdrawal state changes;
- audit integrity failures if verification is exposed to monitoring.

Periodically review:

- active admin accounts;
- role/permission overrides;
- active admin sessions;
- old bootstrap configuration;
- unused owner/admin accounts.

## 19. Incident response

### Suspected stolen bearer token

1. Revoke the session through self-session or security-session endpoint.
2. If scope is unclear, disable the admin or force privilege/session-version change to invalidate sessions.
3. Review audit events around the affected period.
4. Do not rotate `ADMIN_SECURITY_KEY` as the first reaction unless it itself is compromised.

### Lost/stolen authenticator

- use a remaining recovery code if appropriate;
- revoke active sessions;
- security owner should review whether re-enrollment tooling/change is needed;
- do not disable MFA globally as a convenience workaround.

### Compromised `ADMIN_SECURITY_KEY`

Treat as high severity because one key currently supports several admin security primitives.

A safe rotation requires a planned migration because existing encrypted MFA secrets are derived from the old key.

Do not simply change the env value and restart expecting admins to keep working.

Plan must cover:

- invalidating/reissuing bearer sessions;
- re-encrypting or re-enrolling MFA secrets;
- impact on old audit integrity verification;
- recovery-code hash strategy;
- controlled owner access during transition.

### Compromised `BOT_TOKEN`

The bot token is also used to validate Telegram Mini App `initData`.

After rotating it:

- update `BOT_TOKEN`;
- restart app to register Telegram webhook with the new bot token context;
- retest normal user and admin Telegram initData validation;
- revoke suspicious admin sessions as appropriate.

## 20. Production deployment controls

- HTTPS only;
- database/Redis private;
- production secrets in a secret manager or protected environment file;
- `.env` permissions restricted;
- PostgreSQL backup and restore tested;
- reverse proxy/body limits reviewed;
- time synchronization enabled;
- security logs monitored;
- no third-party analytics scripts on future admin UI by default;
- `ADMIN_BOOTSTRAP_TELEGRAM_IDS` removed after owner enrollment.

See `docs/OPERATIONS_RUNBOOK.md` for full deployment/rollback/provider operations.

## 21. Security test expectations

CI includes admin security regression tests for core primitives such as:

- deny-by-default permission behavior;
- TOTP verification;
- encrypted MFA secret handling;
- opaque token hashing;
- audit metadata redaction/integrity behavior.

Authorization changes should add/update tests before merge. OWASP explicitly recommends unit/integration tests for authorization logic.

## 22. Current limitations / next hardening steps

- no dedicated visual admin client is bundled yet;
- audit HMAC remains application/database tamper-evidence, not external immutable logging;
- admin authentication is tied to Telegram signed identity plus TOTP rather than WebAuthn/passkeys;
- current controls are aligned to selected OWASP guidance but are not an independent ASVS verification/certification;
- any future cookie-based admin UI needs a new explicit CSRF/session-cookie review before release.
