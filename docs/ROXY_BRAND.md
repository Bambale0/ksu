# ROXY product and brand contract

**Status:** synchronized with shipped runtime on 2026-08-20.

ROXY is the user-facing brand for the KSU Telegram AI product. Repository/package/runtime identifiers may continue using `ksu` for compatibility.

## Product identity

- Primary name: **ROXY**
- Descriptor: **AI Creative Studio**
- Greeting: **Привет! Это ROXY ✨**
- Tagline: **Твори. Генерируй. Зарабатывай.**

## Palette

| Token | Value | Purpose |
| --- | --- | --- |
| `--roxy-bg` | `#09080F` | main almost-black background |
| `--roxy-bg-deep` | `#06060B` | deep background |
| `--roxy-surface` | `#18171F` | secondary surfaces |
| `--roxy-surface-strong` | `#23212A` | cards |
| `--roxy-text` | `#FBF8FF` | primary text |
| `--roxy-muted` | `#A8A4B2` | secondary text |
| `--roxy-violet` | `#8F6BFF` | violet accent/glow |
| `--roxy-purple` | `#B86CFF` | primary accent |
| `--roxy-pink` | `#FF73CA` | pink accent/glow |
| `--roxy-pink-soft` | `#FF9DDC` | light accent |

Primary CTA gradient:

```css
linear-gradient(105deg, #8c6cff 0%, #c58dff 42%, #ff9bdc 100%)
```

## Visual rules

- dark branded product surface;
- graphite/glass cards with restrained borders;
- violet/pink glow is decorative and must not reduce contrast;
- large white headings with compact supporting copy;
- primary actions use the approved luminous gradient;
- active navigation uses a soft violet surface;
- reduced-motion users keep a stable surface.

## Approved promo slide artwork

The home promo carousel contains approved user-supplied slide compositions. These assets are **artwork**, not templates for regeneration.

Runtime assets:

```text
app/web/mini_app/roxy-partner-referrals-slide-source.webp
app/web/mini_app/roxy-creator-rewards-slide-source.webp
```

Documentation mirrors:

```text
docs/assets/roxy-promo/partner-referrals-runtime.webp
docs/assets/roxy-promo/creator-rewards-runtime.webp
```

Asset rules:

- preserve the exact approved composition, typography, objects and copy;
- do not replace the slides with AI-generated/reconstructed approximations;
- do not re-typeset or restyle them as SVG recreations;
- do not crop artwork to force a card aspect ratio;
- render with `object-fit: contain`;
- do not apply blur/sharpen/filter/transform effects in the browser;
- cache-bust when replacing the approved binary;
- asset integrity/regression tests must validate real packaged files, not impossible placeholder size/hash requirements.

The first supplied master is approximately 1536×857 and the second 1536×864. When a higher-resolution master is supplied, replace the packaged runtime copy from that exact master rather than redrawing the scene.

`docs/assets/roxy-promo/README.md` records the asset provenance/handling contract.

## ROX economy

Approved public rules:

- **1 ROX = 1 ₽**;
- **50 ROX** welcome bonus;
- **30 ROX** inviter bonus;
- **5 ROX** to the original author for a paid repeat/remix; no self-reward;
- referral top-up rewards: **30%** level 1 and **5%** level 2;
- minimum partner withdrawal: **3,000 ROX**.

Internal spend ROX and withdrawable partner earnings are separate accounting domains.

## Generation pricing presentation

Generation cards may display current backend model prices, but brand/UI copy never overrides billing. Current public baseline is documented in `GENERATION_MINI_APP.md`. Live published Admin Tariffs and server quote/create logic remain authoritative.

## Main customer navigation

The product keeps the compact customer navigation contract around Create, Prompts, My ROX, Earn and Profile while advanced capabilities live inside the corresponding product surfaces.

Create is media-first and branches into separate Photo and Video flows. This is part of the ROXY product contract, not just a styling choice.

## Production environment

Production overrides must match the public ROX denomination:

```dotenv
START_BALANCE_ROX=50
INVITE_BONUS_ROX=30
PROMPT_REPEAT_BONUS_ROX=5
INTERNAL_CREDIT_RUB=1
REFERRAL_FIRST_PERCENT=30
REFERRAL_SECOND_PERCENT=5
PARTNER_MIN_WITHDRAWAL_RUB=3000
```

Generation prices may additionally be controlled by the latest published Admin Tariffs configuration. Do not assume environment defaults are the only live pricing source.

## Telegram integration

ROXY keeps signed `initData` authentication, safe-area/content-safe-area handling, stable viewport behavior, Telegram BackButton navigation, theme changes and dark Telegram chrome where supported.

## BotFather release checklist

Repository code cannot change Telegram account-level branding. For a consistent production release configure BotFather/Main Mini App with:

- visible name **ROXY**;
- short/about text aligned with **ROXY · AI Creative Studio**;
- dark loading/background treatment close to `#09080F`;
- approved ROXY icon/placeholder artwork.

## Main files

- `app/web/mini_app/roxy-brand.css` / `roxy-brand.js` — brand layer;
- `app/web/mini_app/roxy-partner-promo.css` / `roxy-partner-promo.js` — promo carousel;
- `app/web/mini_app/roxy-create-center.*` — media-first Create entry;
- `app/web/mini_app/roxy-generation-flow-v3.js` — current Photo/Video product flow;
- `app/web/mini_app/roxy-economy.*` — customer ROX surfaces;
- `app/core/config.py`, generation/referral/user services — server product/economy defaults;
- `docs/assets/roxy-promo/` — documented slide asset mirrors.
