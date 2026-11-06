# Support and balance private-read locking audit — 2026-11-06

## Pre-edit scope and evidence

Independent review of the durable support recipient changes found a composition
hazard after their eligibility queries were changed to PostgreSQL `FOR SHARE`.
The notification list and account overview call support authorization first, then
`NeironychBalanceAlertService.authorized_owner(lock=True)`. The latter performs
only an eligibility SELECT but acquires `FOR UPDATE` on the same User and
AdminAccount rows. Two authenticated reads can both hold shared locks and then
attempt incompatible upgrades. The real current-user dependency commits its
identity/bootstrap work before entering these route bodies, so it does not
serialize them.

The bounded isolated regression will issue real signed HTTP requests for the
notification inbox and account overview, synchronize immediately after both
support eligibility reads, and require both complete with the expected private
notifications. No provider requests or production data are involved. The existing
balance read/revocation regressions must remain green to prove that a weaker read
lock still blocks owner demotion until the read transaction completes.

If the failure is reproduced, the intended source change is limited to using
`FOR SHARE` for the balance eligibility read. No eligibility condition, grant,
recipient configuration, financial value, or mutation path changes.

PostgreSQL 17 documents that `FOR SHARE` is compatible with another shared/key
shared read and conflicts with row UPDATE/DELETE and `FOR NO KEY UPDATE`:
https://www.postgresql.org/docs/17/explicit-locking.html#LOCKING-ROWS

## Reproduction

The isolated signed HTTP regression failed as intended before the balance change:
notification inbox completed with 200 while account overview raised DBAPIError
after both support reads held shared eligibility locks. Result: 1 failed in
5.37s; isolated runner log test-run-20261106T062510Z-3661539.log.

## Verification

The isolated PostgreSQL log independently reported `deadlock detected` at
2026-11-06 06:25:30.158 UTC for the RED run. After the one-lock-mode change,
the new real signed HTTP concurrency case plus the complete existing provider
balance suite passed: **38 passed in 10.74s**, runner log
`test-run-20261106T062556Z-3663355.log`. This includes the existing inbox and
profile demotion-blocking tests and delivery/revoked-owner regressions.
Ruff, AST parsing for both changed Python files, and scoped `git diff --check`
passed. No eligibility predicates or mutation behavior changed.
