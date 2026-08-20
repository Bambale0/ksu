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

## Repository hygiene automation

Repository operations now define a safe lifecycle for short-lived branches and superseded code:

- merged feature/fix/docs/chore branches are pruned automatically from trusted `main`;
- a branch is eligible only when its current tip exactly equals a recorded merged-PR head SHA;
- branches with open PRs, protected environment/release names or post-merge commits are preserved;
- divergent clean-port source branches may be deleted only through the reviewed `scripts/superseded_branches.txt` allowlist;
- the deletion contract is regression-tested;
- `REPOSITORY_HYGIENE.md` documents branch pruning and the rule for removing obsolete runtime code/config/docs/tests after replacements are merged;
- Alembic history is explicitly preserved even when the runtime feature that introduced an old migration is later retired.

## Seedance 2.5 callable Kie parity

Seedance 2.5 is synchronized with the callable Kie input schema checked on 2026-08-20 rather than broader marketing capability claims:

- provider model remains `bytedance/seedance-2-5`;
- callable resolution is `480p` / `720p`; `1080p` and `4K` are rejected by ROXY for this route;
- `output_format` (`mp4` / `mov`) and `nsfw_checker` are first-class catalog fields;
- legacy `fixed_lens` is removed for Seedance 2.5 and discarded from old drafts;
- reference limits are 30 images / 10 videos / 10 audio files;
- first/last-frame and multimodal-reference modes remain mutually exclusive;
- explicit duration is 4–30 seconds in ROXY; provider auto-duration remains disabled until actual-duration billing settlement exists;
- provider-specific validation happens before wallet debit;
- release acceptance now locks the same callable schema so marketing/UI drift cannot silently widen provider inputs.

## Hosted card lost-response recovery

The primary hosted-card adapter is synchronized with the current provider contract and no longer relies on an unverified metadata-correlation assumption:

- invoice creation remains `POST /api/v3/invoice`;
- authoritative single-contract lookup is `GET /api/v1/invoices/{id}`;
- arbitrary ROXY `payment_id` values are not placed in `clientUtm`, because the current public schema defines it as UTM attribution and webhooks do not guarantee returning it;
- if a verified webhook references a contract whose local `external_id` was lost, ROXY fetches the authoritative contract first;
- recovery requires authoritative id, amount, currency and buyer email;
- a local bind is allowed only when exactly one unresolved card intent matches exact amount/currency/email;
- zero or multiple candidates, missing identity data or provider mismatch fail closed with no bind and no wallet credit;
- a successful recovered bind also completes the durable `PaymentRequest` and then reuses the ordinary authoritative reconcile path;
- new regression tests cover the current lookup route, unique recovery, buyer mismatch, ambiguous candidates and missing authoritative identity fields.

## Referral registration anti-fraud

Referral attachment is now guarded at the new-user registration boundary rather than relying on client behavior:

- migration `0026_referral_antifraud` adds durable `referral_events` audit records;
- self-referral, missing inviter and inactive inviter attempts are rejected and recorded;
- inviter admission is serialized with a PostgreSQL row lock so concurrent registrations cannot bypass counters;
- configurable hourly and daily thresholds reject the new attachment without disabling the inviter;
- a short burst threshold rejects the threshold-crossing attempt and can mark the inviter inactive when autoban is enabled;
- default controls are 30/hour, 120/day and a sixth attempt within 10 seconds blocked with burst autoban enabled;
- accepted referral relation and invite bonus are created only after admission passes;
- invite bonus remains idempotent through the existing `invite-bonus:<visitor-id>` wallet key;
- existing users are not rebound to another inviter;
- `.env.example`, partner/economy docs, release acceptance and the operations runbook are synchronized with the same contract;
- the documented partner withdrawal floor is corrected to the runtime value of 3000 RUB.
