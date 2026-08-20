# ROXY Release Acceptance

**Status:** synchronized with shipped runtime on 2026-08-20.

This is the release checklist for the customer Mini App plus the money-sensitive generation/admin contracts that can change customer behavior without a frontend deploy.

## Automated gate

A release candidate must pass:

- all Mini App/Admin JavaScript syntax checks;
- focused ROXY shell/navigation/create/economy/payment contracts;
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
- Video/Create routing returns to the wrong surface;
- quote and actual debit diverge;
- a late/duplicate provider callback can reverse a terminal generation state;
- an ambiguous provider submission can trigger a blind duplicate paid provider task;
- refund is not exactly-once for a failed generation;
- live admin pricing disappears after restart;
- a pricing publish can bypass permission/confirmation/MFA;
- ROX/payment state is ambiguous;
- Seedance 2.5 UI/catalog accepts a parameter outside the currently callable Kie schema without an explicit tested adapter;
- Seedance 2.5 auto-duration is exposed before actual-duration billing settlement exists;
- a generation action is shown despite being unsupported by the backend catalog;
- approved promo artwork is missing, cropped or replaced by reconstructed artwork.
