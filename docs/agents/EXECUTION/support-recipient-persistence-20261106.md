# Durable support recipients — PR #581 P1 audit, 2026-11-06

## Evidence and approved scope

Review comment 4489542861 identifies a real lifecycle defect: docs/ADMIN_SECURITY.md explicitly instructs the owner to clear ADMIN_BOOTSTRAP_TELEGRAM_IDS after enrollment, but SupportConversationService currently uses that temporary environment variable for both enqueue and delivery/inbox authorization. Clearing it removes all recipients and hides existing notices. Owner-created support administrators cannot be explicitly assigned as recipients.

Three sources were examined:
1. AdminAccount role/permission grants establish authorization but do not establish an operator's subscription. Broadcasting to every authorized account would include unrelated historical accounts and is not acceptable.
2. UserPreference persists general customer notification and marketing switches. It has no per-admin operational recipient assignment; operational notices intentionally bypass the general customer switch.
3. AdminRuntimeSetting provides an existing persisted JSON setting with a primary key and updated_by_admin_id. This is the approved durable source; no schema migration is required.

Root approved a versioned support_incoming_recipients setting with explicit admin UUID membership and owner-managed support_notifications fields in the existing admin create/update/list APIs. Current bootstrap IDs are only a one-time import source. Explicit stored empty configuration always wins; no automatic all-admin fallback.

## Lifecycle and compatibility

- Import only existing active configured users with active AdminAccount and effective support.read.
- Initialize at startup when eligible configured accounts exist. If there are no eligible accounts, do not create an empty record.
- Seed an absent record after a trusted initial-owner account has been flushed, covering standalone admin login and ordinary Mini App bootstrap.
- After persistence, changing or clearing bootstrap environment configuration does not alter recipients.
- When both the durable setting and eligible bootstrap accounts are absent, remain unconfigured. An owner must explicitly select recipients through admin management.
- New admin support_notifications defaults false. Nullable/omitted update preserves legacy clients; explicit false removes membership.
- Per-admin response exposes support_notifications and support_notifications_effective. Admin list also reports support_notifications_configured and support_notifications_revision.
- Membership alone grants no support access: current User/AdminAccount activity and effective support.read are required at enqueue, inbox/unread access and delivery.

## Locking audit before edits

get_admin_context_base locks AdminSession, validates the principal, updates activity, then commits before returning to require_permission and the route. It does not retain an AdminAccount lock into owner CRUD.

Use the setting row FOR UPDATE before the target AdminAccount lock for owner membership/privilege edits; delivery and sensitive reads acquire the setting FOR SHARE before User/AdminAccount locks. Bootstrap initialization uses INSERT ON CONFLICT DO NOTHING and never overwrites an existing record.

Notifications list/read-all and AccountProfileService currently check provider-balance authorization first, which can lock the same User/AdminAccount. Move the support-policy check before that existing check to preserve one lock order. The standalone and inline bootstrap paths use only one-time non-overwriting insertion, not a new global advisory lock.

## Planned changes and exclusions

New recipient-config service; support conversation recipient selection; owner admin request/view/audit fields; startup and both trusted bootstrap hooks; two authorization-check orderings; ADMIN_SECURITY runbook; new focused recipient regressions. Existing support test HTTP fixture needs RedisDep and the production ResourcePolicyError handler after the separate rate-limit repair.

No schema migration, unrelated permission grant, generic user preference change, production configuration write, live message, historic replay, credential change, commit or push is performed in this implementation slice. Root owns checkbox UI, outbound recovery P2, combined review and release.

## Verification plan

Write HTTP/startup/bootstrap/worker regressions before implementation. Require RED for explicit recipient assignment with empty bootstrap, clearing bootstrap after persistence, first enrollment after empty startup, explicit opt-out, eligibility validation and removal versus in-flight delivery. Retain owner/fresh-MFA gates. Use only the locked isolated Docker/PostgreSQL/Redis runner with provider access disabled. Add focused concurrency evidence and then run the existing support suite together with the rate-limit suite.

Verification results are recorded in the final evidence section below.


## Concrete concurrency review follow-up before correction

Initial recipient regressions passed 13/13 (test-run-20261106T061721Z-3648565.log). The combined support/rate/profile/bootstrap/security compatibility checkpoint passed 68 tests in 23.98s (test-run-20261106T061928Z-3652668.log). These results preceded the following new review case.

Root identified a real lock-cycle opportunity: two selected operators submit customer tickets concurrently. Each ticket/message insert holds a foreign-key KEY SHARE lock on its own User. The enqueue query then asks for FOR UPDATE on every selected recipient User/AdminAccount. Each transaction can wait for the other's customer FK lock. Existing customer authentication does commit profile mutations before the handler, but that does not release these later ticket/message foreign-key locks.

