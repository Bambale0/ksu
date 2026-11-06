# Admin capability audit — 2026-11-06

## Scope and evidence

Baseline: main `9590eb61ca209b3fcb2cb9a77ab74c3cf49840c7`, reviewed remote-first before the execution worktree was created. Root execution ledger: [support-inbox-admin-audit-20261106.md](support-inbox-admin-audit-20261106.md).

This matrix distinguishes **source review**, **browser execution with mocked APIs**, and **production verification**. A navigation item or green source-contract test does not establish that its real production mutations work. This audit did not send support replies, start campaigns, grant balances, make refunds, or alter production entities.

Actual surfaces: main admin **11 navigation sections**, control console **13 sections**, plus separate trend and creator-partnership pages. Server-side Telegram/internal administration is an additional adapter surface.

## Capability map

Paths below are relative to `/api/v1/admin` unless otherwise stated.

| Capability / current controls | UI and API ownership | Server permission / service | Evidence in this slice |
| --- | --- | --- | --- |
| Login, MFA enrollment, recovery, logout | `admin.js`, `control.js`; `/auth/*` | `admin_deps.py` checks active account/user/session, session expiry, UA/IP binding, live permissions and sensitive step-up | Source review; mocked login executed in every new browser test. Hidden authentication screen regression reproduced and fixed in both pages. No live identity/MFA operation performed. |
| Overview | Main/control overview → `GET /dashboard` | `dashboard.read`; `AdminReportingService` | Source wiring reviewed; overview used as mocked landing page. Real metrics not asserted here. |
| Users | Main list/search/details/history/status/wallet/notes; control list/search/block/unblock/balance → `/users/*`, `/control/users/*` | `users.read/manage`, `users.wallet.adjust` with step-up; domain-scoped history permissions; `AdminUserService` and legacy adapters | Source review. Existing `test_admin_user_history_permissions.py`, `test_admin_parity_integration.py` identified; no production user mutation performed. |
| Generations and operations | Main list + KIE reconcile; control details/replay/refund → `/generations/*`, `/control/operations/*` | `generations.read/manage`, `operations.read/manage`; `AdminGenerationOperationsService` and command ledger | Source review. Main reconcile button is deliberately KIE-only; control is the broader operation surface. Browser executed refund-result handling for already-refunded and no-charge responses with MFA. Root owns ledger/refund regression and provider dispatch fixes. |
| Payments | Main list/filter/reconcile/refund; control recheck/reprocess → `/payments/*`, `/control/payments/*` | `payments.read/manage/refund`; step-up, `AdminPaymentService`, payment-provider services | Source review. Root confirmed and owns missing Payment2328 dispatch. No provider or monetary write executed by this slice. |
| Support | Main/control shared inbox; search/status filter/list pagination, exact-chat launch, previous messages, answer/retry, reopen/status; control additionally assignment/priority | `support.read/manage`; both adapters call common support service / transactional delivery outbox | Browser exercised both UIs with actual assets: 14 scenarios covering list pages, history, reply transport retry, delivery state, mobile reopen, read-only access, delayed requests and navigation races. Backend delivery/worker tests belong to support slice. Assignment/priority wiring source-reviewed. |
| Withdrawals / partner analytics | Main withdrawal list/state; control analytics/withdrawal state → `/withdrawals/*`, `/partners/analytics`, `/partners/withdrawals/*` | `withdrawals.read/manage`, `partners.read/manage`; sensitive payout state requires step-up | Source review. No payout transition executed. |
| Promo codes and referral program | Both consoles create/edit/state/partner binding/program terms → `/promocodes/*` or `/control/promocodes/*` | `promocodes.read/manage`; `AdminPromoService`, command idempotency | Source review; existing promo-state/partner-contract tests identified. No real promo/program changes performed. |
| Referral rewards | Main filter/list → `/referrals/rewards` | `referrals.read`; read adapter | Source review. Mutation belongs to program/partner management, not reward table. |
| Security audit and all admin sessions | Main overview/audit/session list/revoke → `/security/*`, `/audit` | `security.read`, `audit.read`, `sessions.manage` + fresh step-up for revoke | Confirmed duplicate DELETE route bypassed step-up/reason on baseline. Root removes shadow route; UI now requires a 3–500 character reason, handles step-up and confirms execution. Browser RED→GREEN verifies request reason across MFA retry and disappearance of revoked session. |
| Admin accounts and roles | Main account list/create/edit/disable → `/admins`, `/roles` | `admins.read/manage`; owner constraints, step-up, validated permission overrides | Source review. UI preserves existing permission overrides; does not expose an arbitrary override editor. No account-role change performed. |
| Own sessions | Main session list/revoke → `/auth/sessions*` | Current admin session ownership | Source review. Separate from all-admin session revoke route above. |
| Tariffs / model prices | Control JSON tariff editor/publish → `/tariffs`, `/tariffs/publish` | `pricing.read/manage`, step-up; `AdminPricingService` with tariff/model-tier validation | Source review; pricing validation/model-tier tests identified. No price edits performed. |
| CMS | Control create draft/read document/publish revision → `/cms/documents*` | `cms.read/manage`; `AdminCmsService`, versioned publish | Source review; no publication performed. |
| Campaigns | Control segment preview/create/test/start/cancel → `/notifications/preview`, `/notifications/campaigns*` | `notifications.read/manage`; start requires step-up; `AdminNotificationService`, persisted recipient/outbox worker | Source review; existing campaign idempotency/materialization integration test identified. No messages sent. |
| Prompts, feed and quick trends moderation | Control pending prompt moderation, trend create/remove, feed visibility → `/prompts/*`, `/trends/*`, `/feed/*/moderation` | `prompts.read/manage`, `social.moderate`; `AdminContentService` | Source review. Dedicated trend page is used for rich editing. |
| Runtime / providers / alert policy | Control provider routes, prompt-tool routes, subscription requirement, reload, balance alert → `/runtime/*` | `runtime.manage`; revision and command-idempotency checks; fresh step-up for provider/alert mutations | Four existing browser tests rerun GREEN: provider-route revisions/idempotency through MFA, photo/video prompt-tool routes and canceled MFA form preservation, balance-alert settings. APIs mocked; no production provider change. |
| Exports | Control format/type export → `/control/exports/{kind}.{format}` | `finance.read`; `AdminExportService` | Source review; no private export generated. |
| Dedicated trend editor | `trends.html/js`: list/options/create/edit/activate/delete → `/trends`, `/trends/options`, `/trends/{id}`, `/{id}/activate` | `social.moderate`; model-aware server validation/content service | Source route/form inventory; existing `trend-admin-v2`, `trend-category-admin`, `trend-admin-mobile-interaction` browser suites identified. They were not rerun by this slice. |
| Creator partnerships | `creator-partnership.html/js`: application filter/decision, agreement edit, period grant → `/creator-partnership/*` | `partners.read/manage`; grant sensitive/step-up | Source inventory. Separate page exists; main index does not link it directly. No contract/grant mutation executed. |
| Telegram admin / internal admin adapters | `app/bot/handlers/admin*.py`, `internal_admin.py` | Live admin authorization, HMAC/body/timestamp/network validation for internal adapter, shared services | Source/test inventory only. Not an end-to-end Telegram button audit in this slice. |

