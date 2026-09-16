# Domain Context

## Curated Trend

An admin-owned reusable generation template stored as an `AdminTrend`. Ordinary users can run a Curated Trend but cannot edit its hidden generation recipe.

## Template Category

An admin-owned grouping of Curated Trends shown to users as a category of ready-made templates. Ordinary users cannot create, rename, hide, reorder, or delete Template Categories.

The mandatory `Тренды` category is the live/root category. A Curated Trend with no explicit category assignment appears there.

## Trend Assignment

The relationship that places one Curated Trend into one Template Category.

A Trend Assignment can be:

- **manual** — an admin explicitly chose the category; later hashtag edits must not override it;
- **automatic** — the category was selected from the trend's hashtags and may be recalculated when those tags or categories change.

A manual assignment to the root `Тренды` category is still an explicit assignment and remains authoritative.

## Partner Promo Program

Partner promo codes are the only financial activation mechanism for the referral program.

- Every promo code belongs to one partner (`promo_codes.partner_user_id`).
- Program economics are global and database-owned in `partner_promo_program_config`; individual promo codes do not define their own reward amount.
- Initial partner-program values are: **25 ROX** to the user on first promo activation, **30%** of paid RUB basis to the first-line partner, **+10 ROX** to that partner for each successful referred-user top-up, and **+50 ROX** to the referred user for each successful promo-attributed top-up from **1000 RUB**.
- A plain referral/deep link may still create an attribution relation for analytics/anti-fraud, but it grants **no ROX and no cash reward**. Financial rewards start only after a promo upgrades/creates the relation with `source=promo`.
- A plain link attribution is non-financial and may be replaced by the user's first valid partner promo, even when the link pointed to another partner. Once `source=promo`, partner ownership is immutable for the user; later promo codes cannot move the user to another partner.
- The welcome ROX grant is one-time and idempotent per user. Ordinary package bonuses are independent from promo attribution: 300→+30, 500→+50, 1000→+100, 2000→+150, 5000→+200 ROX by default. Package config may override bonus_credits explicitly.
- The promo-attributed top-up bonus is a separate payment-time layer: when the paid RUB basis reaches the configured threshold (initially 1000 RUB), the user receives the configured +50 ROX on top of the ordinary package bonus.
- Only first-line paid top-ups earn commission. Second-line financial rewards are disabled for this program.
- The fixed partner top-up ROX bonus is idempotent per source payment transaction and is reversed on a full payment refund. Cash referral rewards keep the existing proportional refund accounting.
- Every partner-program financial row stores audit context for its reason, promo code, partner, referred user and source payment (where a payment exists), in addition to an idempotency key/unique financial source.
- Admins manage global economics, promo ownership, limits, expiry and state through the admin control surface. Legacy promo rows without `partner_user_id` are not activatable until assigned.


## Active Feature Execution — Partner promos independent from referral links

