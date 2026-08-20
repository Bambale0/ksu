# ROXY Release Acceptance

**Status:** synchronized with shipped runtime on 2026-08-20.

This is the release checklist for the customer Mini App plus the money-sensitive generation/admin/operations contracts that can change customer behavior or recovery safety without a frontend deploy.

## Automated gate

A release candidate must pass:

- all Mini App/Admin JavaScript syntax checks;
- focused ROXY shell/navigation/create/economy/payment contracts;
- card payment recovery tests covering current provider lookup route, unique recovery and ambiguity refusal;
- referral anti-fraud tests covering hour/day limits, burst restriction and concurrent admission serialization;
- PostgreSQL backup contract tests covering shell syntax, private archive creation, custom-format validation, checksum/retention, compose isolation and production deploy integration;
- model catalog and pricing tests;
- provider-contract tests for current callable model schemas, including Seedance 2.5;
- generation reliability tests covering durable outbox recovery, terminal-state monotonicity, uncertain provider submission handling, hard lifetime, stale callback rejection and refund exactly-once behavior;
- admin security/console tests;
- Alembic migration on real PostgreSQL;
- full Python regression suite;
- packaged promo slide asset checks.

Existing UI gate expectations remain: canonical routes, no unsafe global fetch monkeypatch, no whole-document text rewriting, safe-area/VisualViewport/BackButton support, 44px touch targets, 16px mobile form inputs, horizontal-overflow protection, focus-visible and reduced-motion support.

## Required viewport matrix

- 360×800
- 390×844
- 430×932
- 1366×768
- 1920×1080

Verify Home, Create, Photo flow, Video flow, Result, History, Feed, Wallet, Profile and one nested child surface. No horizontal scroll, clipped primary actions or bottom-nav overlap is acceptable.

## Create / generation acceptance

Run these flows against the release environment:

1. `Создать → Фото` stays inside the Photo product flow.
2. `Создать → Видео` stays inside the Video product flow and **does not bounce to Home**.
3. Builder Back returns to the selected media product screen.
4. WAN 2.7 photo is available and can quote/generate/edit through the image model contract.
5. Image model quote → create debits exactly the quoted flat ROX cost.
6. Video quote → create debits exactly `resolved ROX/s × billing seconds`.
7. Upload/reference modes reject missing/incompatible required media before provider submission.
8. Result polling/history/reuse continue to work and a reuse receives a fresh quote.
9. Duplicate/late provider callbacks do not change an already-terminal generation state.
10. A failed/refunded generation cannot later become a successful charged result after a late callback.
11. A provider timeout/ambiguous `createTask` response leaves the generation recoverable without immediately creating a second provider task.
12. An unresolved uncertain submission eventually fails/refunds exactly once after the configured unknown-submission timeout.
13. A provider task that exceeds `GENERATION_HARD_TIMEOUT_SECONDS` eventually reaches a terminal failed/refunded state rather than being kept alive indefinitely by polling.
14. A provider success without usable result media is not exposed as a completed charged empty result.
15. Seedance 2.5 catalog exposes `output_format` and `nsfw_checker`, does not expose legacy `fixed_lens`, and reports a 4–30 second explicit billing range.
16. Seedance 2.5 accepts only the currently callable Kie resolution enum (`480p`, `720p`); `1080p` and `4K` are rejected server-side even if broader marketing material mentions higher model capabilities.
17. Seedance 2.5 frame mode cannot be combined with multimodal references, and last-frame input requires first-frame input.
18. Seedance 2.5 enforces product/provider reference counts: at most 30 images, 10 videos and 10 audio references; UI video upload copy must reflect ROXY's current 100 MB shared upload ceiling.
19. Seedance 2.5 `duration=-1`/auto is not exposed until billing can settle against an authoritative actual duration after completion.

## Hosted card checkout acceptance

Run card recovery against the staging provider/mock contract:

