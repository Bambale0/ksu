# Documentation sync — 2026-08-20

This synchronization aligns the maintained documentation set with the current ROXY runtime after the WAN 2.7 photo / generation pricing / live admin tariff work and the reliability/operations hardening merged throughout the 2026-08-20 release chain.

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

Documentation records the shipped recovery/accounting contract:

- generation terminal states are monotonic;
- late/duplicate callbacks cannot turn a refunded failure into success;
- Kie submission failures are classified as permanent, retryable or uncertain;
- uncertain `createTask` outcomes are not blindly resubmitted;
- unknown submissions use a configurable recovery timeout before idempotent fail/refund;
- active provider tasks use `GENERATION_HARD_TIMEOUT_SECONDS` (default 7200 seconds) as a hard safety ceiling;
- provider success without usable result media is not finalized as a charged empty result;
- release acceptance includes recovery/refund regression gates;
- documentation policy requires relevant maintained docs/config examples to be updated in the same runtime-affecting PR before merge.

The configuration template is synchronized with the hard-timeout setting and must contain placeholders only for secrets.

## Repository hygiene automation

Repository operations define a safe lifecycle for short-lived branches and superseded code:

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
- release acceptance locks the same callable schema so marketing/UI drift cannot silently widen provider inputs.

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

Referral attachment is guarded at the new-user registration boundary rather than relying on client behavior:

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

## Verified PostgreSQL backup operations

The old operations backup staging branch was clean-ported onto current `main` and hardened before release:

- a dedicated `backup-worker` uses `postgres:17-alpine` and a private `db_backups` volume;
- default periodic cadence is 3 hours, newest 16 archives retained, with backup-on-start enabled;
- periodic archives use `pg_dump --format=custom --no-owner --no-privileges`;
- an archive is not published as current until it is non-empty and parseable by `pg_restore --list`;
- published archives receive SHA-256 sidecars and `latest.dump` / `latest.dump.sha256` symlinks;
- archive creation uses `umask 077`, and unpublished crash leftovers are removed on worker restart;
- the old shared-volume lock-directory mechanism was intentionally not ported because an abrupt process kill could leave a stale lock that permanently suppresses future backups;
- the customer app startup is not coupled to completion of a potentially long backup;
- production deploy now separates application build services from runtime services and explicitly starts/verifies `backup-worker`;
- the existing pre-migration deployment dump is additionally checked with `pg_restore --list` and receives a SHA-256 sidecar before Alembic may proceed;
- local host/volume retention is explicitly documented as **not** equivalent to off-host disaster recovery;
- `DATABASE_BACKUPS.md` defines verification, restore-drill, incident and encrypted off-host durability requirements;
- database dumps are never routed through Telegram/chat by this implementation;
- release acceptance and operations/deploy docs are synchronized with the same backup contract.

## Current Kling 2.5 Turbo Pro and AI Avatar parity

The current Kie callable contracts are implemented directly rather than copied from the historical Tanya payloads:

- `kling/v2-5-turbo-text-to-video-pro` is exposed as `kling-2.5-turbo-pro-t2v`;
- `kling/v2-5-turbo-image-to-video-pro` is exposed as `kling-2.5-turbo-pro-i2v`;
- `kling/ai-avatar-standard` and `kling/ai-avatar-pro` are separate current avatar products;
- Kling 2.5 Turbo Pro accepts only 5/10-second clips; T2V exposes the current 16:9 / 9:16 / 1:1 aspect-ratio set;
- I2V requires a first-frame HTTPS URL and supports the current optional `tail_image_url`; both image controls advertise the current 10 MB Kie callable limit;
- CFG, negative prompt and `nsfw_checker` are part of the current Kling 2.5 callable contract;
- Avatar accepts image + audio + prompt only; current UI limits are 10 MB image, 100 MB audio and 300 seconds maximum audio duration;
- Avatar prompt guidance may be empty, matching Kie's own long-form guidance while still emitting the provider `prompt` field;
- Avatar has no provider `duration` input: ROXY bills against top-level `billing_seconds` and strips that accounting metadata before provider submission;
- default ROXY tariffs are 30 ROX/s for Kling 2.5 T2V/I2V, 20 ROX/s for Avatar Standard and 30 ROX/s for Avatar Pro; published Admin Tariffs remain authoritative;
- model-specific public allowlists reject unknown/legacy fields before wallet debit and provider normalization repeats the same contract at submission;
- `KLING_25_AVATAR_CONTRACT.md`, compact pricing, dynamic UI and regression tests are synchronized with the same current-provider contract.