## Confirmed corrections in the UI slice

1. Both support pages now use `support-inbox.js` against their respective canonical API adapters. This prevents the old main-admin answer path from bypassing the new command headers and delivery status display.
2. Search and list pagination expose existing conversations beyond the original first page. Search label matches server-supported fields; it does not claim full-text message search.
3. History initially shows the latest page, loads previous messages by cursor, merges/deduplicates pages, and explicitly distinguishes unknown historical delivery status from delivered messages.
4. Closed/resolved conversations have an explicit reopen action. Both read-only views hide support mutation controls.
5. Reply drafts survive network errors and navigation. Retrying the same draft reuses its idempotency key; in-flight state survives rerender, and new text typed during a request is preserved.
6. Async replies cannot reopen a conversation the operator has left. Concurrent opening/refreshing cannot mix cached messages from different users.
7. Shared CSS now honors the HTML `hidden` attribute. Visual review found the previous `display:grid` rules kept login and other supposedly hidden controls visible after login.
8. All-admin session revoke now supplies a reason and performs the existing MFA confirmation flow.
9. Operation refunds distinguish `refunded`, `already_refunded`, and `no_charge` instead of claiming every response created a new credit.
10. Admin assets have a cache version. Playwright CI triggers on admin assets and includes the new suite in the explicit WebKit selection; existing mocked control-console fixtures load the new shared script.

## Verification record

Executed on the isolated execution worktree, using actual admin HTML/CSS/JavaScript and Playwright route mocks. Browser traffic never targeted production APIs.

- New suite: `frontend/mini-app/e2e/admin-support-inbox.spec.mjs`, **17 Chromium cases GREEN**.
- Existing suites: `admin-provider-routes.spec.mjs`, `admin-prompt-tool-routes.spec.mjs`, `admin-neironych-balance-alert.spec.mjs`, **4 Chromium cases GREEN**.
- Total: **21/21 Chromium GREEN**.
- RED was observed before corrections for list identity/access, session-revoke reason, pending-send rerender, mixed-user cached history, hidden login panels, and misleading refund outcomes.
- Both mobile support pages were rendered at 390×844, checked for document overflow, and screenshots inspected. Console page exceptions and unexpected mocked requests are asserted absent.
- Local WebKit execution was attempted but unavailable: host lacks WebKit shared libraries (GTK/GStreamer/WOFF/GLES and others). No production OS packages were installed. WebKit remains an explicit CI gate in the existing Playwright container.
- `node --check` passed for modified admin/control/shared scripts; parent runs final backend/CI gates.

## Remaining coverage boundaries and source observations

