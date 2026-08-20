# ROXY Design System

**Status:** synchronized with shipped Mini App runtime on 2026-08-20.  
**Scope:** customer Telegram Mini App under `app/web/mini_app/`. Admin surfaces may reuse tokens, but this document is authoritative for the user product only.

ROXY is a dark, media-first AI creative studio. The interface should feel compact, premium and operational: fast to scan, touch-friendly, with restrained glass surfaces and violet/pink accent energy.

## Sources Of Truth

Use these files before introducing new visual language:

- `docs/ROXY_BRAND.md` — product identity, palette, ROX rules and promo artwork contract.
- `app/web/mini_app/styles.css` — base Telegram Mini App layout, safe areas and shared primitives.
- `app/web/mini_app/roxy-brand.css` — legacy ROXY brand layer over the Telegram base.
- `app/web/mini_app/roxy-approved-surfaces.css` — final approved override layer for late-mounted modules.
- `app/web/mini_app/roxy-approved-theme.css` — legacy approved theme layer; do not expand it when `roxy-approved-surfaces.css` can cover the case.

When runtime and documentation disagree, backend/runtime behavior wins for product state and this document should be updated.

### Runtime CSS Order

The current Mini App is layered rather than a single clean stylesheet. New work must respect this order:

1. `styles.css` loads from `index.html` and defines Telegram-compatible primitives.
2. `roxy-brand.css` loads from `index.html` and maps the base UI into ROXY.
3. Feature styles load on demand from runtime modules, for example `wallet.css`, `feed.css`, `studio-shell.css`, `roxy-create-center.css`, `roxy-profile-cabinet.css`, `prompt-tools.css`, `trends.css` and `batch.css`.
4. `roxy-approved-theme.css` and then `roxy-approved-surfaces.css` are mounted by `roxy-brand.js` as the final customer-brand correction layer.

For new customer UI, treat `html.roxy-approved-brand` tokens in `roxy-approved-surfaces.css` as canonical. Values in `docs/ROXY_BRAND.md` and `roxy-brand.css` may describe the older brand layer and should not be copied when they differ from the approved layer.

## Identity

- Product name: **ROXY**
- Descriptor: **AI Creative Studio**
- Greeting: **Привет! Это ROXY ✨**
- Tagline: **Твори. Генерируй. Зарабатывай.**
- Logo mark: packaged SVG at `app/web/mini_app/roxy-logo.svg`; do not replace with text-only `RX` marks in shipped surfaces.

## Design Principles

- **Media-first:** Create starts from Photo/Video intent and generated output should dominate result/detail views.
- **Compact premium:** Prefer dense, readable panels over marketing layouts. Avoid oversized empty sections.
- **Dark glass:** Surfaces are graphite/violet-tinted, with thin borders and soft inner highlights.
- **One accent system:** Primary actions use the approved violet to pink gradient. Secondary accents use violet-soft or pink-soft, not new colors.
- **Telegram-native ergonomics:** Preserve viewport, content safe-area and bottom navigation behavior.
- **Stable motion:** Small transitions are acceptable; reduced-motion users must keep a stable surface.

## Tokens

Canonical ROXY tokens:

```css
:root,
html.roxy-approved-brand {
  --roxy-bg: #08070f;
  --roxy-bg-deep: #05040b;
  --roxy-surface: #15121d;
  --roxy-surface-2: #1b1624;
  --roxy-text: #fbf9ff;
  --roxy-muted: #aaa2b8;
  --roxy-violet: #8f63ff;
  --roxy-violet-soft: #b184ff;
  --roxy-purple: #b768ff;
  --roxy-pink: #ff69c9;
  --roxy-pink-soft: #ff94dc;
  --roxy-border: rgba(173, 112, 255, .22);
  --roxy-border-strong: rgba(227, 101, 211, .34);
  --roxy-gradient: linear-gradient(110deg, #8f63ff 0%, #b768ff 46%, #ff69c9 100%);
}
```

Compatibility tokens map ROXY into the older Telegram variable layer:

```css
--bg: var(--roxy-bg);
--text: var(--roxy-text);
--hint: var(--roxy-muted);
--link: #c6a4ff;
--button: var(--roxy-violet);
--button-text: #ffffff;
--surface: var(--roxy-surface);
--section: var(--roxy-surface-2);
--accent-text: var(--roxy-pink-soft);
--border: var(--roxy-border);
--border-strong: var(--roxy-border-strong);
```

Do not add local one-off color values when a token exists. New semantic tokens should be introduced only when at least two surfaces need the same meaning.

## Color Usage

