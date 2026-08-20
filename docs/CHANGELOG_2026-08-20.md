# Documentation sync — 2026-08-20

This synchronization aligns the documentation set with the merged ROXY runtime after the WAN 2.7 photo / generation pricing / live admin tariff work and the generation recovery hardening merged in PR #180.

Updated or added in the earlier sync:

- root `README.md`;
- canonical `docs/README.md` index;
- `CURRENT_STATE.md` and documentation maintenance policy;
- generation Mini App flow and pricing contract;
- ROXY Create Center flow;
- ROXY brand and promo asset rules;
- ROXY economy implementation;
- Admin Console pricing behavior;
- Admin Runbook pricing publish/rollback procedure;
- ROXY release acceptance;
- compact `PRICING.md` reference;
- promo artwork documentation and binary mirrors;
- promo asset regression test corrected to validate real packaged binaries rather than stale impossible size/hash assumptions.

## Generation recovery hardening sync

Runtime baseline after PR #180: `fa787db146f713b8f6568f037dd2d1ca17c2c68c`.

Documentation now records the shipped recovery/accounting contract:

- generation terminal states are monotonic;
- late/duplicate callbacks cannot turn a refunded failure into success;
- Kie submission failures are classified as permanent, retryable or uncertain;
- uncertain `createTask` outcomes are not blindly resubmitted;
- unknown submissions use a configurable recovery timeout before idempotent fail/refund;
- active provider tasks use `GENERATION_HARD_TIMEOUT_SECONDS` (default 7200 seconds) as a hard safety ceiling;
- provider success without usable result media is not finalized as a charged empty result;
- release acceptance includes recovery/refund regression gates;
- documentation policy now requires relevant maintained docs/config examples to be updated in the same runtime-affecting PR before merge.

The configuration template is also synchronized with the hard-timeout setting and must contain placeholders only for secrets.
