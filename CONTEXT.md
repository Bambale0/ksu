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
- Initial production values are: **25 ROX** to the user on first promo activation, **30%** of paid RUB basis to the first-line partner, and **+10 ROX** to that partner for each successful referred-user top-up.
- A plain referral/deep link may still create an attribution relation for analytics/anti-fraud, but it grants **no ROX and no cash reward**. Financial rewards start only after a promo upgrades/creates the relation with `source=promo`.
- A plain link attribution is non-financial and may be replaced by the user's first valid partner promo, even when the link pointed to another partner. Once `source=promo`, partner ownership is immutable for the user; later promo codes cannot move the user to another partner.
- The welcome ROX grant is one-time and idempotent per user. Promo activation is independent from payment success and does not increase a purchased ROX package.
- Only first-line paid top-ups earn commission. Second-line financial rewards are disabled for this program.
- The fixed partner top-up ROX bonus is idempotent per source payment transaction and is reversed on a full payment refund. Cash referral rewards keep the existing proportional refund accounting.
- Every partner-program financial row stores audit context for its reason, promo code, partner, referred user and source payment (where a payment exists), in addition to an idempotency key/unique financial source.
- Admins manage global economics, promo ownership, limits, expiry and state through the admin control surface. Legacy promo rows without `partner_user_id` are not activatable until assigned.


## Active Feature Execution — Partner promo share activation

- **Task:** fix the production case where a user joins through a plain referral link but the partner promo is never activated, so the user receives no +25 ROX and the partner financial program remains disabled.
- **Observed production case:** an affected new user existed with `referral_relations.source=link`, `promo_id=NULL`, no promo redemption and no promo welcome wallet transaction, while the partner-owned promo code was active and unused.
- **Root cause:** the partner cabinet exposes profile/plain referral links only. A plain `ref_*` link intentionally creates non-financial attribution and carries no promo code, so there is nothing to redeem. A new-user promo POST could also be blocked by the generic onboarding mutation gate.
- **Invariant:** economics stay unchanged and DB-owned: +25 ROX once on first valid promo activation; partner 30% of successful first-line paid RUB basis +10 ROX per successful referred-user top-up; invitation alone pays nothing.
- **Implementation:** expose every partner-owned promo in `/api/v1/referrals/stats` with a canonical `promo_<CODE>` Mini App link; route signed promo deep links to `/mini-app/payments/?promo=<CODE>`, where the existing idempotent redeem flow activates the promo; exempt `/api/v1/promocodes` from onboarding mutation gating; keep ordinary referral links explicitly non-financial.
- **Admin repair:** the legacy Telegram admin promo menu must use the partner-owned/global-economics contract and must not reference removed per-code `reward_credits`.
- **Security:** promo ownership comes from server-side `PromoCode.partner_user_id`; the client never chooses partner ownership. Existing promo anti-fraud, immutable `source=promo` attribution, idempotent wallet credit and capacity checks remain authoritative.
- **No-hardcode:** partner code lists and welcome amount come from DB/API; promo links are generated from configured bot username and the stored promo code.
- **Verification:** isolated PostgreSQL migration + focused backend/domain tests, Ruff, Next typecheck/build, Mini App contract/E2E, full exact-head CI and code review before merge/deploy.
- **Progress:** production diagnosis complete; fix implemented locally on `fix/promo-deeplink-activation`; focused backend tests 50/50 green, Ruff green, Next typecheck/build green; PR/CI/deploy pending.