Add an actual two-client HTTP regression with a barrier after both SupportMessage flushes and before notify_operators; require both requests to finish with 201 and both selected recipients to receive exactly one notice per ticket. Reproduce RED before changing eligibility reads to FOR SHARE. FOR SHARE remains incompatible with real User/AdminAccount UPDATE while allowing foreign-key KEY SHARE. Membership row locks and authorization grants remain unchanged.


## Existing admin-edit compatibility before correction

Root reviewed the actual owner edit UI, which submits the current support_notifications boolean together with role/active changes. set_subscription initially validated eligibility before checking whether membership was unchanged. Deactivating a subscribed administrator or moving that administrator to a role without support.read therefore returned 422 and blocked existing management.

Add actual owner PATCH regressions for both changes with the existing true subscription flag, require RED, then validate eligibility only for a new addition to the recipient set. Retain configured=true/effective=false for an existing assignment after access revocation; enqueue/delivery/private access must continue to reject the inactive or unauthorized account. New opt-in to an ineligible account remains rejected by the existing three regression cases.


## Final evidence and source freeze

All recipient changes were tested through the isolated internal-only Docker/PostgreSQL/Redis harness. Customer support requests, owner admin CRUD, real bearer authentication, startup, both trusted bootstrap paths, private inbox and notification-worker dispatch were exercised without external provider access or live Telegram messages.

| Check | Result | Harness log |
| --- | --- | --- |
| Initial P1 behavior RED | 11 failed / 2 passed in 9.38s; missing durable assignment, opt-out, validation and initialization | test-run-20261106T061428Z-3643871.log |
| Initial recipient implementation | 13 passed in 9.99s | test-run-20261106T061721Z-3648565.log |
| Pre-review support/rate/profile/bootstrap/security checkpoint | 68 passed in 23.98s | test-run-20261106T061928Z-3652668.log |
| Concurrent selected-operator customer tickets RED | 1 failed in 7.43s; HTTP outcomes DBAPIError/201; isolated PostgreSQL confirmed deadlock detected at 06:22:03.092 UTC | test-run-20261106T062142Z-3656809.log |
| Existing admin access-edit RED | 2 failed in 6.73s; deactivation and role-to-finance PATCH returned 422 instead of 200 | test-run-20261106T062718Z-3666128.log |
| FINAL combined support/recipient/rate/profile/bootstrap/security/private-read regression | 72 passed in 24.51s | test-run-20261106T062837Z-3668821.log |
| Final Ruff 0.16.4, AST parsing, scoped git diff --check | Passed for all 10 owned Python files and scoped documentation | Exit 0 |

Final combined job: job_a86c39e6ddab. Harness log directory: /root/ksu-support-admin-test-harness-20261106/.

The final suite includes 16 recipient regressions, the existing 20 support-delivery regressions, 11 rate-limit cases, profile/support compatibility, existing Mini App bootstrap and admin security tests, and the independent signed-HTTP private-read concurrency regression. The balance authorization lock upgrade was fixed and independently verified in the separate support-balance-lock audit; this combined run includes that composition.

Final behavior:
- One absent-only bootstrap import persists eligible explicit configured accounts. Empty startup does not prevent later first-owner enrollment through either auth path.
- Persisted empty configuration always wins, and clearing bootstrap does not disable already assigned recipients.
- Owner/fresh-MFA CRUD is the ongoing management path; omitted/null update preserves existing clients.
- A new opt-in requires an active user/account with effective support.read. An unchanged assignment can remain stored but ineffective after deactivation or loss of permission.
- Membership rows use shared read locks and exclusive management locks. User/AdminAccount eligibility reads use FOR SHARE, preserving the revocation barrier without conflicting with customer foreign-key KEY SHARE.
- Removal during in-flight delivery waits for the authorized send, then suppresses subsequent pending delivery and private inbox visibility.
- Concurrent recipient edits preserve both assignments; unrelated administrators never receive a notice merely because their role is eligible.

Root reviewed the final design and concrete corrections. engineering_guidance independently signed off the final membership, bootstrap, permission, owner/MFA, no-op edit and lock behavior with no remaining blocker. Product Python/test source is frozen. Root owns the final full backend/CI/release verification; these results do not claim production deployment.

Owned P1 files:
- app/services/support_recipient_config.py (new)
- app/services/support.py
- app/api/v1/admin_accounts.py
- app/services/admin_security.py
- app/services/inline_admin.py
- app/main.py
- app/api/v1/notifications.py
- app/services/account_profile.py
- tests/test_support_recipient_persistence.py (new)
- tests/test_support_delivery_regressions.py
- docs/ADMIN_SECURITY.md
- docs/agents/EXECUTION/support-recipient-persistence-20261106.md (new)

No schema migration, credential change, production configuration mutation, historical replay, commit or push was performed by this slice.