1. Invoice creation uses the current create route and stores local `Payment`/`PaymentRequest` before the remote side effect.
2. Authoritative contract lookup uses `GET /api/v1/invoices/{id}`.
3. A normal create stores the provider contract id and payment URL without changing the public neutral `card` surface.
4. A lost create response leaves the local intent `creation_unknown`; reconciliation does not blindly issue a second invoice.
5. A verified webhook for an unknown provider contract performs authoritative lookup before any local bind or wallet mutation.
6. Recovery binds only when contract id + exact amount + exact currency + normalized buyer email identify exactly one unresolved local `card` intent.
7. Zero candidates, two or more candidates, missing provider identity fields, amount/currency/email mismatch or provider lookup failure perform no bind and no ROX credit.
8. A recovered `PaymentRequest` transitions from `unknown`/`creating` to `completed` only after the row-locked bind succeeds.
9. The webhook body alone never credits ROX; ordinary authoritative reconcile runs after recovery.
10. Duplicate success remains wallet-credit idempotent.
11. The provider adapter does not depend on arbitrary custom `clientUtm` keys for merchant correlation.
12. Opening the hosted payment URL still requires a second direct user action in Telegram.

## Referral / partner acceptance

Run registration-time referral admission against real PostgreSQL:

1. A new user with a valid inviter creates exactly one `ReferralRelation` and credits the configured invitation bonus once.
2. Existing users cannot change inviter by presenting a different referral payload later.
3. Self-referral, missing inviter and already-restricted inviter create no relation and no invitation bonus.
4. With hourly limit `1`, the second admitted attempt is rejected with `hourly_limit`, creates no bonus and leaves the inviter active.
5. With daily limit `1`, the second admitted attempt is rejected with `daily_limit`, creates no bonus and leaves the inviter active.
6. With burst max `2` and autoban enabled, the second attempt inside the burst window is rejected and the inviter becomes `is_active=false`.
7. With burst autoban disabled, the triggering attempt is rejected with `burst_limit` but the inviter remains active.
8. Two concurrent registrations for the same inviter cannot both pass a configured limit of one; row-lock serialization leaves one accepted relation and one rejected audit event.
9. Every evaluated referral attempt that reaches the admission service is durably represented in `referral_events` with a reason/context.
10. Alembic metadata imports `referral_models`, and migration `0026_referral_antifraud` upgrades successfully on PostgreSQL.
11. Partner cabinet reports the configured minimum withdrawal consistently; current default is 3,000 RUB/ROX.
12. Withdrawable 30%/5% referral rewards remain separate from spend-wallet invitation bonuses.

## PostgreSQL backup / restore acceptance

Run the operations contract against the compose/deploy configuration:

1. `scripts/backup_postgres.sh` passes `sh -n` and runs with `umask 077`.
2. Periodic dumps use PostgreSQL custom format and are not published as `latest.dump` unless non-empty and parseable through `pg_restore --list`.
3. A SHA-256 sidecar is written for every published periodic archive and retention removes the matching sidecar with an expired dump.
4. `backup-worker` uses `postgres:17-alpine`, a private `db_backups` volume and a read-only script mount; it is not coupled into the customer `app` startup dependency chain.
5. The production deploy explicitly includes `backup-worker` in runtime services but not in the application build list.
6. Before Alembic, the production deploy creates a pre-migration `-Fc` archive, verifies non-empty bytes, parses it through `pg_restore --list` and writes a SHA-256 sidecar.
7. Deployment fails if `backup-worker` cannot reach a running state after runtime recreation.
8. After release, `/backups/latest.dump` and `/backups/latest.dump.sha256` validate successfully and the archive catalog is readable.
9. A restore drill into an isolated/disposable database succeeds and application-level integrity checks pass; production is never overwritten for a drill.
10. Local `db_backups` retention is not reported as off-host disaster recovery. Operations must verify an encrypted off-host copy/snapshot separately.
11. Database dumps are never uploaded through Telegram/chat or exposed from the public web root.
12. Media bucket durability is tested separately because a PostgreSQL archive contains media metadata/object keys, not object bytes.

## Public pricing baseline acceptance

