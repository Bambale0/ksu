# ROXY visual brand

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

## Product semantics

The visual reference contains a `1 ROX = 1 ₽` statement. **Do not copy it into the product.** Billing, exchange rate and package economics remain server-authoritative. The ROXY brand layer must never change quote, payment, wallet or generation calculations.

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
- `app/web/mini_app/index.html` — first-paint ROXY identity;
- `trends.html`, `prompt-tools.html`, `batch.html` — standalone ROXY surfaces;
- `app/core/config.py` and `app/bot/handlers/start.py` — default Telegram onboarding brand;
- `tests/test_roxy_brand_contract.py` — regression contract.
