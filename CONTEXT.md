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


## Active Feature Execution — Partner promo share activation

- **Task:** fix the production case where a user joins through a plain referral link but the partner promo is never activated, then restore the product's ordinary package bonuses and layer the user promo top-up reward on top without changing partner attribution rules.
- **Audit baseline:** current merge target is `main@2f4263ecd41b69a71a3e9851a59776c471c77afe`; existing promo attribution, anti-fraud, audit/idempotency, payment completion/refund accounting, admin control surfaces and payment-provider adapters are reused rather than replaced.
- **User-visible acceptance:** ordinary package bonuses are 300→+30, 500→+50, 1000→+100, 2000→+150 and 5000→+200 ROX by default; a promo-attributed successful top-up from 1000 RUB adds +50 ROX to the user; first promo activation adds +25 ROX; partner receives 30% +10 ROX from successful first-line top-ups; invitation alone pays 0.
- **Observed production case:** an affected new user existed with `referral_relations.source=link`, `promo_id=NULL`, no promo redemption and no promo welcome wallet transaction, while the partner-owned promo code was active and unused.
- **Root cause:** the partner cabinet exposes profile/plain referral links only. A plain `ref_*` link intentionally creates non-financial attribution and carries no promo code, so there is nothing to redeem. A new-user promo POST could also be blocked by the generic onboarding mutation gate.
- **Invariant:** +25 ROX once on first valid promo activation; partner 30% of successful first-line paid RUB basis +10 ROX per successful referred-user top-up; invitation alone pays nothing; ordinary package bonuses always apply independently; an active promo adds the configured user top-up bonus (+50 ROX initially) when the successful payment reaches the configured minimum (1000 RUB initially).
- **Implementation:** expose every partner-owned promo in `/api/v1/referrals/stats` with a canonical `promo_<CODE>` Mini App link; route signed promo deep links to `/mini-app/payments/?promo=<CODE>`, where the existing idempotent redeem flow activates the promo; exempt `/api/v1/promocodes` from onboarding mutation gating; keep ordinary referral links explicitly non-financial.
- **Admin repair:** the legacy Telegram admin promo menu must use the partner-owned/global-economics contract and must not reference removed per-code `reward_credits`.
- **Security:** promo ownership comes from server-side `PromoCode.partner_user_id`; the client never chooses partner ownership. Existing promo anti-fraud, immutable `source=promo` attribution, idempotent wallet credit and capacity checks remain authoritative.
- **No-hardcode:** partner code lists, welcome amount, partner rewards, user top-up promo bonus and its minimum RUB threshold come from DB/API. Ordinary package bonus_credits can be set in package configuration; the compatibility defaults preserve the current product matrix for existing deployments.
- **Schema/API/UI:** migration 0039 adds DB-owned `topup_user_rox` and `topup_user_min_rub`; payment payloads expose separate package/promo bonus fields; admin can edit promo user reward/threshold; Mini App shows base + ordinary gift + promo gift + total.
- **Observability/audit:** payment-time promo grants use an idempotent wallet transaction tied to payment/promo/partner/referral user; payment payload retains RUB basis, threshold, status and separated bonus amounts for reconciliation/debugging.
- **Rollout/rollback:** migration is additive with defaults 50/1000 and a reversible downgrade; disabling the global partner program stops new partner-program rewards without removing existing attribution; ordinary package bonuses remain independently configurable by package.
- **Verification plan:** clean PostgreSQL migration, full backend/domain regression, Ruff/compile/admin JS, Next typecheck/build, focused + comprehensive Chromium/WebKit E2E, two-axis code review, then all required GitHub workflows on one exact PR SHA before merge and exact-main deploy verification after merge.
- **Progress:** clean migration through 0039 succeeded; focused backend/payment/admin suite 73/73 green; full clean backend regression 1159/1159 green; Ruff/compile/admin JS green; Next typecheck/build green; focused promo/customer Chromium E2E 17/17 green. Comprehensive browser audit and exact-head GitHub CI/review remain before merge.