- **Task:** restore the product's ordinary package bonuses and layer the partner promo program on top while keeping promo codes completely independent from referral/share links.
- **Audit baseline:** current merge target is `main@2f4263ecd41b69a71a3e9851a59776c471c77afe`; existing promo attribution, anti-fraud, audit/idempotency, payment completion/refund accounting, admin control surfaces and payment-provider adapters are reused rather than replaced.
- **User-visible acceptance:** ordinary package bonuses are 300→+30, 500→+50, 1000→+100, 2000→+150 and 5000→+200 ROX by default; a promo-attributed successful top-up from 1000 RUB adds +50 ROX to the user; first promo activation adds +25 ROX; partner receives 30% +10 ROX from successful first-line top-ups; invitation alone pays 0.
- **Observed production case:** a user who joined through a plain referral link had `referral_relations.source=link`, `promo_id=NULL`, no promo redemption and no promo welcome wallet transaction while a partner promo existed. That state is valid until the user separately enters the promo code.
- **Root cause:** an earlier implementation incorrectly tried to carry/activate promos through referral/share links. Product contract is stricter: `ref_*` links handle referral attribution only, while promo activation is an explicit standalone action. Separately, a new-user promo POST could be blocked by the generic onboarding mutation gate.
- **Invariant:** referral/share links never contain, select or auto-activate a promo. Promo codes are entered separately by the user. +25 ROX is granted once on first valid promo activation; partner gets 30% of successful first-line paid RUB basis +10 ROX per successful referred-user top-up; invitation alone pays nothing; ordinary package bonuses always apply independently; an active promo adds the configured user top-up bonus (+50 ROX initially) when the successful payment reaches the configured minimum (1000 RUB initially).
- **Implementation:** preserve existing referral/profile links unchanged; remove promo deep-link/share-link generation, parsing and query auto-activation; keep partner-owned promo codes visible as codes only; activate through the explicit `/api/v1/promocodes/redeem` user action; exempt that promo flow from onboarding mutation gating so a new user can enter a code before onboarding completes.
- **Admin repair:** the legacy Telegram admin promo menu must use the partner-owned/global-economics contract and must not reference removed per-code `reward_credits`.
- **Security:** promo ownership comes from server-side `PromoCode.partner_user_id`; the client never chooses partner ownership. Existing promo anti-fraud, immutable `source=promo` attribution, idempotent wallet credit and capacity checks remain authoritative.
- **No-hardcode:** partner code lists, welcome amount, partner rewards, user top-up promo bonus and its minimum RUB threshold come from DB/API. Ordinary package bonus_credits can be set in package configuration; the compatibility defaults preserve the current product matrix for existing deployments.
- **Schema/API/UI:** migration 0039 adds DB-owned `topup_user_rox` and `topup_user_min_rub`; payment payloads expose separate package/promo bonus fields; admin can edit promo user reward/threshold; Mini App shows base + ordinary gift + promo gift + total.
- **Observability/audit:** payment-time promo grants use an idempotent wallet transaction tied to payment/promo/partner/referral user; payment payload retains RUB basis, threshold, status and separated bonus amounts for reconciliation/debugging.
- **Rollout/rollback:** migration is additive with defaults 50/1000 and a reversible downgrade; disabling the global partner program stops new partner-program rewards without removing existing attribution; ordinary package bonuses remain independently configurable by package.
- **Verification plan:** clean PostgreSQL migration, full backend/domain regression, Ruff/compile/admin JS, Next typecheck/build, focused + comprehensive Chromium/WebKit E2E, two-axis code review, then all required GitHub workflows on one exact PR SHA before merge and exact-main deploy verification after merge.
- **Progress:** clean migration through 0039 succeeded; full clean backend regression 1159/1159 green; Ruff/compile/admin JS green; Next typecheck/build green; promo/wallet Chromium E2E 11/11 green. Referral/share links and promo codes are fully separated. The known review findings are closed: non-RUB promo preview now uses the same RUB accounting basis as backend settlement, and legacy pre-0039 admin idempotency retries preserve their original request hash. Exact-head GitHub CI/browser gates remain before merge.
## Active Feature Execution — Durable Nexus admin test delivery

- **Task:** replace the inline 240-second Telegram Nexus polling flow with a durable DB-backed queue so admin test results survive bot/worker restarts and temporary Telegram/provider failures.
- **Audit baseline:** replacement of stale PR #447 on current main; preserve the later live DB-admin authorization fix already in main and do not restore env-only admin access.
- **Schema:** additive migration `0040_nexus_admin_tasks` follows `0039_promo_user_topup_bonus`; task rows store requester/chat, prompt/references, provider task id, result/error, lease/backoff state and unique idempotency key.
- **Lifecycle:** `queued → generating → delivering → succeeded`; provider/hard-timeout failures use `failure_pending → failed` only after the failure notification is successfully sent.
- **Durability invariant:** `succeeded`/`failed` are the only terminal states. A worker crash, expired lease or Telegram send failure leaves the row claimable. Provider submission is protected by the persisted idempotency key.
- **Optional configuration:** `NEXUS_API_KEY` remains optional. `nexus-test-worker` always starts and publishes heartbeats; without the key it stays healthy/idle instead of degrading `/health/operational`.
- **Production wiring:** `nexus-test-worker` is a compose service, an immutable application service in `deploy-production.yml`, part of operational health and worker metrics.
- **Admin UX:** the existing `🧪 Тест` flow remains limited to live active DB admins/bootstrap admins; the final step only enqueues and immediately returns a queue id, while result/failure is delivered asynchronously to the same Telegram chat.
- **Verification:** migration chain, lease recovery, idempotent enqueue, provider submit/poll/result delivery, failure-notification retry, optional-key idle heartbeat, deploy-service contract, health contract, full CI/E2E and exact-SHA production deploy.


