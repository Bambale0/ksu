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


## Active Feature Execution — Persistent promo visibility in Mini App

- **Task:** make an already activated partner promo visibly persist across Mini App reloads/navigation and surface its benefit on payments/profile without changing promo economics.
- **Baseline SHA:** `70ae3f961950ce103e8c88f8d3131526287ceab8`.
- **Current state:** activation/economics exist and are covered by backend tests; `/mini-app/promocodes/` shows immediate activation result; `payments/page.tsx` only knows promo state from manual input or `?promo=` and therefore loses visible state after reload/navigation.
- **Missing:** authenticated read endpoint for the current user's active promo attribution; automatic hydration of that state on payments/profile; regression coverage for persisted visibility.
- **Reuse:** `PromoCodeService.relation_for_user`, `PartnerPromoProgramService`, existing `PromoCode`/wallet audit rows, customer API helper.
- **Security:** derive user from authenticated session only; never accept user/partner ownership from client; return only user-facing promo metadata.
- **No-hardcode:** economics remain DB-owned by `partner_promo_program_config`.
- **Observability:** no new provider path; existing request-id HTTP middleware remains authoritative. Endpoint is read-only and deterministic.
- **Acceptance criteria:** (1) after promo activation, reload/navigation still shows active code; (2) payments page auto-hydrates it without re-entry; (3) UI explicitly shows +welcome ROX benefit and that purchased package amount itself is unchanged; (4) checkout automatically carries active promo metadata when applicable; (5) profile exposes active promo/program state; (6) existing activation/payment/refund economics stay unchanged.
- **Verification matrix:** unit/domain — existing promo economics + new view helper; DB/API integration — required; authorization — required via CurrentUserDep; migrations — N/A, no schema change; provider contract — N/A; idempotency/retry — existing activation/checkout unchanged; API — required; E2E — required for persisted UI; smoke — required through Mini App/CI; observability — existing request middleware; admin configurability — economics unchanged/DB-backed; performance — indexed PK/FK lookup only; rollback — code-only revert.
- **Plan:** 1) add failing API regression for active promo state; 2) implement read endpoint; 3) hydrate payments/profile UX from endpoint; 4) add frontend/E2E assertions; 5) code review against spec + AGENTS; 6) exact-head CI, merge, deploy, exact-SHA production verification.
- **Progress:** audit complete; implementation pending.
