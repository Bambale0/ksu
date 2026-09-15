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
- Current production economics: promo activation itself grants **0 ROX**; an activated user receives **+50 ROX** only after a successful payment with authoritative paid RUB amount **>= 1000 ₽**; the first-line partner receives **30%** of the successful paid RUB amount plus **+10 ROX** for that top-up.
- A plain referral/deep link may still create an attribution relation for analytics/anti-fraud, but it grants **no ROX and no cash reward**. Financial rewards start only after a promo upgrades/creates the relation with `source=promo`.
- A plain link attribution is non-financial and may be replaced by the user's first valid partner promo, even when the link pointed to another partner. Once `source=promo`, partner ownership is immutable for the user; later promo codes cannot move the user to another partner.
- Promo activation is persisted but grants no wallet transaction. The user payment bonus is idempotent per successful eligible payment and is recorded separately from the purchased package.
- Package economics are independent from promo economics. Approved RUB packages are: 326.1 ₽ -> 300 base +30 package bonus = 330 ROX; 543.5 ₽ -> 500 +50 = 550; 1087 ₽ -> 1000 +100 = 1100; 2173.9 ₽ -> 2000 +150 = 2150; 5434.8 ₽ -> 5000 +300 = 5300.
- With an active promo, only payments meeting the >=1000 ₽ threshold receive the additional +50 ROX: therefore the 1087/2173.9/5434.8 ₽ packages total 1150/2200/5350 ROX. The 326.1/543.5 ₽ packages remain 330/550 ROX.
- Only first-line paid top-ups earn commission. Second-line financial rewards are disabled for this program.
- The fixed partner top-up ROX bonus is idempotent per source payment transaction and is reversed on a full payment refund. Cash referral rewards keep proportional refund accounting. The user's payment-bound promo bonus is also reversed with the payment.
- Every partner-program financial row stores audit context for its reason, promo code, partner, referred user and source payment, in addition to an idempotency key/unique financial source.
- Admins manage global promo payment bonus, minimum payment threshold, partner commission, partner top-up ROX, promo ownership, limits, expiry and state through the admin control surface. Legacy `welcome_rox` remains only for schema/API compatibility and production value is zero.
- Legacy pre-0039 pending promo reservations must still settle according to the promise made at checkout; new promo activations use only the payment-bound program above.


## Active Feature Execution — Paid promo + package bonus separation

- **Task:** implement the final package/promo mechanics without hardcoded runtime economics.
- **Baseline:** current `main` after merged PR #455.
- **Package contract:** package total = `base_credits + bonus_credits`; package bonus belongs to the package and applies with or without promo.
- **Promo contract:** activation stores immutable partner attribution and grants no ROX. Successful eligible payment grants `payment_bonus_rox` (default 50) only when authoritative paid RUB >= `min_payment_rub` (default 1000).
- **Partner contract:** source must be `promo`; first-line partner receives global `first_line_percent` (default 30%) of authoritative paid RUB plus `topup_partner_rox` (default 10) for every successful referred-user top-up.
- **UX:** active state says «Промокод активен — +50 ROX при пополнении от 1000 ₽». Package cards display base ROX, package gift, conditional promo gift, and resulting total.
- **Accounting:** package payment credit, user promo payment bonus, partner fixed ROX bonus and partner RUB commission remain distinct auditable/idempotent records.
- **Refunds:** payment ROX and user promo ROX reverse with the payment; partner fixed +10 reverses on full refund; partner RUB commission reverses proportionally.
- **Compatibility:** retain old admin request fields and pre-upgrade pending promo reservations; no new activation-time ROX.
- **Verification:** migration + ORM parity; unit/integration for activation, below-threshold, eligible payment, duplicate settlement, partner 30%/+10, refund; API catalog split; Mini App static/E2E; Admin Console; Batch; ROXY E2E; Release Gate; full CI; Codex review.