## Grouped model-family picker

The Mini App model-selection menu now removes repeated top-level cards for versions that belong to the same public family:

- repeated `Nano Banana`, `Seedream`, `Seedance`, `WAN`, `GPT Image` and other backend families are collapsed generically by the public family label rather than by a second hardcoded catalog;
- each grouped family card contains an inline version selector, using compact chips such as `Base`, `Pro`, `2`, `2 Lite`, `3.0`, `4.5`, etc.;
- price, available mode badges and the card subtitle update from the currently selected concrete product;
- the version choice is remembered separately per media type and model family;
- selecting/opening a version delegates to the original generation product card, so schema rendering, validation, quote, wallet debit and provider submission remain unchanged and server-authoritative;
- single-product families keep their existing card without an unnecessary selector;
- version controls keep 44 px mobile touch targets, focus-visible state and reduced-motion support; families above five versions use a horizontal chip row to avoid widening the Mini App;
- `ROXY_CREATE_CENTER.md` and focused regression coverage are synchronized with the shipped behavior.

## Full app model identity and admin-free audit

PR #191 hardens the customer model/accounting contract across the whole ROXY app:

- every new generation snapshots the exact upstream provider model into `_provider_model`; the worker submits the frozen snapshot instead of re-reading a mutable customer label;
- customer presentation/grouping is keyed separately from provider routing, and Kling Video, Kling Motion and Kling AI Avatar are explicitly distinct customer families;
- generation history exposes the stored provider identity for audit while internal routing/accounting fields remain stripped from provider input;
- active `AdminAccount` users have `0.00 ROX` customer-wallet cost for normal generation, Suno/music, Prompt Tools, Batch + failed-item retry, Trends and Feed remix;
- retail price metadata is preserved and provider/operator billing still occurs; rate limits, concurrency, circuit-breaker, schema validation and durable recovery remain enabled for admins;
- zero-cost admin work creates no fake debit/refund pair and zero-cost remix cannot mint the paid prompt-repeat author bonus;
- Mini App zero-price model badges render as `Бесплатно` and wallet-facing legacy `кр.` terminology is normalized to ROX;
- Telegram auth remains local to API clients that need it; no global `window.fetch` replacement is introduced;
- the focused contract and release checklist live in `MODEL_IDENTITY_AND_ADMIN_FREE.md`, with regression tests locking exact current Kling mappings, provider snapshot precedence, internal-field stripping, presentation completeness and admin-free decisions.

## Tanya-derived trending model catalog

The customer model picker is narrowed to the current `banano_kling:tanyapi` product set instead of exposing every historical provider version:

- Photo keeps Nano Banana 2 Lite, Seedream 5 Pro, Nano Banana Pro/2, Seedream 4.5 Edit, GPT Image 2, Wan 2.7 Pro and Grok Imagine image edit;
- Video keeps Kling 3.0, Kling 2.5 Turbo Pro, Grok Imagine / 1.5, Seedance 2.0 plus KSU's already provider-verified Seedance 2.5, Gemini Omni Video, Veo 3.1, Kling Motion 2.6/3.0 and Kling AI Avatar Standard/Pro;
- obsolete picker choices such as base Nano Banana/Edit, Seedream 3/4, Seedream 5 Lite, GPT Image 1.5, Seedance 1.5 and Seedance 2.0 Fast/Mini are no longer offered for new customer work;
- old specs remain internal so historical rows and legacy provider snapshots can still be read/reconciled; inactive IDs are rejected at the new-work preparation boundary before wallet debit/provider submission;
- Grok video upscale/extend remain current result follow-up operations but are not top-level model cards;
- `TRENDING_MODEL_CATALOG.md` is the maintained allowlist/migration contract and `tests/test_trending_model_catalog.py` locks the exact public set.