## Active Feature Execution — Frontend production-readiness audit

- **Task:** perform a complete customer Mini App UX/frontend production-readiness audit from a real-user perspective, fix confirmed defects in priority order P0 → P3, and prove the result with deterministic browser/CI/deploy evidence.
- **Audit baseline:** `main@79ef98425d21ace4f693c127c3463aad125314aa` on 2026-09-16. Canonical customer source is `frontend/mini-app/`; existing Next.js 16/React 19 static export, Telegram integration, backend-driven model schemas, design tokens, Playwright audit suite and exact-SHA deploy gates are reused.
- **Existing state:** broad Chromium + mobile WebKit coverage already exists for core generation, payments, history, referrals, trends, responsive surfaces, WebView navigation and client error reporting. Current production main is green, but the suite does not yet prove the full requested matrix for accessibility, console/network cleanliness across all surfaces, exact touch-target coverage, complete loading/empty/error/retry state coverage, or measurable frontend performance budgets.
- **Known overlapping work:** PR #466 changes Home/Catalog navigation but is currently failing CI and Mini App Playwright; stale PR #409 is superseded by #466. PR #469 adds an atomic language-preference endpoint and is not part of this audit unless a user-visible language defect is reproduced.
- **Primary risks:** accidental duplicate navigation roots; interactive controls without deterministic feedback; async states that fail silently; mobile/WebView safe-area and keyboard regressions; hidden 4xx/5xx requests in apparently successful screens; accessibility regressions; unnecessary re-fetch/render work; broad CSS overrides causing layout shifts.
- **No-hardcode rule:** preserve backend-owned catalog, pricing, package, model and feature contracts. Audit/fixes may add semantic/accessibility metadata, state handling, shared helpers and tests, but must not hardcode production URLs, user data, business rules, provider capabilities or mutable economics.
- **Observability:** preserve existing client error reporting and add correlation/interaction telemetry only where a critical user path cannot otherwise be diagnosed; never log secrets, Telegram initData or sensitive payloads.
- **Acceptance criteria:** no known P0/P1 user blocker remains; every confirmed broken action has a regression test; core async actions expose loading/success/error/retry feedback; duplicate submits remain protected; root/deep-link/back/refresh flows are deterministic; responsive coverage includes 320/360/375/390/414/768/1024/1280/1440/1920 where meaningful; mobile touch targets and safe areas are verified; console has no uncaught/rejected/resource failures in audited scenarios; unexpected API errors fail tests; keyboard/focus/semantic accessibility is covered for critical screens; production smoke verifies the exact merged SHA.
- **Verification matrix:** unit/domain=N/A unless logic is extracted; DB/migrations=N/A unless backend defect requires them; authorization=preserve existing server checks and exercise browser auth boundaries; provider contract=existing deterministic fakes; idempotency=double-submit/payment/generation regressions; API integration=browser routes + real ROXY E2E; frontend E2E=expanded Chromium/WebKit matrix; smoke=exact-SHA deploy health + Mini App release marker; observability=client error reporter/critical-path evidence; no-hardcode=reviewed against runtime APIs; performance=measure bundle/request/render signals before changing; rollback=small reviewable commits, revert PR or deploy prior immutable SHA.
- **Implementation plan:** (1) inventory routes/components/interactives and current browser coverage; (2) extend audit harness first so missing behaviors can fail deterministically; (3) run current branch checks and classify failures P0–P3; (4) fix smallest confirmed root causes, not visual symptoms; (5) re-run focused then comprehensive Chromium/WebKit/ROXY E2E; (6) perform two-axis standards/spec review; (7) merge only on exact-head green gates; (8) verify exact-main production deployment and post-deploy smoke.
- **Progress:** baseline and repository instructions inspected; mandatory external guidance refreshed; branch `audit/frontend-production-readiness-20260916` created from the exact production main SHA. Audit harness expansion and defect reproduction are next.
