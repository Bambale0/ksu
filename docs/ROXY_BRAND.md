# ROXY product contract

ROXY is the user-facing brand for the KSU Telegram AI product.

## Product name

- Primary: **ROXY**
- Descriptor: **AI Creative Studio**
- Russian home greeting: **Привет! Это ROXY ✨**
- Tagline: **Твори. Генерируй. Зарабатывай.**

The repository/package/runtime identifiers may continue using `ksu` for compatibility. User-facing product surfaces should use ROXY.

The default Telegram onboarding title is `Добро пожаловать в ROXY`. Production environments that explicitly set `ONBOARDING_TITLE` must update that environment value as part of the release; an environment override intentionally wins over the code default.

## Palette

| Token | Value | Purpose |
| --- | --- | --- |
| `--roxy-bg` | `#09080F` | main almost-black background |
| `--roxy-bg-deep` | `#06060B` | outer/deep background |
| `--roxy-surface` | `#18171F` | controls and secondary surfaces |
| `--roxy-surface-strong` | `#23212A` | cards |
| `--roxy-text` | `#FBF8FF` | primary text |
| `--roxy-muted` | `#A8A4B2` | secondary text |
| `--roxy-violet` | `#8F6BFF` | violet glow |
| `--roxy-purple` | `#B86CFF` | primary accent |
| `--roxy-pink` | `#FF73CA` | pink glow/accent |
| `--roxy-pink-soft` | `#FF9DDC` | light pink accent |

Primary CTA gradient:

```css
linear-gradient(105deg, #8c6cff 0%, #c58dff 42%, #ff9bdc 100%)
```

## Visual rules

- dark-only branded product surface;
- graphite glass cards with thin translucent white borders;
- violet glow from the left/top and pink glow from the right;
- large white headings with restrained supporting copy;
- primary actions use the violet-to-pink luminous gradient;
- secondary actions stay dark and low-contrast;
- active navigation uses a soft violet surface;
- the central Create control receives the strongest glow;
- glow is decorative only and must not reduce text contrast;
- no animation is required for the visual identity; reduced-motion users keep a stable surface.

## ROX economy

The approved reference is the product contract, not decorative copy:

- **1 ROX = 1 ₽**;
- **50 ROX** welcome bonus;
- **30 ROX** for an invited friend;
- **5 ROX** to the original author for each paid repeat/remix of their prompt;
- **30%** of real top-ups from referral level 1;
- **5%** of real top-ups from referral level 2;
- minimum withdrawal: **3,000 ROX**.

ROX are presented as two balances:

- **bonus/internal ROX** — welcome, invite, prompt-repeat, purchased and other wallet credits. They can be spent inside ROXY and cannot be withdrawn;
- **withdrawable ROX** — only partner rewards backed by real paid top-ups. They are accounted separately from the spend wallet and may be withdrawn subject to the 3,000 ROX minimum.

The current database keeps this separation without duplicating money: `wallet.balance` is the internal spend balance, while `ReferralReward` + `PartnerWithdrawal` are the source of truth for withdrawable earnings. With the fixed 1:1 rate, one withdrawable ROX maps to one RUB of partner accounting.

Prompt repeat rewards are idempotent and are not awarded for self-repeats.

## Main menu

The public primary menu is deliberately limited to five entries:

1. ✨ Создать
2. 🔁 Промпты
3. 💎 Мои ROX
4. 👥 Заработать
5. 👤 Профиль

Advanced product capabilities remain available inside the corresponding Studio/profile surfaces and do not crowd the primary menu.

## Production environment contract

A production `.env` that still overrides the old economics must be updated during deployment:

```dotenv
START_BALANCE_ROX=50
INVITE_BONUS_ROX=30
PROMPT_REPEAT_BONUS_ROX=5
INTERNAL_CREDIT_RUB=1
REFERRAL_FIRST_PERCENT=30
REFERRAL_SECOND_PERCENT=5
PARTNER_MIN_WITHDRAWAL_RUB=3000
```

Do not deploy the new UI with old environment overrides: the server remains authoritative for prices and withdrawals.

## Telegram integration

ROXY keeps the existing Telegram integration contracts:

- content safe-area and safe-area CSS variables;
- stable viewport handling;
- Telegram BackButton behavior;
- signed `initData` authentication owned by the existing product modules;
- branded Telegram header/background/bottom-bar colors are set to `#09080F` when the client supports those methods.

## BotFather release checklist

The web repository cannot change Telegram account-level branding or the Main Mini App loading screen. For a fully consistent release, configure the bot/Main Mini App in BotFather with:

- visible bot name: **ROXY**;
- short/about text aligned with **ROXY · AI Creative Studio**;
- dark Mini App loading background close to `#09080F`;
- ROXY icon/placeholder artwork;
- matching dark header/loading treatment for both supported appearance modes.

## Files

- `app/web/mini_app/roxy-brand.css` — palette and visual overrides;
- `app/web/mini_app/roxy-brand.js` — brand copy, Telegram chrome and home presentation;
- `app/web/mini_app/roxy-economy.css` / `roxy-economy.js` — split balances, approved earning table and five-item navigation;
- `app/api/v1/referrals.py` — server-authoritative ROX economy state;
- `app/services/users.py` — welcome/invite bonuses;
- `app/services/generations.py` — prompt-repeat bonus;
- `app/core/config.py` — product economics defaults;
- `tests/test_roxy_economy.py` / `tests/test_internal_credits.py` — regression contracts.