| Role | Token | Usage |
| --- | --- | --- |
| App background | `--roxy-bg`, `--roxy-bg-deep` | Body, fixed overlays, deep shells |
| Surface | `--roxy-surface`, `--roxy-surface-2` | Panels, cards, checkout blocks |
| Primary text | `--roxy-text` | Headings, strong values, button text on dark |
| Muted text | `--roxy-muted` | Captions, helper copy, empty states |
| Primary action | `--roxy-gradient` | Create, pay, publish, submit, start |
| Secondary accent | `--roxy-violet-soft` | Section kickers, active nav text, focus emphasis |
| Tertiary accent | `--roxy-pink-soft` | Text buttons, arrows, light links |
| Border | `--roxy-border` | Standard panel outline |
| Strong border | `--roxy-border-strong` | Featured, selected or high-value panels |

Avoid gold, Telegram-blue and beige/brown visual language in customer surfaces.

## Typography

Base font stack:

```css
font-family: Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
```

Scale:

| Role | Size | Weight | Notes |
| --- | --- | --- | --- |
| View title | `clamp(26px, 7vw, 34px)` | 850-900 | Main in-app headings |
| Hero title | `clamp(30px, 8vw, 46px)` | 900 | Only for first-screen product hero |
| Section title | `18px` to `24px` | 800-850 | Cards and section heads |
| Body | `13px` to `15px` | 400-650 | Keep line-height around `1.4-1.55` |
| Caption | `10px` to `12px` | 650-850 | Kicker, labels, metadata |

Letter spacing may be positive for uppercase micro-labels. Avoid negative letter spacing outside large headings and brand wordmarks.

## Spacing And Layout

- App shell width: `min(100%, 840px)`.
- Mobile side padding: `max(12px, Telegram content safe-area inset)`.
- Desktop shell may use a sidebar, but customer navigation remains compact and task-oriented.
- Section vertical rhythm: `18px` to `24px`.
- Card internal padding: `14px` to `20px`.
- List gaps: `8px` to `12px`.
- Bottom padding must account for `--nav-height` and Telegram content safe area.

Use CSS grid for repeated cards and forms. Preserve `minmax(0, 1fr)` in narrow layouts to prevent text overflow.

## Radius

| Element | Radius |
| --- | --- |
| Small controls, chips | `10px` to `12px` |
| Inputs, balance, compact buttons | `12px` to `14px` |
| Media thumbnails, icons | `13px` to `15px` |
| Standard cards | `16px` to `20px` |
| Hero / modal sheets / bottom nav shell | `22px` to `26px` |
| Pills / badges | `999px` |

Cards should not be nested inside decorative cards. Use full-width sections and individual cards for repeated items.

## Elevation

Standard surface:

```css
border: 1px solid var(--roxy-border);
background:
  radial-gradient(circle at 100% 0%, rgba(143,99,255,.08), transparent 42%),
  linear-gradient(145deg, rgba(28,23,38,.94), rgba(14,12,21,.96));
box-shadow: inset 0 1px rgba(255,255,255,.025), 0 16px 40px rgba(0,0,0,.22);
```

Primary glow is reserved for CTAs, active create affordances and important account/economy highlights. Do not apply glow to every card in a list.

## Core Components

### App Shell

Use `.app-shell`, `.product-header`, `.app-main` and `.app-view` for customer surfaces.

- Header is sticky and blurred.
- Brand button returns to the product home.
- Balance chip is an action and must remain visible on primary surfaces.
- Main content must leave room for bottom navigation.
- Deep routes may mount `studio-shell.css` / `studio-shell.js`; keep `.studio-bottom-nav` visually aligned with the customer navigation contract.

### Brand Mark

Use `.brand-mark`, `.studio-sidebar-mark` or `.onboarding-mark`.

- Runtime mark uses `/mini-app/roxy-logo.svg`.
- Size: `42px` header, `46px` sidebar, `56px` onboarding.
- Do not render visible fallback letters after `roxy-approved-brand` is active.

### Panels And Cards

Use `.shell-panel`, `.shell-card`, `.card`, `.result-card`, `.profile-card`, `.account-overview-block` or feature-specific cards that follow the standard surface recipe.

Card anatomy:

- Section kicker or compact label.
- One clear title/value.
- Optional muted description.
- One primary action or a small set of secondary actions.

### Buttons

Primary:

```css
.primary-button {
  min-height: 44px;
  border: 1px solid rgba(255,255,255,.09);
  border-radius: 14px;
  background: var(--roxy-gradient);
  color: #fff;
  font-weight: 800;
}
```

Use for irreversible or revenue/product-forward actions: create, pay, publish, submit, start.