- Most non-support lists still request a fixed first 50 or 100 records; some have filters/search, but this slice did not add universal pagination. Large payment/operation/withdrawal catalogs therefore need a separate access-completeness check.
- Control-console navigation is not filtered by each account's permissions. The API still enforces permissions; visibility of a menu item is not permission to execute its action.
- The creator-partnership page exists but has no direct link from the main index.
- Inbox polling merges the latest 100 messages with loaded history. More than 100 new messages between refreshes can leave a gap after history was previously considered complete. This is not a claim of an unlimited, gap-free real-time stream; cursor paging and normal refresh were tested.

This is a source-level inventory of the entire admin control surface plus targeted executable regression coverage. It is **not** a claim that every administrative mutation was exercised against production or that delivery to a real Telegram recipient has already been verified.


## Follow-up audit: complete access to existing records

Authorized follow-up: inventory pagination contracts before edits, expose supported server pages while retaining filters, link the existing creator-partnership page with its permission, and align control navigation with live capabilities. Production mutations remain excluded. Root has captured the previous UI snapshot; this is a separate implementation slice.

Baseline execution HEAD: `1b52d3b759e29823fdda114f9f2ec4d9955b40fe`. Initial backend gap assessment is pending source inventory; no unsupported client-only paging will be introduced.

### Source inventory before pagination implementation

| List API | offset already accepted/applied | total before follow-up | Decision |
| --- | --- | --- | --- |
| Main users / generations / payments | yes | yes | Add explicit client pager, preserve filters |
| Main withdrawals | yes | no | Pager uses full-page continuation; no invented total |
| Main audit | yes | no | Independent audit pager; session list unchanged |
| Main referral rewards | no | no | Backend slice adds DB paging before UI is accepted |
| Control users / payments | yes | yes | Add explicit pager |
| Control operations | yes | no | Full-page continuation fallback |
| Partner withdrawals | yes | no | Independent withdrawals pager |
| Campaigns | no HTTP offset, service capped 100 | no | Backend slice adds bounded paging |
| Promo list (main/control) | no HTTP offset, service capped 100 | no | Backend slice adds bounded paging; lookup q retains existing item contract |
| CMS documents / prompts | no HTTP offset, service capped 100 | no | Backend slice adds bounded paging |
| Creator applications / agreements | yes | yes | Two independent pagers; application status preserves/reset semantics |
| All-admin sessions | no | no | Backend gap; no fake client paging |
| Rich/quick trends | no, service capped 200 | no | Backend gap; no fake client paging |
| Tariff versions | no HTTP offset, service capped 100 | no | Backend gap, not a current-entity list |
| User combined history | no, source-capped | no | Backend gap, not changed by list pager |

Backend additions are separately audited in `admin-list-pagination-backend-20261106.md`; UI does not implement unsupported offsets silently. Browser RED before edits: main/control users lack Next and control navigation exposes finance sections to support-only operator.

### Follow-up implementation and browser verification

- Added shared `admin-pagination.js`. Each list explicitly constructs its own query and mounts its own pager; there is no interception of API calls. Next uses server `has_more`/total when available, otherwise a full returned page permits one further request. A short/empty terminal page disables Next and retains Previous.
- Main: users, generations, payments, withdrawals, referral rewards, promo codes, active admin sessions, audit history.
- Control: users, payments, generation operations, campaigns, CMS documents, promo codes, prompts, quick trends and partner withdrawals.
- Dedicated trend editor: server-wide query and active/inactive filtering, offset reset on filter changes, paging; removed page-local search that would hide older matching records.
- Creator management: application and agreement queues have independent offsets; application status resets only its queue. Summary labels explicitly identify page-local counts.
- Main and control now link the existing creator-partnership page only with `partners.read`, preserving Telegram launch query/hash.
- Control navigation uses the current `me.permissions` capabilities. An account without overview access lands in its first allowed section. The compound moderation screen fetches prompt/social data only when the respective capability is present.
- The 24 new browser cases reached a synthetic old record beyond page one and asserted actual offset/filter query values through Next → Refresh → Previous. Independent creator queues, global trend search, support-only navigation, creator-link permission and prompt-only moderation were also exercised.
- Combined regression run: **45/45 Chromium GREEN** (24 pagination/navigation + previous 21 support/security/runtime/refund). Log: `/tmp/ksu-admin-pagination-browser-20261106.log`.
- Existing runtime fixtures now include the real `me.permissions` field; their mutation/MFA/revision assertions remain intact.
- All four admin pages load the new helper; changed admin/control/trend/creator scripts and styles use `v=20261106-pagination`. CI WebKit selection includes `admin-pagination.spec.mjs` and the separate `media-download.spec.mjs` fix.
- The earlier source gaps for paged queues, creator navigation and control navigation are superseded by this follow-up. Unchanged boundaries: tariff-version history and combined user history remain separately bounded; the browser tests use mocked APIs, not production writes. Backend DB paging is verified by the backend slice, separately from these browser contracts.

### Follow-up review and source-contract gate

