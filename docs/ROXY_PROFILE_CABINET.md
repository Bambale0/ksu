# ROXY Profile / Cabinet

The primary bottom navigation stays intentionally small:

- Главная
- Каталог
- Создать
- История
- Профиль

`Профиль` is the user-facing cabinet. ROX, payments, referrals and settings are not separate primary navigation destinations.

## Cabinet composition

The Profile cabinet summarizes server-authoritative data from:

- `/api/v1/me/overview`
- `/api/v1/referrals/stats`

It exposes quick actions for:

- `Мои ROX` — opens the existing secondary `wallet` route;
- `История` — remains a separate primary route;
- `Реферальная программа` — scrolls to the existing automatic 30% / 5% partner cabinet;
- `Настройки` — scrolls to the existing settings/notifications/support tools.

The old technical `account-overview-card` remains available in code for diagnostics/backward compatibility, but is hidden from the commercial customer surface by the ROXY cabinet layer. Telegram/internal account IDs and accounting-credit diagnostics should not dominate the customer Profile UX.

## Two different partnership concepts

### Automatic referral economy

This is the existing ROXY financial contract:

- first line: 30% of real purchased ROX;
- second line: 5%;
- withdrawable balance separated from bonus/spend-only ROX;
- normal withdrawal rules and audit trail.

The Profile labels this section **Автоматическая реферальная программа** so it cannot be confused with creator collaboration.

### Creator / Influencer partnership

This is a separate manually agreed program from customer feedback:

- individual terms based on channel, audience, engagement and cooperation format;
- possible monthly ROX allowance after approval;
- not a rewrite of 30% / 5% referral accounting.

Until the dedicated creator-partnership lifecycle in #45 is implemented, the Cabinet CTA uses the existing support form as an honest contact path and pre-fills a creator-partnership topic. It does not create fake approval/status/grant records.

## Navigation boundary

`wallet` remains an allowed secondary deep route because existing payment buttons need a direct balance/top-up destination, but it is not a sixth primary navigation tab. The active primary item remains `Профиль` while the wallet sub-surface is open.
