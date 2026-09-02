# ROXY / KSU adversarial audit — 2026-09-02

Status: **in progress**

This is a living security + reliability audit for the whole `ksu` project. Findings are recorded before remediation and are only marked fixed after a regression test and the relevant CI/release gate pass.

## Scope and trust boundaries

The audit covers the full product surface:

1. Telegram / Mini App authentication and deep links.
2. Browser ↔ API boundaries, including hidden/private data contracts.
3. User uploads, reference storage, media ownership and provider transport.
4. Generation quote / launch / history / repeat / publish / remix flows.
5. Billing, credits, refunds, quantity and idempotency.
6. Payment providers and webhook authenticity/idempotency.
7. External generation providers, callbacks, polling and failure handling.
8. Admin authentication, authorization and privileged operations.
9. Database integrity, migrations, race conditions and stale records.
10. CORS/CSRF, redirects, SSRF, injection, path traversal, unsafe file handling and secret exposure.
11. Frontend state restoration, stale Telegram `start_param`, WebView/browser differences and mobile E2E.
12. Deployment, exact-SHA verification, rollback and production smoke checks.

## Severity

- **Critical** — direct account/payment/admin compromise, arbitrary code execution, mass secret exposure, or equivalent production compromise.
- **High** — meaningful privacy/authorization/billing bypass or an attacker-controlled primitive with realistic impact.
- **Medium** — exploitable integrity/availability/privacy weakness with narrower impact, or a production flow that can be reliably broken.
- **Low** — hardening, metadata leakage, operational weakness or low-impact edge case.

## Finding register

| ID | Severity | Area | Finding | Status | Verification |
| --- | --- | --- | --- | --- | --- |
| ADV-001 | High | Private repeat | The earlier repeat flow hid the source prompt in UI but still transported the recreate recipe to the browser, exposing prompt/settings through network/devtools. | Fix in PR #387 | Backend + Playwright regression: hidden recipe never appears in bootstrap, DOM or request bodies. |
| ADV-002 | High | Private repeat / media ownership | Private-repeat currently accepts any syntactically URL-like HTTPS value as a “recipient-owned” reference. A caller can bypass the UI and inject another user’s or attacker-controlled URL. | Confirmed; remediation in progress | Add server-side ownership check against ready product-owned `UserReference` rows and negative API tests. |
| ADV-003 | High | Private repeat / information disclosure | Private-repeat `/quote` delegates the full normal quote response, including `billing_seconds`; this leaks a hidden source setting that the server-only contract is meant to protect. | Confirmed; remediation in progress | Private quote response must be explicitly allow-listed and regression-tested for absence of hidden recipe fields. |
| ADV-004 | Medium | Private repeat / legacy compatibility | Legacy generations whose source reference lives in top-level `input_url` cannot currently be satisfied by the repeat UI because `input_url` is not a model UI field. | Regression added; remediation in progress | Playwright case with `reference_fields: ["input_url"]` must upload and launch successfully. |
| ADV-005 | Medium | Private repeat / validation | `references_required=true` with no explicit `reference_fields` does not force the backend to receive a reference; an empty payload can reach model validation/provider logic. | Confirmed; remediation in progress | Unit/API test must reject an empty recipient-reference payload before generation quote/launch. |
| ADV-006 | Low/Design | Private repeat capability | Repeat token is replayable, has no explicit expiry/revocation, and embeds the source generation UUID plus an HMAC. The signature prevents forgery, but possession is a durable bearer capability and reveals an opaque source identifier. | Open design review | Decide whether durable share links are intended; if not, migrate to opaque revocable capability records. |

## Current private-repeat invariants

The intended contract is:

- Source prompt, generation parameters and billing recipe never cross the recipient browser boundary.
- The browser may receive only safe routing metadata required to render the repeat flow.
- The recipient cannot override model, prompt, price-driving parameters, quantity or billing duration.
- Source media is never reused for the recipient.
- Every recipient media URL accepted by quote/launch must be a ready product-owned upload belonging to that authenticated recipient.
- Quote may expose the final price required for consent, but not the hidden source recipe itself.
- Invalid/tampered links and unusable source recipes fail without revealing source ownership or private recipe values.

## Whole-project audit matrix

| Domain | Adversarial questions | State |
| --- | --- | --- |
| Telegram auth / Mini App auth | initData signature/age, browser auth fallback, replay, user identity confusion | Pending |
| Deep links / startapp | token tamper, stale sticky payloads, IDOR, open redirects, replay | In progress |
| Uploads / media | MIME spoofing, size abuse, path traversal, ownership, SSRF, cross-user reuse | In progress |
| Generation API | parameter smuggling, quantity bypass, stale models, double-submit, cost mismatch | Pending |
| Billing / wallet | races, double charge/refund, negative balance, admin-free bypass | Pending |
| Payments | webhook signatures, idempotency, amount/currency mismatch, replay | Pending |
| Provider callbacks | authenticity, task ownership, replay, unexpected payloads, stuck states | Pending |
| Feed / publish / remix | private-data disclosure, IDOR, hidden prompt leaks, stale references | Pending |
| References / presets | cross-user access, arbitrary remote URLs, SSRF chain, deleted references | Pending |
| Admin | auth bypass, capability escalation, CSRF, dangerous bulk actions | Pending |
| Database | constraints, transaction boundaries, stale/orphan records, migration parity | Pending |
| Frontend | hidden data in state/storage, stale route recovery, unsafe navigation, iOS WebView | In progress |
| Deployment | branch protection, exact-SHA deploy, rollback, release smoke | Pending |

## Method

For each finding:

1. Establish a deterministic failing test or other red-capable signal at a public seam.
2. Minimize the reproduction.
3. Apply the smallest safe fix.
4. Add/retain regression coverage for success, failure and adversarial edge cases.
5. Run the relevant local/CI suites and the repository release gates.
6. Record the final commit/PR and production exact SHA here.

The audit is not complete while any high-risk domain above remains `Pending`, or while a finding marked fixed lacks regression and release evidence.