- Isolated source-contract runner: `test_admin_console.py`, `test_admin_control_surface.py`, `test_admin_trends_surface.py`: **22/22 GREEN**. One assertion was updated from the former literal unpaged trends URL to the actual query URL and pager invocation; authentication, CRUD and idempotency assertions remain unchanged.
- Independent read-only UI review found no new blocking pagination defect. Generic main/control renderers retain their pre-existing lack of a global stale-navigation guard; the stronger stale-response guarantee applies to support and the dedicated trend/creator views only.
- Final capability audit found a backend/UI contract mismatch: `admin_auth.login/me` uses `admin_security.effective_permissions`, which only enumerated legacy `ROLE_PERMISSIONS`, while `AdminPolicy.has_permission` also grants `ROLE_PERMISSION_SUPPLEMENTS`. Owner `*` masked this in older fixtures. Root owns the required backend capability-enumeration correction and role/deny regression tests before the RBAC navigation change is accepted. The UI deliberately does not duplicate role-to-permission configuration.

## Follow-up audit before capabilities change — 2026-11-06

The new permission-aware Control navigation exposed an existing mismatch in the
actual login/me contract. Both `admin_auth.login` and `admin_auth.me` serialize
`admin_security.effective_permissions`, which only includes legacy
`ROLE_PERMISSIONS`; the endpoint gate `AdminPolicy.has_permission` also includes
`ROLE_PERMISSION_SUPPLEMENTS`. Consequently a normal active admin or finance
operator receives an incomplete capability list and cannot discover already
authorized pricing, operations, partners and other Control sections. The
owner-wildcard browser fixtures did not demonstrate the real non-owner contract.

A second confirmed representation defect is wildcard + explicit deny: the old
serializer returns `["*"]` for owners even when the endpoint policy rejects the
denied permission. Deny-all is also not applied correctly to serialized grants.
The policy itself already treats deny before role/allow and rejects inactive
accounts. This change must preserve those endpoint grants, including explicit
allows, and leave the older `admin_security.has_permission` call sites unchanged.

Plan before source edits: add separate signed login/me ASGI regressions using
synthetic persisted administrators, real session authentication and isolated
Redis/PostgreSQL; reproduce the omitted role supplements and deny mismatch.
Then share the existing effective policy calculation between AdminPolicy and
the serializer without a circular import. Wildcards remain compact only without
denies; wildcard + deny enumerates all registered capabilities plus explicit
allows. The registered owner-only permission `admins.manage` must remain visible.
No role grant, production account, permission override or production API call
will be changed.

Logout read-only check: main `clearSession`, Control `logout`, and dedicated
trends `logout` already call `pagination.reset()`; the creator page has no logout
or account-switch control and its memory disappears on navigation/reload. No
confirmed cross-session pager leak requires an additional UI change in this
slice.

Capabilities RED: isolated real signed login/me/session regression produced **14 failed, 4 passed** (job_de3e4243b4f5). Failures specifically prove omitted supplements for all five non-owner roles, wildcard/exact deny and deny-all mismatch, and inactive-account serializer mismatch. Auth/MFA setup, owner wildcard without denies and legacy grants already passed.

### Capabilities fix and verification

Resolved the login/me contract with one shared module,
`app/services/admin_permissions.py`. The existing base role definitions,
supplements, action definitions and legacy predicate were moved without changing
their values. `AdminPolicy.has_permission` delegates to the same effective
predicate that filters the serialized capability list; the old
`admin_security.has_permission` import continues to expose its original grants.
There is no circular import and no account/grant migration.

The response now includes supplemental and explicit grants, applies exact and
wildcard denies, and reports no permissions for an inactive account. An
unrestricted wildcard still serializes as `["*"]`. A wildcard with exceptions
expands the registered role/action permissions, including owner-only
`admins.manage`, then removes denied entries and retains explicit custom allows.
This finite UI representation does not narrow runtime wildcard authorization:
`future.unknown` remains allowed unless the old policy would deny it.

Verification after the confirmed RED:

- **54 passed** in the isolated runner, including **20 new capabilities
  regressions** and existing admin security, policy, user-history authorization,
  account privilege revocation and composed session-revocation HTTP tests.
  Job `job_4f4138596213`; pytest 14.81 seconds.
- **7 creator-partnership contract tests passed** separately after replacing the
  old source-file-literal assertion with actual `AdminPolicy.action` checks for
  permission, confirmation and grant step-up. The existing API guards remain
  asserted. Job `job_754df3d676c8`; pytest 3.72 seconds.
- New integration cases use signed synthetic Telegram initData, actual TOTP,
  persisted isolated admin/session records and real login/me routes. No auth
  dependency is bypassed. Cases cover every existing role, explicit and wildcard
  allow/deny, owner deny, MFA setup, and deactivation.
- Pure parity verification covers seven roles (including unknown), both active
  states, nine override combinations and all registered permissions plus custom
  and unknown permissions. An AST-backed assertion catches omitted permission
  literals in route/action gates when expanding wildcard exceptions.
