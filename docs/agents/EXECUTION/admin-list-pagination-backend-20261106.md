# Admin list pagination backend audit — 2026-11-06

## Scope and ownership

The user asked to check the entire admin area and management of existing entities. After the support delivery core checkpoint, root authorized a separate read-only pagination slice. support_audit owns the API/service changes and isolated regression tests below; admin_audit owns UI pagination and the capability matrix. The primary execution ledger and other agents' files are not overwritten.

## Evidence before implementation

| Endpoint | Existing source | Confirmed limit/gap |
| --- | --- | --- |
| GET /api/v1/admin/referrals/rewards | admin_operations.list_referral_rewards | default 100/max 200, partner/status filters, no offset |
| GET /api/v1/admin/notifications/campaigns | admin_capabilities → AdminNotificationService.list_campaigns | service default 100/max 200, no HTTP paging or service offset |
| GET /api/v1/admin/promocodes | admin_capabilities → AdminPromoService.list_promos | default 100/max 200, no offset; q is a separate exact lookup returning item |
| GET /api/v1/admin/control/promocodes | admin_control → same promo service | same list gap and exact-lookup contract |
| GET /api/v1/admin/cms/documents | admin_capabilities → AdminCmsService.list_documents | default 100/max 200, no offset |
| GET /api/v1/admin/prompts | admin_capabilities → AdminContentService.list_prompts | default 100/max 200, status filter, no offset |
| GET /api/v1/admin/trends | admin_capabilities → AdminContentService.list_trends | first 200 only; dedicated UI searches title/model/tags and active state in that subset |
| GET /api/v1/admin/security/sessions | admin_audit.list_all_sessions | default 100/max 500, active-only filter, no offset |

Three explanations were considered: missing records in storage, intentionally denied read permissions, and truncated list queries/UI. The source confirms the third explanation for any data set exceeding the existing caps. Synthetic rows beyond the cap will reproduce it without assuming production data loss or weakening permissions.

## Planned contract

- Additive list response: items, total, limit, offset, has_more. Existing item shapes and default limits remain unchanged.
- HTTP offset defaults to 0 and is bounded at 100000; apply LIMIT/OFFSET in the database, never to an already capped Python list.
- Count uses the same filters as the page query. Include a UUID tie-break after the existing activity/creation ordering to keep equal-time records stable.
- Preserve referral partner/status, prompt status, and session active-only semantics.
- Keep promo q lookup returning item, including not-found behavior; paging applies only to the list branch.
- Move the dedicated trend UI's existing search to the complete DB set using optional q (max 128) and is_active. Search title, model_id and tags only; do not search private prompts. Treat user % and _ as literal search text.
- No schema migration, financial effect, campaign send, privilege change, session revocation, provider call, or production mutation.

Planned production files: app/api/v1/admin_operations.py, admin_capabilities.py, admin_control.py, admin_audit.py; app/services/admin_notifications.py, admin_promos.py, admin_cms.py, admin_content.py.

## Acceptance and verification plan

Write tests/test_admin_list_pagination.py first, then run it in the existing isolated Docker/PostgreSQL harness with blank provider credentials and an internal-only network. Require a meaningful RED for repeated/ignored pages and missing metadata before product edits.

Cover page 2/page 3 with equal timestamps, one data set beyond the old cap, exact filtered total/has_more including empty final page, current RBAC denial at actual HTTP seams, unchanged promo lookup/defaults, trend title/model/tags search plus active state and exclusion of private prompt text. Clean up only test-owned fixture rows so full-suite order is not changed.

References checked for the trend JSON search implementation:
- https://docs.sqlalchemy.org/en/20/core/functions.html
- https://www.postgresql.org/docs/17/functions-json.html

Verification results: pending RED and implementation.

## Equal-time ordering in existing offset lists (before correction)

UI pagination review and source inspection found existing OFFSET queries ordered only by created_at in main users/generations/payments/withdrawals/audit and shared admin users/reporting/operations/partner-withdrawal services. Equal timestamps therefore have no defined order across pages.

