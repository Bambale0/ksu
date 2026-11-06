# Support identity boundary — PR #581 P1 audit, 2026-11-06

## Evidence before edits

Review thread PRRT_kwDOT1THts60azHn identifies raw customer identity returned by AdminSupportService._ticket_view to every support.read principal. The current object includes Telegram ID, username, first name and last name regardless of users.pii. The common list_tickets query also searches those User columns without users.pii, exposing whether a private identity matches a ticket through both results and total counts.

Both main /api/v1/admin/support/tickets and control /api/v1/admin/control/tickets delegate list/detail reads to this service. The internal signed admin ticket endpoints also delegate to it. Assign/update/reply responses contain ticket/message/outbox IDs and state, not this customer identity object.

AdminUserService._view defines the existing identity convention: internal UUID remains visible; denied Telegram ID is *** followed by its last four digits (**** for four or fewer), username and last_name are null, first_name is [restricted]. AdminPolicy.has_permission is the canonical effective-permission function, including explicit allow/deny overrides. Support, moderator and auditor lack users.pii by default; a raw role-name check would be incorrect.

SupportConversationService.notify_operators already stores only generic text and a ticket UUID, with no profile identity, topic or message body. Its worker forwards that generic notice. No notification source change is needed.

## Narrow design and verification

Change only AdminSupportService product code. Pass effective users.pii to the common identity view and reuse the existing Telegram masking function. Build topic/internal-user-UUID/ticket-UUID search predicates for all permitted support readers, adding Telegram ID/username/first-name/last-name predicates only for effective users.pii. Apply the same filtered predicates to list data and total counts. Keep support.read mandatory; users.pii alone grants no support access. Preserve customer conversation text as the authorized support content; do not attempt to redact user-authored messages.

Add actual bearer-authenticated HTTP regressions for main and control list/detail/search across support/moderator/auditor, admin with explicit PII deny, support with explicit PII allow, and privileged admin. Verify safe identifier/topic search remains functional, both fields and count-based search are restricted, and a finance principal with PII but no support permission is denied. Reproduce RED before source edits, then run support regression compatibility.

The previous support activity/pagination regression intentionally tests raw identity and username search but uses a support role without an explicit PII grant. After the new RED evidence, give only that test actor an explicit users.pii allow so its original activity/search assertions remain valid; do not broaden all support fixtures.

Scope excludes UI, role definitions, schema, production data, live delivery and unrelated user API changes. The existing user-list search also has an independent pre-existing PII predicate issue; root was informed separately and owns its scope decision.

## Approved adjacent user-search scope, before edits

Root approved closing the same confirmed search inference in both existing user-list implementations: app/services/admin_users.py (control/internal) and app/api/v1/admin_users.py (main). Both currently apply raw profile predicates despite returning masked fields. Without effective users.pii, user search must match only an internal User UUID; name, username and Telegram ID matching require users.pii. Main currently lacks internal UUID search, so add it to support the restricted search contract while preserving the endpoint's existing response shape. Keep global roles, endpoint permissions, filters, pagination and identity masking unchanged. Actual HTTP main/control regressions must exercise both implementations and explicit allow/deny overrides.

## RED evidence before product correction

The actual bearer-authenticated HTTP suite produced 18 failed / 8 passed in 14.63s on unchanged product behavior: raw support identities for restricted roles (both surfaces), hidden-user search hits/counts on both user implementations, and missing internal UUID search on the main user endpoint. Explicit PII allowances and finance-without-support denial already passed. Evidence: job_d82b301c8e07, test-run-20261106T074319Z-3786810.log.

Implementation is limited to the support view/query and canonical user-list query. The main user-list route delegates to AdminUserService.list_users, preserving response fields, filters, pagination bounds/order and permission checks while removing duplicate search policy.

## Final evidence and source freeze

| Check | Result | Evidence |
| --- | --- | --- |
| New bearer-authenticated HTTP cases before fix | 18 failed / 8 passed in 14.63s | job_d82b301c8e07; test-run-20261106T074319Z-3786810.log |
| Combined PII/support/pagination/parity/privilege-revocation suite | 84 passed in 45.48s | job_3d9367701122; test-run-20261106T074506Z-3792239.log |
| Ruff, AST and scoped diff check | All passed for five Python files | Exit 0 |

The combined suite includes all 26 new HTTP cases, the existing 20 support-delivery cases, all 20 admin pagination cases, and existing admin parity and privilege-revocation checks. The new tests use real bearer sessions and the isolated Redis/PostgreSQL harness rather than bypassing permission dependencies. Explicit users.pii deny overrides an admin role; explicit allow grants a support actor profile visibility and matching search. users.pii without support.read still cannot read tickets.

Restricted identity is identical on main/control list and detail: internal UUID retained, masked Telegram ID, null username/last name, [restricted] first name. Matching by hidden profile fields is excluded from both data and count queries. Authorized support topic, ticket UUID and internal-user UUID search remains available; user-list search without users.pii accepts only full internal User UUID. The existing support activity test now explicitly grants PII to its one raw-identity-search actor, while all new restricted-role expectations remain strict.

The common service also protects internal signed admin reads. Generic incoming notices were traced and remain unchanged. Customer-authored topic/message content remains authorized support.read content; this change does not claim blanket anonymization or redact conversational text.

Owned paths:
- app/services/admin_support.py
- app/services/admin_users.py
- app/api/v1/admin_users.py
- tests/test_support_pii.py (new)
- tests/test_support_delivery_regressions.py (one explicit actor grant in an existing activity/search case)
- docs/agents/EXECUTION/support-pii-boundary-20261106.md (new)

Root independently reviewed the three product diffs and the complete new test file and signed off the identity, search/count, UUID, response-shape and permission behavior. engineering_guidance independently found no source blocker. Product and test source are frozen; root owns the combined snapshot, exact-head CI and release. UI work belongs to admin_audit and is validated separately.

No schema, role grant, production mutation, credential change, live message, historical replay, commit or push was performed. The earlier read-only release baseline and postdeploy script remain available.