Secondary/quiet:

- `.quiet-button`: bordered dark surface for navigation or low-risk mode changes.
- `.ghost-button`: transparent text action for utility controls.
- `.text-button`: link-like action inside section headers.

Disabled primary buttons use muted graphite gradients and no glow.

### Inputs

Use `.input`, `.textarea`, `.json-input`, native `select`, `input` and `textarea` under `.roxy-approved-brand`.

- Background: dark translucent.
- Border: `--roxy-border`.
- Focus: violet border plus soft outer ring.
- Textareas should resize only when the workflow benefits from long prompts/support text.

### Tabs And Segmented Controls

Use `.family-tabs`, `.family-tab`, `.feed-tab`, `.studio-library-tab` for option sets.

- Active tabs use violet/pink brand fill or soft active surface.
- Keep tab height around `36px`.
- Use horizontal scroll on narrow screens rather than wrapping into multiple noisy rows.

### Navigation

Primary customer navigation contract:

- Create
- Prompts
- My ROX
- Earn
- Profile

Active state uses violet-soft text with a small gradient indicator. The central create action can carry stronger gradient treatment.

Implementation classes:

- Base nav: `.bottom-nav`, `.bottom-nav-item`.
- Studio nav: `.studio-bottom-nav`, `.studio-nav-item`.
- Customer override: `.roxy-customer-navigation-ready .studio-bottom-nav`, `.roxy-customer-nav-item`, `.roxy-central-create`.
- Profile badge: `.profile-nav-badge`.

The customer nav is the product contract. Do not expose legacy `feed`, `history`, `library` or admin-like routes as primary customer tabs unless product navigation is intentionally changed.

### Status And Feedback

- Toasts sit above bottom nav and use high-contrast dark background.
- Inline validation uses compact `role="status"` text near the affected action.
- Empty states use dashed or soft bordered panels; keep copy short and actionable.
- Success: `--success` / `#72dba2`.
- Danger: `--danger` / `#ff8298`.

### Toggles And Choice Rows

Use switch rows for binary preferences and radio-like cards for package/provider choices.

- Switches follow `.profile-switch`: `46px` by `28px`, `999px` track, visible focus on the hidden input sibling.
- Package/provider choices use `.payment-package`, `.payment-provider`, `.primary-card-package` or `.payment-method-choice`.
- Selected choices use `is-selected`, `aria-checked` where radio semantics apply, strong pink/violet border and a compact check mark.

### Media Cards

Use media cards when the first decision is output type or reusable media.

- Create entry: `.roxy-media-grid`, `.roxy-media-card`, `.roxy-media-card-icon`, `.roxy-media-card-count`.
- Generated media: `.generation-thumb`, `.result-card`, `.studio-reference-preview`, `.feed-card`.
- Trend media: `.trend-card-media`, `.trend-runner-preview`.

Media that represents an actual output, trend or reference must render the asset itself. Decorative placeholders are acceptable only for loading, empty or unavailable states.

### Data And Metric Cards

Use compact metric cards for account, partner and wallet data.

- Profile: `.roxy-cabinet-metric`, `.roxy-cabinet-action`.
- Partner: `.partner-stat`, `.partner-row`, `.partner-line-badge`, `.partner-status`.
- Wallet: `.wallet-hero`, `.payment-history`, `.payment-status-card`.

Numbers are high-emphasis; explanations are muted and short. Avoid long paragraph copy in metric cards.

## Product Surface Patterns

### Create

Create is media-first. The first choice should be Photo vs Video, followed by server-driven model/schema controls.

Required structure:

- Direction cards for media type.
- Model family picker.
- Dynamic settings form.
- Sticky or nearby quote/summary.
- Primary create action disabled until validation passes.

### Wallet And ROX

- Public denomination is `1 ROX = 1 ₽`.
- Balance values are high-emphasis white.
- Payment package cards use selected state with strong border.
- Checkout provider rows are radio-like choices, not plain links.

### Earn / Partner

Use step cards, metric cards and withdrawal panels. Rewards should be clear, but do not imply live pricing rules beyond backend/admin authority.

### Feed / Discovery / Trends

Generated media is the primary object. Cards should show actual images/videos when available. Avoid blurred or purely decorative previews when the user needs to inspect output.

### Prompt Tools / Trends / Batch

Standalone utility screens can keep their route-specific wrappers, but must still consume the approved palette through `roxy-approved-surfaces.css`.

- Prompt Tools: `.tool-tabs`, `.tool-tab`, `.tool-panel`, `.tool-result`, `.tool-submit`.
- Trends: `.trend-filter`, `.trend-card`, `#trendRunner`, `#trendResult`.
- Batch: `.batch-upload`, `.batch-quote`, `.batch-result`, `.batch-progress-bar`.