Verify representative catalog/quote responses against the approved baseline:

```text
Nano Banana PRO            25 ROX
WAN 2.7 photo              20 ROX
GPT Image 2                20 ROX
Nano Banana 2              25 ROX
Nano Banana 2 Lite         25 ROX
Seedream 4.5               20 ROX
Seedream 5 Pro             20 ROX
Seedance 2.0               40 ROX/s
Seedance 2.5               60 ROX/s
Kling 3.0                  30 ROX/s
Veo 3.1                    35 ROX/s
Grok                        15 ROX/s
Grok Imagine 1.5           30 ROX/s
Gemini Omni                from 30 ROX/s
Kling Motion 2.6 720p      20 ROX/s
Kling Motion 2.6 1080p     30 ROX/s
Kling Motion 3.0 720p      60 ROX/s
Kling Motion 3.0 1080p     80 ROX/s
```

If an intentionally published Admin Tariff differs, verify against that published tariff instead and record the version in the release evidence.

## Admin pricing acceptance

In staging/pre-production:

1. operator without `pricing.manage` cannot publish generation pricing;
2. invalid/unknown model IDs are rejected;
3. price-mode mismatch is rejected;
4. unsupported tier parameters are rejected;
5. publish requires explicit confirmation and fresh MFA step-up;
6. after publish, a new quote reflects the new price immediately;
7. controlled generation debit equals that quote;
8. restart/reload restores the latest published pricing from PostgreSQL;
9. publish/rollback is visible in the admin audit trail.

## Promo slide acceptance

The two approved user-supplied slides must be present as packaged WebP files and mirrored under `docs/assets/roxy-promo/`.

Visual checks:

- exact supplied composition/copy is preserved;
- no AI-redrawn/reconstructed slide is substituted;
- `object-fit: contain` keeps the full frame visible;
- browser CSS applies no crop, filter or transform processing;
- broken artwork produces an explicit fallback/error state rather than silently hiding the promo.

## Physical Telegram acceptance

Run one real iOS and one real Android pass:

- cold start from bot launcher;
- nested deep route;
- Telegram BackButton child → parent → Home;
- keyboard in prompt/comment/support/payment fields;
- background/reactivate;
- disconnect/reconnect during a server request;
- Photo and Video generation entry flows.

## Other critical product flows

Also verify music, Trends, Prompt Tools, Batch, feed/profile publish/remix, History hide/restore, presets, notifications, support, author subscribe/unsubscribe, promo/insufficient-ROX recovery, payment redirect/return/terminal balance refresh and referral withdrawal create/cancel.

## Failure policy

Do not promote if:

- any automated release/CI gate fails;
- the pre-migration PostgreSQL archive is empty, unreadable by `pg_restore --list` or missing its checksum;
- `backup-worker` is absent from the production runtime or cannot stay running;
- the repository/docs imply that local Docker-volume retention is off-host disaster recovery;
- Video/Create routing returns to the wrong surface;
- quote and actual debit diverge;
- a late/duplicate provider callback can reverse a terminal generation state;
- an ambiguous provider submission can trigger a blind duplicate paid provider task;
- refund is not exactly-once for a failed generation;
- live admin pricing disappears after restart;
- a pricing publish can bypass permission/confirmation/MFA;
- card create uncertainty can trigger a blind second remote invoice;
- an unknown card webhook contract can bind to an ambiguous/mismatched local intent or credit ROX without authoritative provider verification;
- concurrent referral registrations can bypass the configured admission limit or create more than one invite bonus per referred user;
- hour/day referral limits can deactivate a normal inviter account;
- burst autoban can attach/bonus the triggering blocked referral;
- ROX/payment state is ambiguous;
- Seedance 2.5 UI/catalog accepts a parameter outside the currently callable Kie schema without an explicit tested adapter;
- Seedance 2.5 auto-duration is exposed before actual-duration billing settlement exists;
- a generation action is shown despite being unsupported by the backend catalog;
- approved promo artwork is missing, cropped or replaced by reconstructed artwork.