- Ruff on all five changed Python files, AST parsing and `git diff --check`
  passed. Root independently compared the five moved definitions with the
  previous source and confirmed equivalence. Independent engineering review
  also signed off with no new blockers: auth/MFA/inactive/session-version paths,
  legacy imports, acyclic dependencies, wildcard semantics and deny precedence
  were checked against the actual diff and the GREEN54 + GREEN7 results.

Pagination backend completion was independently delivered by the support agent:
**20 pagination/RBAC tests passed**, plus **39 compatibility tests passed**.
Its source audit and exact endpoint coverage are in
`docs/agents/EXECUTION/admin-list-pagination-backend-20261106.md`. These counts
overlap some existing contract suites and are not added into a unique grand
total. UI coverage remains the earlier **45/45 Chromium** result.

This final slice changed only the shared permission implementation, its existing
import adapters, a dedicated regression file, the legitimate creator policy
contract assertion and this audit record. The earlier admin UI/pagination and
workflow files remain frozen. Logout/reset inspection found no further confirmed
cross-session pagination defect. No production CRUD, user reply, notification,
balance, grant or permission override was executed.

## PR review P1: customer support write rate limit — pre-edit audit

Review comment 4489542846 identified an authenticated abuse path: customer
`POST /support/tickets` and `POST /support/tickets/{id}/messages` each persist a
message and enqueue an operator notice, with no common per-customer admission
limit. Repeated requests can therefore produce unbounded operator notification
traffic. Operator replies are a different authenticated flow and must remain
available when a customer's budget is exhausted.

Existing source was inspected before editing: `AbuseProtectionService.consume`
already implements atomic fixed-window `INCRBY/EXPIRE/TTL` in one Redis Lua
script; `app.main.resource_policy_error` exposes 429 or fail-closed 503 with
`Retry-After` and a typed error code. The global
`ABUSE_PROTECTION_ENABLED` / `ABUSE_FAIL_CLOSED` settings define availability
policy. Generation, upload and payment limits govern different actions and
cannot safely stand in for a support-message quota.

Accepted implementation scope: a typed
`SUPPORT_MESSAGE_RATE_LIMIT_PER_MINUTE` setting, default **10**, documented in
`.env.example`, with nonnegative validation. As with the existing primitive,
**0 disables this particular quota**; the global protection switch and
fail-open/fail-closed behavior remain unchanged. Both customer write endpoints
share one `abuse:support:user:{user_uuid}` key and a per-minute window. Admission
occurs after content/ownership/status validation but before creating a support
record or invoking message notification. Redis rejection must leave support
records and enqueue calls unchanged. Operator routes are excluded.

Test plan: real signed customer HTTP requests, real isolated Redis/PostgreSQL,
shared create/reply budget across tickets, concurrent mixed requests, invalid
payload/foreign/closed ticket behavior, Retry-After from TTL and expiry recovery,
unavailable Redis, explicit disable/fail-open policies, and an operator reply
after exhaustion. Notification entry is spied while preserving the real service;
no Telegram worker or production action is run. Existing support regression
fixture is owned by the recipient agent; this slice owns the separate new rate
test and the direct-call profile/support fixture adjustment.

### Customer support rate-limit result

Confirmed RED: **8 failed, 3 passed** (`job_e573b22b29ed`), including all 20
concurrent mixed create/reply requests being accepted against a configured
budget of three. Excess and unavailable-Redis requests incorrectly returned 201.
After the minimal admission guard, **22 tests passed**
(`job_569aacac89e9`, 10.39 seconds): 11 new HTTP/config tests plus existing
profile/support and abuse-protection suites. The concurrency regression now
allows exactly three requests; rejected requests create no extra support rows or
notification calls. TTL-based retry, real-key expiry, per-user isolation,
validation ordering, operator replies and existing policy switches are covered.
Ruff/AST/diff checks and independent engineering review passed.

The only existing customer-write callers found under tests were the delivery
regression fixture and profile/support direct calls. The latter now supplies a
real isolated Redis client; the recipient agent owns the delivery-fixture update
and final combined run. Customer read routes and operator routes gained no new
limiter dependency. This limit covers the authenticated customer API; the bot's
legacy fallback writer does not invoke the new operator-notification service.

## Explicit support recipient UI — pre-edit audit

The approved backend contract adds a persisted, opt-in recipient mapping managed
through existing owner-only admin create/update forms. `GET /admin/admins`
returns per-row `support_notifications` (configured) and
`support_notifications_effective` (currently eligible), plus top-level
`support_notifications_configured` and revision. The list contains all admin
accounts, so zero eligible recipients can be derived from the returned rows.

Before edits, `renderAdmins` was inspected along with generic checkbox handling,
`openStepUp`, OTP verification and the explicit execute click. Existing create
and edit controls already require both owner role and `admins.manage`; changes
already run through fresh MFA and an explicit final execution step. The missing
UI control prevents an owner from managing the new durable recipient mapping.

