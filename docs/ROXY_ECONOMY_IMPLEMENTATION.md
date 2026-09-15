# ROXY economy implementation

**Status:** synchronized with shipped runtime on 2026-08-20.

This document is the deployment/runbook companion to `ROXY_BRAND.md`.

## Approved product rules

- 1 ROX = 1 RUB for RUB package/pricing denomination.
- Registration without a promo code grants 0 ROX.
- Ordinary referral/profile/share links are non-financial.
- Partner promo activation grants the configured welcome ROX once; current default is 25 ROX.
- A promo-attributed 1st-line successful top-up pays the partner the configured cash commission; current default is 30% of the authoritative paid RUB basis.
- The same successful top-up grants the partner the configured fixed wallet bonus; current default is +10 ROX.
- 2nd-line financial rewards are 0.
- Prompt repeat/remix grants no referral bonus.
- Minimum partner cash withdrawal: 3,000 RUB by current server configuration.

Internal spend ROX live in the wallet/accounting domain. Withdrawable partner earnings are RUB-backed referral cash accounting and are not merged into the spend wallet. Partner-promo economics are database/admin controlled through the global promo program configuration.

## Public denomination migration

Migration `0023_roxy_one_ruble_denomination` converted persisted legacy 10-RUB credit values to public 1-RUB ROX while preserving real monetary value.

Current production denomination/config compatibility:

```dotenv
INTERNAL_CREDIT_RUB=1
START_BALANCE_ROX=0
INVITE_BONUS_ROX=0
PROMPT_REPEAT_BONUS_ROX=0
REFERRAL_FIRST_PERCENT=0
REFERRAL_SECOND_PERCENT=0
PARTNER_MIN_WITHDRAWAL_RUB=3000
```

The zero-valued referral variables above are deprecated compatibility knobs. They are not authoritative business configuration; current partner promo economics come from the database/admin-controlled global partner promo program config.

## Referral admission anti-fraud

Registration-time referral admission is non-financial. A plain `/start`/share/profile link may establish attribution for analytics and sharing, but it must not create ROX or cash rewards. Financial rewards begin only after a valid partner promo activation.

Current defaults:

```dotenv
REFERRAL_ANTIFRAUD_MAX_PER_HOUR=30
REFERRAL_ANTIFRAUD_MAX_PER_DAY=120
REFERRAL_ANTIFRAUD_BURST_WINDOW_SECONDS=10
REFERRAL_ANTIFRAUD_BURST_MAX=6
REFERRAL_ANTIFRAUD_BURST_AUTOBAN=true
```

Rules:

- accepted link relations are counted from durable `referral_relations`;
- registration/link admission never creates a wallet or cash bonus;
- hour/day limits reject the attempted link attachment but do not deactivate the inviter;
- with the default burst settings, the sixth registration within 10 seconds is rejected and the referrer account is restricted when autoban is enabled;
- all evaluated registration referral attempts are persisted to `referral_events` with a reason and context;
- an existing non-financial link attribution may be replaced by the first valid promo attribution according to the partner promo service rules;
- once promo-owned, attribution cannot silently move to another partner.

Promo activation and payment reward idempotency protect the financial program separately from registration anti-fraud.

## Generation billing

Flat generation:

```text
cost_rox = flat_price_rox
```

Per-second generation:

```text
cost_rox = resolved_unit_price_rox × billing_seconds
```

The server resolves model/parameter pricing and repeats that calculation on create before wallet debit.

### Approved generation baseline

```text
Nano Banana PRO            25 ROX
WAN 2.7 photo              20 ROX
GPT Image 2                20 ROX
Nano Banana 2              25 ROX
Nano Banana 2 Lite         25 ROX
Seedream 4.5               20 ROX
Seedream 5 Pro             20 ROX
Seedance 2.0 480p          40 ROX/s
Seedance 2.0 720p          50 ROX/s
Seedance 2.0 1080p         60 ROX/s
Seedance 2.5 480p          50 ROX/s
Seedance 2.5 720p          60 ROX/s
Seedance 2.5 1080p         70 ROX/s
Seedance 2.5 4K            90 ROX/s, reserved until callable provider support is exposed
Kling 2.5 Turbo Pro 5s     40 ROX
Kling 2.5 Turbo Pro 10s    80 ROX
Kling AI Avatar Standard   100 ROX/s
Kling AI Avatar Pro        150 ROX/s
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

This is the approved default baseline. The live runtime tariff can differ after an authorized admin publish.

## Admin Tariffs and runtime pricing

Generation pricing is not a frontend constant.

- the backend catalog contains default price definitions;
- environment pricing overrides may exist;
- the latest published Admin Tariffs `generation_pricing` version is applied as a runtime override;
- publish requires the privileged pricing permission and high-impact confirmation/MFA policy;
- invalid model IDs, price-mode mismatches and unsupported parameter tiers are rejected;
- quote and actual debit share the same resolver;
- the latest published tariff is restored from PostgreSQL after restart.

Operationally, a price change is complete only after catalog/quote verification and a controlled debit check. See `ADMIN_RUNBOOK.md` and `ROXY_RELEASE_ACCEPTANCE.md`.

## Package/payment units

If `ROX_PACKAGES_JSON` or `CARD_PACKAGES_JSON` are explicitly configured, amounts are expressed in public ROX. For RUB packages, omitting either `amount` or `credits` derives the missing value with the public denomination of 1 ROX per 1 RUB. When both values are present, the package uses the explicit provider price: customers receive the configured ROX amount and pay the configured RUB amount. Use that form when mirroring independently priced provider catalogs such as Lava Top.

A non-zero `GENERATION_DAILY_SPEND_LIMIT_CREDITS` is also interpreted in current public ROX units despite the legacy config field name.

## Release verification

After deploy/migration/restart:

1. `/api/v1/generations/models` reports the current public ROX denomination/prices.
2. Generation quote values match the active tariff.
3. A controlled generation debit equals its quote.
4. Kling Motion 2.6/3.0 resolve different 720p and 1080p rates correctly.
5. Restart preserves the latest published Admin Tariff.
6. `/api/v1/referrals/stats` keeps wallet ROX and withdrawable partner RUB accounting separate.
7. New registration receives 0 ROX and creates no `welcome_bonus` transaction, even if a stale legacy environment still contains `START_BALANCE_ROX=50`.
8. Ordinary referral/share links create no financial reward.
9. Valid promo activation grants the configured welcome ROX exactly once and persists promo attribution.
10. A successful promo-attributed 1st-line top-up creates only the configured 1st-line cash commission plus fixed partner ROX bonus.
11. 2nd-line financial rewards remain zero.
12. Hour/day rejected registration referrals create no relation and leave the inviter active.
13. Burst threshold blocks the triggering registration and, when configured, restricts the referrer account.
14. Concurrent registration attempts for one inviter cannot exceed the configured limit through a race.
15. Paid remix/repeat does not create a referral bonus.
16. Partner cash rewards remain separately withdrawable subject to the configured RUB threshold.
