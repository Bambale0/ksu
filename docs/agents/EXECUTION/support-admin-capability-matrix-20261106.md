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