Planned narrow change: add an unchecked-by-default create checkbox and an edit
checkbox using the persisted configured value, include its boolean in the
existing MFA-confirmed payload and confirmation description, show configured and
effective recipient states in the account table, and show an owner-only warning
when configuration is missing or there are zero eligible recipients. Do not
infer opt-in from role or change any grants. Extend the existing admin support
browser spec (already included in Chromium and WebKit CI), prove RED for absent
checkbox/status/warning, then verify enable/disable and create behavior only
after the existing MFA + execute flow, and absence of owner controls for
non-owners. Cache-bust the main admin script.

### Explicit support recipient UI — result

The six new browser cases were first **RED** against the old UI
(`job_b3da7c6e0fc2`): the checkbox, configured/effective table state and owner
warning were absent. The narrow renderer change now provides:

- An unchecked create checkbox and an edit checkbox populated from the
  persisted `support_notifications` value, with explicit boolean POST/PATCH
  payloads.
- The selected notification state in the existing sensitive-action description.
  Verification and the separate execute click remain mandatory in the UI.
- Configured and currently eligible states shown separately. “Получатель
  активен” describes eligibility and does not claim Telegram delivery.
- An owner-visible warning for unconfigured recipients or zero eligible rows.
  Non-owners retain read access where authorized and receive no owner controls.
- A new `admin.js?v=20261106-support-recipients` URL in the main HTML.

Final targeted Chromium run: **23/23 passed**
(`job_b3925e03fa3a`, 21.8 seconds), comprising the 17 previous
support/security/refund scenarios and six new recipient scenarios. The first
post-change run had 20 passing cases and three new-test navigation/locator stops;
the journey was corrected to open the mobile sidebar and target the visible role
combobox. No product guard or expected result was weakened.

The mobile enable/disable case exercises 390×844 layout, menu navigation,
checkbox state, reason input, OTP verification, explicit execute, payload and
reloaded status. Its screenshot was visually inspected: all form fields and
both action buttons fit, with no document-width overflow. Console page errors
and unexpected requests remained empty. The spec was already in both Chromium
and WebKit CI selections; local WebKit availability remains the previously
documented limitation. Node syntax and diff checks passed.

Rate product files and this recipient UI are stable. The recipient backend
agent owns the combined delivery/rate/profile validation and final recipient
concurrency fix; its final shared integration result is recorded in that audit
and the parent execution ledger. This UI run used synthetic browser API data
and did not change any real administrator or send notifications.

Independent engineering review signed off the recipient UI after reading the
actual renderer, six new cases and GREEN23 output: no automatic opt-in, boolean
payloads, configured/effective distinction, owner gates, reason and the existing
MFA/execute sequence were preserved. Rate and recipient UI source are frozen.

A final read-only rate compatibility check found that the customer support
create/reply handlers clear drafts only after the awaited request succeeds.
`customerRequest` throws for 429; the existing HTTP mapper displays “Слишком
много запросов. Попробуйте чуть позже.” in the page alert and preserves the draft.
No frontend change or additional test was needed. The current ROXY real-browser
runner overrides its legacy support/profile scenario with profile/partner
navigation and makes zero support writes, so this new budget is not exhausted
by that seven-scenario gate.


## Follow-up audit: browser attachment MIME (2026-11-06)

This slice follows actual PR CI failure: Chromium passed the download scenarios;
WebKit mobile 1.56.1 timed out on both browser-fallback download events. No
production request, file, or recipient was changed during reproduction.

Pre-edit evidence:

- Exact CI image mcr.microsoft.com/playwright:v1.56.1-noble, installed
  Playwright 1.56.1, isolated network-none container with read-only source:
  unchanged download spec reproduced **2 passed / 2 failed** (job_eae793ecc598).
- A real loopback HTTPS server and the same PNG bytes/filename reproduced the
  failure independently of Playwright route fulfillment. The response was 200
  with Content-Disposition: attachment, but the resulting DOM rendered an
  image; no download event occurred. Both self/blank target and with/without
  noreferrer behaved the same (job_14ee1250efd6).
- Serving those exact bytes as application/octet-stream completed the actual
  download with the expected filename and identical saved bytes in all four
  target/rel combinations. A separate HTTP/HTTPS and mobile/desktop comparison
  also succeeded (job_60a8940d3ec6). Explicit acceptDownloads was enabled.
- Existing local attachment responses preserve image/video MIME. The S3
  presigner overrides Content-Disposition only. Both therefore need the same
  explicit attachment MIME contract. Preview MIME and stored media metadata
  must remain image/video MIME.
- Upstream corroboration: microsoft/playwright#34076 reports renderable image
  attachments opening inline in Playwright WebKit. Our local result, not the
  issue alone, is the regression evidence.

Approved minimal scope: local signed ?download=1 and authenticated /download
responses use an octet-stream attachment; S3 download presigns include
ResponseContentType alongside existing disposition. Ownership, signature,
expiry, object-key binding, preview MIME, bytes, filename and range semantics
remain covered. HTTP regression first, then implementation, then browser fixture
mirrors that real response contract. Native throw must explicitly prove the
native API was invoked; cancel must not download. No skip or weaker href-only
assertion is acceptable.


### MIME follow-up result and final freeze