These screens may use wider content caps (`820px` to `1120px`) because they are tool surfaces, but they still need mobile-first safe-area padding and approved primary actions.

### Profile

Profile is an operational cabinet: account, notifications, support, preferences. Use compact rows, toggles and forms rather than marketing cards.

### Onboarding And Child Screens

- Onboarding uses `.onboarding-overlay`, `.onboarding-card`, `.onboarding-mark`, `.onboarding-start`.
- Deep child routes use `.roxy-child-screen-*` wrappers and hide the bottom nav while open.
- Modal/sheet-like child views should cap height with `dvh`, preserve safe-area padding and keep close/back actions visible.

## Assets

Approved promo slide artwork is product-owned and must be preserved exactly:

```text
app/web/mini_app/roxy-partner-referrals-slide-source.webp
app/web/mini_app/roxy-creator-rewards-slide-source.webp
```

Rules:

- render with `object-fit: contain`;
- do not crop, filter, blur, sharpen or transform;
- do not re-typeset or regenerate;
- replace only from a supplied master asset.

## Accessibility

- Every icon-only or ambiguous button needs an accessible label.
- All interactive controls need visible `:focus-visible` treatment.
- Form errors and async status should use `role="status"` or nearby live regions when state changes.
- Preserve text contrast against glow backgrounds.
- Respect `prefers-reduced-motion: reduce`.
- Touch targets should be at least `42px` high unless the control is purely informational.

## Implementation Rules

- New customer CSS should consume ROXY tokens and compatibility tokens, not raw Telegram variables, unless the component is intentionally Telegram-neutral.
- Prefer extending `roxy-approved-surfaces.css` for global final-brand corrections.
- Feature CSS may define local layout classes, but should not define a new palette.
- Avoid `!important` in new feature CSS. It is acceptable in final approved override layers only.
- Do not introduce decorative orb/blob backgrounds. Use restrained radial accents inside surfaces when needed.
- Before adding a new component class, check for an existing primitive in `styles.css`, `studio-shell.css`, `roxy-approved-surfaces.css`, `wallet.css` or the matching feature CSS.

## File Ownership

| Area | Primary files | Notes |
| --- | --- | --- |
| Base shell | `index.html`, `styles.css`, `app.js`, `shell.js` | Telegram primitives, initial views, bottom nav and toast |
| ROXY brand | `roxy-brand.css`, `roxy-brand.js`, `roxy-approved-surfaces.css` | Brand activation and final visual overrides |
| Customer nav | `roxy-customer-navigation.css`, `roxy-customer-navigation.js`, `roxy-icons.js` | Create / Prompts / My ROX / Earn / Profile |
| Create | `roxy-create-center.*`, `roxy-generation-flow-v3.js`, `roxy-generation-flow.css`, `roxy-photo-controls.*`, `roxy-video-controls.*` | Media-first generation workflow |
| Studio/library | `studio-shell.*`, `studio-workspace.*`, `roxy-reference-*`, `roxy-preset-editor.js` | Deep workspace, references and presets |
| Wallet/payments | `wallet.*`, `payment-surface.*`, `primary-card-checkout.js` | ROX balance, packages and checkout |
| Profile | `roxy-profile-cabinet.*`, `profile-tools.*`, `account-overview.js` | Account cabinet, settings, support, notifications |
| Discovery/social | `feed.*`, `social.*`, `roxy-discovery.*`, `roxy-author-profile.js`, `trends.*` | Community, published media and trend tools |
| Partner/economy | `partner.*`, `roxy-economy.*`, `roxy-partner-promo.*` | Earn surface, referrals and creator economy |
| Onboarding/mobile | `onboarding.*`, `roxy-app-onboarding.*`, `roxy-mobile-runtime.*`, `roxy-iphone-polish.css` | First-run, viewport, platform polish and safe areas |

When touching a feature surface, update the feature CSS for local layout and `roxy-approved-surfaces.css` only when the change must apply across several late-mounted modules.

## QA Checklist

Before shipping a visual change:

- Header, bottom nav and Telegram safe areas remain stable on mobile.
- Text does not overflow buttons, cards or balance chips.
- Primary CTA is the only dominant action in its local context.
- Dark mode is coherent without Telegram theme colors.
- Focus states are visible from keyboard navigation.
- Reduced-motion users do not receive layout-moving effects.
- Promo artwork remains uncropped and unfiltered.
- No gold, beige, brown or Telegram-blue accents reappear in customer surfaces.
