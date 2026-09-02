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
| ADV-001 | High | Private repeat | The earlier repeat flow hid the source prompt in UI but still transported the recreate recipe to the browser, exposing prompt/settings through network/devtools. | Merged in PR #387; 6/6 PR workflows green | Backend + Playwright regression: hidden recipe never appears in bootstrap, DOM or request bodies. Main SHA `8d62c6b8929aed98b4d403bc68fb3ddcebb118fe`; production deploy still requires exact-SHA success. |
| ADV-002 | High | Private repeat / media ownership | Private-repeat accepted any syntactically URL-like HTTPS value as a “recipient-owned” reference. A caller could bypass the UI and inject another user’s or attacker-controlled URL. | Merged in PR #387; 6/6 PR workflows green | Quote/launch now require a ready `UserReference` owned by the authenticated user, created by `mini_app_upload`, and using product-owned reference storage. |
| ADV-003 | High | Private repeat / information disclosure | Private-repeat `/quote` delegated the full normal quote response, including `billing_seconds`, leaking a hidden source setting. | Merged in PR #387; 6/6 PR workflows green | Private quote is allow-listed to payable `cost_rox`; regression asserts hidden quote metadata is absent. |
| ADV-004 | Medium | Private repeat / legacy compatibility | Legacy generations whose source reference lives in top-level `input_url` could not be satisfied by the repeat UI because `input_url` is not a model UI field. | Merged in PR #387; 6/6 PR workflows green | Playwright covers a synthetic recipient upload for `reference_fields: ["input_url"]`. |
| ADV-005 | Medium | Private repeat / validation | `references_required=true` with no explicit `reference_fields` did not force the backend to receive a reference; an empty payload could reach model validation/provider logic. | Merged in PR #387; 6/6 PR workflows green | Server-side merge rejects missing required recipient media before quote/launch. |
| ADV-006 | Low/Design | Private repeat capability | Repeat token is replayable, has no explicit expiry/revocation, and embeds the source generation UUID plus an HMAC. The signature prevents forgery, but possession is a durable bearer capability and reveals an opaque source identifier. | Open design review | Decide whether durable share links are intended; if not, migrate to opaque revocable capability records. |
| ADV-007 | High | KIE webhook authentication | KIE callback URLs included the long-lived shared `KIE_WEBHOOK_HMAC_KEY` as `?token=...`, turning a URL-log leak into a global bearer credential. | Remediation in progress | Future callback URLs contain only `generation_id` plus a scoped HMAC binding; the global secret is never placed in the URL and only official KIE signature headers authenticate callbacks. |
| ADV-008 | Medium | Public webhooks / availability | Multiple webhook handlers parse JSON/body before enforcing a small request-body limit. Invalid callers can force unnecessary memory/JSON work before HMAC/API-key rejection on some endpoints. | Confirmed; remediation planned | Add a bounded request-body helper or middleware for webhook routes and tests for oversized payload rejection. |
| ADV-009 | Review | Reference media privacy | Product-owned reusable references are mounted directly under `/uploads/refs` as bearer static URLs. Paths have strong entropy and traversal protections, but anyone possessing a URL can fetch the media without application auth. | Contract review | Confirm this is an intentional provider-transport contract; otherwise introduce signed/expiring delivery URLs or an authenticated media proxy. |
| ADV-010 | High | KIE webhook fail-closed | `verify_kie_webhook()` returned `True` when `KIE_WEBHOOK_HMAC_KEY` was empty. A production misconfiguration could therefore accept unsigned KIE callback requests and let attacker-controlled task IDs reach recovery logic. | Remediation in progress | Verification now returns false without a key; production startup refuses KIE+public callback configuration without `KIE_WEBHOOK_HMAC_KEY`; regression covers the fail-closed case. |
| ADV-011 | High | KIE recovery binding | KIE's official HMAC covers `taskId.timestamp`, but the callback recovery `generation_id` query hint was not included in that signature. In the narrow pre-persist recovery window, a captured valid signed callback could have its generation hint changed. | Remediation in progress | `generation_id` is accepted for recovery only when accompanied by a server-generated HMAC binding scoped to that exact generation. Legacy unsigned hints are ignored. |

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
| Telegram auth / Mini App auth | initData signature/age, browser auth fallback, replay, user identity confusion | Reviewed first pass: signed initData + explicit age check; browser Login Widget signature + 10-minute source credential window. No bypass confirmed yet. |
| Deep links / startapp | token tamper, stale sticky payloads, IDOR, open redirects, replay | In progress |
| Uploads / media | MIME spoofing, size abuse, path traversal, ownership, SSRF, cross-user reuse | In progress; ADV-002/009 recorded |
| Generation API | parameter smuggling, quantity bypass, stale models, double-submit, cost mismatch | In progress |
| Billing / wallet | races, double charge/refund, negative balance, admin-free bypass | In progress |
| Payments | webhook signatures, idempotency, amount/currency mismatch, replay | In progress; 2328 signature algorithm checked against current official documentation, row-lock/idempotent credit path present |
| Provider callbacks | authenticity, task ownership, replay, unexpected payloads, stuck states | In progress; ADV-007/010/011 recorded and remediation underway |
| Feed / publish / remix | private-data disclosure, IDOR, hidden prompt leaks, stale references | Pending |
| References / presets | cross-user access, arbitrary remote URLs, SSRF chain, deleted references | In progress |
| Admin | auth bypass, capability escalation, CSRF, dangerous bulk actions | Pending |
| Database | constraints, transaction boundaries, stale/orphan records, migration parity | In progress |
| Frontend | hidden data in state/storage, stale route recovery, unsafe navigation, iOS WebView | In progress |
| Deployment | branch protection, exact-SHA deploy, rollback, release smoke | In progress; PR #387 main SHA is `8d62c6b8929aed98b4d403bc68fb3ddcebb118fe`, production deploy currently pending exact-SHA success |

## External contract checks

### 2328.io payments

Checked against current 2328.io webhook/authentication documentation on 2026-09-02:

- webhook signature is the `sign` field;
- remove `sign`, compact JSON encode, Base64 encode, HMAC-SHA256 with the payment API key;
- compare in constant time;
- verify amount/currency/order identity and make crediting idempotent;
- webhooks may replay and arrive out of order.

Current implementation matches the signature algorithm, validates local `order_id`, provider UUID and exact amount/currency, and credits via a row-locked/idempotent wallet path. Oversized request handling remains ADV-008.

### KIE callbacks

KIE's current webhook security contract signs `taskId + "." + timestamp` with HMAC-SHA256 and sends `X-Webhook-Timestamp` / `X-Webhook-Signature`. The shared HMAC key is meant to stay secret and does not need to be placed in the callback URL.

The hardened design therefore uses two independent checks:

1. KIE's documented header HMAC authenticates the provider callback and provides the replay window.
2. A separate HMAC value in the callback URL authenticates only the local `generation_id` recovery hint. It is derived from the webhook secret but is not the secret itself and is scoped to one generation.

Legacy callback query `token` values are no longer authentication inputs.

## Method

For each finding:

1. Establish a deterministic failing test or other red-capable signal at a public seam.
2. Minimize the reproduction.
3. Apply the smallest safe fix.
4. Add/retain regression coverage for success, failure and adversarial edge cases.
5. Run the relevant local/CI suites and the repository release gates.
6. Record the final commit/PR and production exact SHA here.

The audit is not complete while any high-risk domain above remains `Pending`, or while a finding marked fixed lacks regression and release evidence.