Two independent causes were confirmed, so neither was hidden by changing the
assertions:

1. Product attachment MIME: image/png attachments rendered inline in this
   WebKit. Explicit local downloads now use application/octet-stream. S3
   attachment presigns include ResponseContentType with the existing
   ResponseContentDisposition; preview presigns retain neither override.
2. Playwright 1.56.1 transport limitation: route.fulfill still did not produce a
   download event even with octet-stream, while a real HTTPS response with the
   identical payload completed successfully (job_56f40340225b). The committed
   browser fixture therefore runs a real loopback HTTPS server, an ephemeral
   port and a runtime certificate. It closes connections/server and removes
   certificate files in finally. Certificate verification is disabled only in
   this test context.

Evidence after the smallest source change:

- HTTP RED: **6 failed / 6 passed**, all failures on the intended MIME/response
  override contract (job_f2240301cc0c).
- HTTP and storage compatibility GREEN: **30 passed, 6.28 seconds**
  (job_5d3dd7fef9eb). Suites: test_media_download_contract,
  test_local_media_storage, test_media_storage, test_legacy_media_backfill,
  test_generation_delivery_media_contract.
- Actual browser GREEN in the same official CI image: **8 passed, 21.8 seconds**
  (job_92b230491af8): four Chromium plus four mobile WebKit. Browser fallbacks
  verify the completed download, saved file bytes, suggested filename, exact
  HTTPS URL, one GET and absence of the Telegram authentication header.
  The native-error test additionally proves the native API was actually called
  before falling back; the cancel path produces no attachment request.
- HTTP coverage preserves owner checks, signed expiry/tampering/object-key
  binding, image/video preview MIME, original PNG/MP4 bytes and byte ranges.
  The S3 tests perform real offline SigV4 signing with synthetic credentials;
  they do not contact external storage.
- Ruff, Python AST for all three Python files, Node syntax and git diff --check
  passed. Independent engineering review signed off the source and personally
  inspected both GREEN job results.

Changed files in this follow-up: app/api/v1/media.py,
app/services/object_storage.py, tests/test_media_download_contract.py,
frontend/mini-app/e2e/media-download.spec.mjs, and this audit.

