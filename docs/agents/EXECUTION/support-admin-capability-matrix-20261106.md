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
