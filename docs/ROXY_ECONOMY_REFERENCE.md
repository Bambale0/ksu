# Approved ROXY economy reference

## Customer and partner program

| Event | Customer ROX | Partner cash | Partner ROX |
| --- | ---: | ---: | ---: |
| Registration without promo | 0 | 0 ₽ | 0 |
| Ordinary invite / referral link | 0 | 0 ₽ | 0 |
| Partner promo activation | +25 ROX by current global config | 0 ₽ | 0 |
| Successful top-up by promo-attributed 1st-line user | package ROX only | 30% of paid RUB basis by current global config | +10 ROX by current global config |
| 2nd line | 0 | 0 ₽ | 0 |
| Prompt repeat/remix | 0 | 0 ₽ | 0 |

Partner-promo economics are managed in the database/admin surface through the global partner promo program configuration. The values above are the current approved defaults, not frontend constants.

## Accounting boundaries

The product deliberately keeps two accounting domains separate:

- **ROX wallet** — internal spend balance used inside ROXY. Purchased package ROX and promo ROX live here and are not cash-withdrawable.
- **Partner cash accounting** — commission backed by successful paid top-ups. This is the only withdrawal source.

Public package denomination is **1 ROX = 1 ₽** for RUB package/pricing calculations. This denomination does not make wallet ROX withdrawable cash.

Current minimum cash withdrawal is **3,000 ₽** unless changed by the approved server/admin configuration.

## Attribution rules

- A referral/profile/share link may create non-financial attribution.
- Financial partner rewards activate only after the user activates a valid partner promo code.
- The first valid promo attribution owns the financial relationship; a different partner promo cannot silently re-parent the user.
- Promo activation is independent from checkout and grants the configured welcome ROX exactly once.
- Paid packages credit exactly the package ROX amount; promo activation does not discount or inflate the package.
- Referral cash commission and fixed partner ROX are idempotent per successful source payment.
- Refunds reverse partner rewards according to the payment/refund rules.

## Deprecated pre-promo settings

The following deployment variables remain accepted only for backwards-compatible configuration parsing and must stay at zero:

```dotenv
START_BALANCE_ROX=0
INVITE_BONUS_ROX=0
PROMPT_REPEAT_BONUS_ROX=0
REFERRAL_FIRST_PERCENT=0
REFERRAL_SECOND_PERCENT=0
```

They are not authoritative business configuration. Partner promo economics come from the database/admin-controlled global program configuration.