Primary references read for corroboration:
[Playwright image-attachment report](https://github.com/microsoft/playwright/issues/34076),
[Playwright routed-download report](https://github.com/microsoft/playwright/issues/28253),
[official S3 GetObject response overrides](https://docs.aws.amazon.com/AmazonS3/latest/API/API_GetObject.html).
The exact 1.56.1 local reproduction is the deciding evidence, rather than the
historical reports alone.

Source is frozen for the parent snapshot. No production deployment or
production messages occurred in this slice. Telegram's native download was
verified through its browser API contract; an actual Telegram device download
remains outside this verification.


## PR review follow-up: session retention and interrupted history (2026-11-06)

Pre-edit source audit for review comments 4489916182 and 4489916210:

- The main admin edit form always submits permission_overrides although that
  field is not editable. update_admin treats every non-null overrides payload
  as a privilege change, even when identical; subscription-only and no-op edits
  therefore revoke the target's sessions, including an owner's own session.
  Fix scope: compare final persisted overrides with the previous value, preserve
  owner normalization, and omit the uneditable blob from the edit form. Actual
  role, active-state and overrides changes must still revoke all target sessions.
- The shared inbox keeps historyComplete after a refresh with a disjoint latest
  100-message page. More than 100 arrivals can leave a middle gap with no older
  paging control. Fix scope: detect a disconnected latest page, resume from its
  cursor, preserve cached messages/draft, and finish once all unique messages
  reported by the API are present.
- Root's independent worker fix adds claimed and delivery_unknown states.
  The inbox must display queued and unconfirmed delivery explicitly, tell the
  operator to confirm receipt before another send, and expose no resend action.

Verification planned before product edits: real HTTP PATCH with actual owner/
target bearer sessions and fresh MFA session state; browser journeys on both
admin surfaces, including a fully loaded 150-message history followed by 250
new messages, gap loading, deduplication, draft preservation and delivery labels.
No production edits, auth probes or messages are part of this follow-up.


### PR review follow-up verification and freeze

- HTTP RED: **5 failed / 3 passed**, job_71849eec5fd1. Subscription-only,
  unchanged and owner-self edits incorrectly incremented session_version;
  existing real privilege-change behavior remained green.
- Browser RED: **5 failed**, job_248694432093. The real edit form submitted
  uneditable overrides; both inboxes hid the gap-loading control; neither
  displayed the new delivery states.
- Backend GREEN: **39 passed, 13.40 seconds**, job_4fb47b342f83. New real HTTP
  PATCH/session tests plus admin privilege revocation, admin security and
  persisted recipient compatibility. Existing target/self sessions remain
  usable through subsequent authenticated /auth/me requests for unchanged
  access. Actual role, active and overrides changes still revoke all target
  sessions and increment their version once.
- Browser GREEN: **54 passed, 1.1 minutes**, job_ae9e91733a04: 27 Chromium and
  27 mobile WebKit scenarios in the same official Playwright 1.56.1 image.
  Both surfaces restore the missing middle of a complete 150-message history
  after 250 new arrivals, ending with all 400 unique messages in order and
  the original draft. Backfill stops when the API total is satisfied.
- Both inboxes label claimed messages as queued and delivery_unknown as
  unconfirmed, with a receipt-check instruction and no automatic/manual
  resend control. The request/worker state tests are owned by the parent slice.
- All prior reply retry, navigation race, draft preservation, RBAC, MFA,
  recipient controls and refund-result browser cases remain green.
- Ruff, Python AST, Node syntax and git diff --check passed. Index/control
  pages reference the updated shared script version; main admin.js is also
  cache-busted.
- Independent engineering review personally inspected both GREEN results and
  approved the actual source/test diff. No additional blocker or test was
  requested.

This closes the previously documented disjoint-refresh history gap. The
changes are frozen for the parent snapshot; no production mutation, commit or
push was performed by this slice.

Follow-up files: app/api/v1/admin_accounts.py; app/web/admin_app/admin.js;
app/web/admin_app/support-inbox.js; app/web/admin_app/index.html;
app/web/admin_app/control.html; tests/test_admin_account_session_changes.py;
frontend/mini-app/e2e/admin-support-inbox.spec.mjs; this audit.


## Follow-up audit: support identity and PII-aware search (2026-11-06)

Pre-edit review of the reported support PII boundary:

- The shared inbox directly renders username, first/last name and Telegram ID,
  and always advertises name/Telegram-ID search. Neither console passes a
  users.pii capability to this renderer.
- The canonical backend slice will retain internal user/ticket UUIDs but redact
  identity without effective users.pii using the existing AdminUserService
  convention: username/last_name null, first_name [restricted], and Telegram
  ID *** plus its last four digits (**** for short IDs).
- Restricted support search remains topic or internal user/ticket UUID only.
  The same boundary defect was confirmed in user-list search; backend owns
  predicate restrictions and main-route delegation. Without users.pii its
  search accepts the full internal User UUID only.
- Main/control user search hints currently promise PII search to every role.
  These hints must reflect the capability contract.
- UI scope is deliberately limited to shared support identity rendering,
  capability wiring, search hints and browser contracts. Backend serialization,
  authorization and search predicates remain the backend agent's responsibility.
  Content of customer-authored ticket messages is not a profile identity field.

Planned UI behavior: effective capabilities decide search hints and full identity.
Without users.pii, the support identity renderer uses only an already masked
Telegram value and the internal UUID, and ignores raw name/username fields even
if a stale response contains them. No browser-side redaction is treated as the
server authorization boundary. Real browser RED will cover both consoles,
restricted and allowed capabilities, list/detail identity, non-PII searches,
and the user-search hint/UUID path. No production reads/writes or messages.

### PII frontend verification and freeze

- Browser RED: **6 failed / 4 passed, 30.1 seconds**, job_eb61810f4462.
  Restricted users were offered unsupported PII searches in both consoles;
  the shared inbox also exposed raw legacy identity fields without users.pii.
  The four allowed-capability scenarios already passed.
- Browser GREEN: **118 passed, 2.5 minutes**, job_755627df8303:
  59 Chromium and 59 mobile WebKit cases using the official Playwright 1.56.1
  image. The complete support-inbox (31 cases) and admin-pagination (28 cases)
  browser files passed in each engine.
- Restricted support list/detail render a recognized masked Telegram value and
  stable internal UUID, ignore raw legacy profile fields, and advertise topic/
  internal UUID search. The allowed users.pii path retains full profile identity
  and PII search. Tests deliberately separate role from effective capabilities:
  an owner without the capability is restricted, and a support role with an
  explicit capability is allowed.
- Main/control user-search hints now advertise only the internal User UUID
  without users.pii. Browser journeys fill the UUID, perform the actual search
  action and assert the outgoing q parameter and masked result. Allowed paths
  preserve username search and full identity.
- The browser fixtures verify UI behavior and request contracts; server-side
  redaction and predicate authorization are covered by the separate backend
  slice. Customer-authored topics/messages may themselves contain personal
  information and remain readable by support.read. No automatic content
  anonymization is claimed.
- Node syntax checks on the three product scripts and two browser files passed.
  HTML entry points cache-bust both the shared inbox and their main/control
  scripts with the support-pii version. git diff --check passed.
- Parent and independent engineering review both signed off the source. The
  engineering reviewer personally retrieved the full GREEN118 job result.

Changed files in this UI slice: app/web/admin_app/support-inbox.js;
app/web/admin_app/admin.js; app/web/admin_app/control.js;
app/web/admin_app/index.html; app/web/admin_app/control.html;
frontend/mini-app/e2e/admin-support-inbox.spec.mjs;
frontend/mini-app/e2e/admin-pagination.spec.mjs; this audit.

All eight files are frozen for the parent snapshot. No production data was
read or changed, no messages were sent, and no commit or push was performed.