Root explicitly authorized appending only each entity's descending UUID to those existing ORDER BY expressions. Preserve all filters, permissions, limits, response shapes and command behavior. Additional files: app/api/v1/admin_users.py; app/services/admin_users.py, admin_reporting.py, admin_generation_operations.py, admin_partners.py. admin_operations.py and admin_audit.py are already in the paging slice.

Add one actual users-HTTP regression with shuffled insertion order, identical created_at and several pages; assert exact deterministic order, no duplicate IDs and no missing IDs. Do not add mirrored tests for every identical ORDER BY suffix.


## Final implementation and verification

The implemented response is additive: `items`, `total`, `limit`, `offset`, `has_more`. Count and rows share the same filters. Pagination uses database LIMIT/OFFSET with deterministic timestamp/UUID ordering; it does not slice a prelimited Python result. Existing item shapes, permissions, default limits and exact promo `q` lookup remain compatible. The trend filter searches the former UI corpus (title, model_id, ordered tags), handles legacy non-array tags, treats SQL wildcards literally and excludes private prompt text.

New HTTP paging is available on all eight endpoint variants in the evidence table. Defaults remain 100/max 200 except trends (200/max 200) and all-admin sessions (100/max 500); offset defaults to 0/max 100000. Referral partner/status, prompt status and active-session predicates are preserved. Trend q is optional with max length 128, and is_active is optional. Existing offset-based queues received only a final descending entity UUID in their ORDER BY.

### TDD evidence

All commands used the locked isolated runner at /root/ksu-support-admin-test-harness-20261106/run_tests.py, its internal-only Docker network and separate PostgreSQL/Redis. No production environment, provider credentials or production data were used.

| Check | Result | Log |
| --- | --- | --- |
| Clean paging RED, after correcting fixture-only promo normalization | 9 failed, 10 passed in 10.72s; eight endpoint variants repeated their first page at offset 2 and trend q was ignored | test-run-20261106T054124Z-3592831.log |
| Existing users equal-time ordering RED | 1 failed in 4.97s; actual HTTP pages did not follow deterministic UUID order | test-run-20261106T054335Z-3597976.log |
| Final paging regressions | 20 passed in 12.53s | test-run-20261106T054517Z-3600664.log |
| Existing admin parity foundation/integration and console/control/trends surface compatibility | 39 passed in 6.56s | test-run-20261106T054651Z-3603723.log |
| Ruff 0.16.4, AST parsing, scoped git diff --check | All passed for the 13 production files plus regression test | Isolated lint/parse/check command, exit 0 |

Logs are local harness evidence under /root/ksu-support-admin-test-harness-20261106/. Final focused job: job_43e9c980ca3a. Compatibility job: job_ab601689abb2.

The regression suite uses real HTTP/API/service/database seams. It checks equal-time page 1/2/3 ordering and uniqueness, a promo data set with 205 rows and an item beyond the previous cap, filtered counts and final empty pages, eight current RBAC denials, default limits, both preserved exact promo lookup variants, global trend search including Unicode/literal wildcards and private-text exclusion, and the existing users offset endpoint. Fixture cleanup removes only synthetic records owned by each case.

### Changed files and freeze

Production:
- app/api/v1/admin_audit.py
- app/api/v1/admin_capabilities.py
- app/api/v1/admin_control.py
- app/api/v1/admin_operations.py
- app/api/v1/admin_users.py
- app/services/admin_cms.py
- app/services/admin_content.py
- app/services/admin_generation_operations.py
- app/services/admin_notifications.py
- app/services/admin_partners.py
- app/services/admin_promos.py
- app/services/admin_reporting.py
- app/services/admin_users.py

Regression: tests/test_admin_list_pagination.py. Audit: this file.

The source was frozen after GREEN and independently reviewed by root. There is no migration and no change to financial commands, campaign sending, session revocation or authorization policy. Commit, exact-head CI and deployment are handled separately by root; these isolated results are not a claim of production deployment or production UI verification.
