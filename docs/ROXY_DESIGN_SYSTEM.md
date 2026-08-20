# ROXY Design System — Concept One

Status: canonical customer design system for the Telegram Mini App.
Last synchronized: 2026-08-20.

## 1. Source of truth

The customer UI has one final visual authority:

- `app/web/mini_app/styles.css` — structural/base compatibility and Telegram variables;
- feature CSS files — local layout hooks required by their feature modules;
- `app/web/mini_app/roxy-design-system.css` — **canonical product tokens, surfaces, typography, controls, navigation and responsive behavior**;
- `app/web/mini_app/roxy-brand.js` — mounts functional product modules and mounts `roxy-design-system.css` last;
- `app/web/mini_app/roxy-brand.css` and `roxy-theme-compat.css` — historical URL entrypoints only. They import the canonical design system and must not contain a second visual language.

Do not add another `approved`, `feedback`, `polish`, `density`, `final`, or `override` stylesheet. Extend the canonical design system or the owning feature layout instead.

## 2. Retired visual layers

The following global override and duplicate-home layers were removed during the Concept One migration and must not be reintroduced:

- `roxy-approved-theme.css`
- `roxy-approved-surfaces.css`
- `roxy-client-feedback.css`
- `roxy-unified-controls.css`
- `roxy-iphone-polish.css`
- `roxy-fhd-density.css`
- `roxy-home-density-v3.css`
- `roxy-mature-ui.css`
- `roxy-mobile-runtime.css`
- `roxy-header-logo.css`
- `roxy-reference-home.css`
- `roxy-reference-home.js`
- `roxy-reference-order.css`

The reference-home bundle was especially problematic because it was mounted indirectly from the notification badge bridge and could hide/reorder the canonical home. The bridge now owns notifications/balance only. The release gate fails if these retired layers return or are mounted again.

## 3. Concept One palette

Canonical tokens:

| Role | Value |
| --- | --- |
| Background | `#0B0B10` |
| Deep background | `#07070B` |
| Violet / action | `#9B5CFF` |
| Pink / brand accent | `#FF5FB7` |
| Primary text | `#FFFFFF` |
| Muted text | `#A6A6B3` |
| Success | `#72DBA2` |
| Danger | `#FF8298` |

The product is dark-first. Violet is the primary functional accent; pink is a brand/accent signal. Gold and Telegram-blue do not belong to the customer visual language.

## 4. Typography and density

- Font stack: Inter → system sans-serif.
- Large headings: 850–950 weight, compact line-height, slight negative tracking.
- Micro labels/kickers: uppercase, high tracking, muted/violet.
- Main cards: 17–26 px radius depending on hierarchy.
- Controls: 13–15 px radius.
- Interactive mobile targets: minimum 44 px.
- Mobile layout must respect Telegram content safe-area variables.
- `prefers-reduced-motion` must remain supported.

## 5. Primary navigation

Customer navigation is fixed to five destinations:

1. `Главная`
2. `Каталог`
3. `Создать`
4. `История`
5. `Профиль`

`Создать` is the central emphasized action. Do not restore `Лента` as the customer-facing primary label.

## 6. Concept One screen family

The visual system is designed around the eight approved Concept One surfaces:

1. **Главный экран** — brand hero, fast create actions, recent work and discovery entrypoints.
2. **Создание изображения** — prompt, model, ratio and capability-driven settings with a single strong generate action.
3. **Результат изображения** — result media first, concise parameters, edit/download/publish/create-again actions.
4. **Создание музыки** — the same builder language applied to real audio models and their server-provided fields.
5. **Библиотека работ** — compact filters and media-first work grid.
6. **Профиль / настройки** — balance/economy, account actions, notifications/support/partner surfaces.
7. **Настройки генерации** — advanced controls appear only when the selected model exposes them.
8. **История генераций** — chronological work/task history with compact status and actions.

These are product states, not eight independent themes. They must share the same primitives and tokens.

## 7. Generation controls contract

The frontend must not maintain a second hard-coded model catalog.

- Models come from `/api/v1/generations/models`.
- Model categories are derived from backend `media_type` and catalog data.
- Controls are rendered from the selected model's server `ui_schema` / capability metadata.
- Unsupported fields must not be shown just because another model supports them.
- Selected model and compatible draft settings remain persistent through the existing generation runtime.
- Audio/music is a real generation flow, not a decorative placeholder.

The design system styles controls; it does not invent provider capabilities.

## 8. Brand and logo

Customer chrome uses the current ROXY mark from:

`/mini-app/assets/roxy-rx-logo-v5.webp?v=5`

The mark is placed inside the product's rounded/arched brand container and must use `object-fit: contain`. Do not replace it with a text `RX` fallback in normal runtime.

Telegram header, background and bottom bar colors are synchronized to `#0B0B10`.

## 9. Surfaces and controls

Use shared patterns from `roxy-design-system.css`:

- glass/dark cards with subtle violet borders;
- violet → pink primary actions;
- dark secondary/quiet actions;
- dark inputs with violet focus ring;
- compact pill filters/tabs;
- media-first result/library cards;
- floating five-item mobile navigation;
- explicit disabled, success, error, empty and skeleton states.

Avoid large decorative glow fields behind every control. Glow is hierarchy, not decoration.

## 10. Responsive behavior

Primary breakpoints:

- mobile-first base;
- `max-width: 430px` for Telegram phone density;
- `min-width: 720px` for two-column generation workspace and wider grids.

Release acceptance covers:

- 360×800
- 390×844
- 430×932
- 1366×768
- 1920×1080

The mobile runtime remains responsible for Telegram safe-area, stable viewport, keyboard/VisualViewport and BackButton behavior. Visual mobile rules live in the canonical design system.

## 11. Contribution rule

Before adding customer UI:

1. Reuse an existing semantic class/token where possible.
2. Put feature-specific layout beside the feature, but keep shared visual semantics in `roxy-design-system.css`.
3. Do not add a new global override stylesheet to fix specificity from an older layer.
4. Do not use `!important` as a routine theming mechanism.
5. Keep model/provider behavior server-driven.
6. Preserve 44 px touch targets, safe areas, focus-visible and reduced-motion behavior.
7. Run `python scripts/check_roxy_release.py` and the ROXY UI contract tests before release.

## 12. Migration note

Concept One intentionally replaces the previous cascade of late-mounted visual correction files and the duplicate reference-home dashboard. Functional modules such as generation, catalog, history, profile, payments, partner flows and Telegram runtime remain intact; only the global visual ownership model changed.
