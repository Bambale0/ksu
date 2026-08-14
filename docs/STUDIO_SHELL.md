# KSU Mini App Studio shell

## Purpose

The Studio shell is the product-composition layer for the existing KSU Mini App. It does **not** replace the generation renderer, pricing, payment, history, Feed, Telegram viewport, or server-authoritative model contracts.

The implementation is intentionally additive:

- `app.js` remains the schema-driven generation renderer;
- `shell.js` remains the compatibility shell for the original `create/history/wallet/profile` views;
- `shell-integration.js` mounts `studio-shell.css` and `studio-shell.js` after the existing product modules;
- `studio-shell.js` composes those modules into the product-level Studio information architecture.

## Primary product routes

The canonical user navigation is:

1. **Главная** — orchestration screen and quick starts;
2. **Лента** — the existing Feed mounted as first-class Studio content instead of a floating-only entry point;
3. **Создать** — the existing schema-driven builder;
4. **История** — existing generation history;
5. **Профиль** — existing profile/social/support tooling.

On mobile and inside Telegram these routes are exposed through a five-item bottom navigation. On desktop (>=1024px) they are exposed through a persistent sidebar.

Secondary sidebar routes reuse existing product surfaces:

- Пополнение -> existing Wallet view;
- Тренды -> `/mini-app/trends.html`;
- Референсы -> Studio library backed by `/api/v1/references`;
- Пресеты -> Studio library backed by `/api/v1/presets`;
- Batch -> `/mini-app/batch.html`;
- Prompt Tools -> `/mini-app/prompt-tools.html`;
- Партнёрка -> existing profile/partner module;
- Поддержка -> existing profile/support module.

## Create workspace

The Studio layer turns the current builder into a result-centric workspace without changing the generation business logic.

Desktop composition:

```text
ControlsPane                     ResultPane
----------------------------     ----------------------------
Model                            empty / processing / result
Scenario                         result actions supplied by
Dynamic ui_schema fields         existing result/social layers
Quote
Generate
```

The existing `#resultCard` is moved at runtime into the result pane. DOM IDs and generation handlers remain unchanged, so `app.js` continues to own generation state and rendering.

On narrow screens the same DOM becomes a single-column controls -> result flow.

## Schema-driven model contract

`studio-shell.js` contains no model-family switch statements and no model IDs. Model capabilities still come from:

```text
/api/v1/generations/models
        -> ui_schema
        -> app.js renderer
        -> server quote
        -> generation admission
```

The Studio shell only chooses product placement and navigation.

## References and presets

The Studio library exposes the owner-scoped backend that already exists in KSU.

References support:

- list;
- register by HTTPS URL;
- image/video/audio kind;
- delete.

Presets support:

- list;
- save the current local generation draft as a server preset;
- restore a preset into the schema-driven builder;
- delete.

Video preset duration is preserved through `billing_seconds`. The API write schema must keep that field aligned with `UserPresetService`.

Applying a preset stores the draft using the same local keys already used by `app.js`, remembers the selected model, and reloads once so the normal app initialization sanitizes the draft against the current server `ui_schema`. This avoids a second client-side model validator.

## Feed compatibility

`feed.js` remains the Feed transport/rendering implementation. The Studio layer remounts its overlay into `#studioFeedView`, hides the legacy floating launcher, and opens the existing Feed through its own launcher event. Feed visibility, remix authorization, hidden-prompt policy, comments, likes, and shares remain backend-owned.

## Telegram integration

The Studio layer keeps the existing Telegram shell contracts:

- signed `Telegram.WebApp.initData` via `X-Telegram-Init-Data`;
- no use of `initDataUnsafe` for API authentication;
- existing BackButton handling remains in the compatibility shell/product modules;
- CSS continues using Telegram content-safe-area variables and `env(safe-area-inset-*)` fallbacks;
- reduced-motion users get animations/transitions disabled in the Studio layer.

## CI contract

CI validates:

- JavaScript syntax for `studio-shell.js` using `node --check`;
- primary Studio routes;
- absence of hardcoded model families in Studio composition;
- References/Presets product integration;
- signed Telegram auth usage;
- safe-area and reduced-motion CSS;
- `billing_seconds` in the preset write contract;
- the full existing regression suite.

## Manual acceptance checklist

Before merging a Studio UI change, verify at minimum:

- Desktop >= 1024px: sidebar and two-column Create workspace;
- Mobile browser: five-item bottom navigation and single-column Create;
- Telegram Android/iOS: safe areas and BackButton behavior;
- Home -> trend, scratch, Prompt Tools, References quick starts;
- Feed: list, likes/comments/share/remix via existing module;
- Create: model switching, scenario switching, quote, submit, progress, result;
- References: list/register/delete;
- Presets: save/apply/delete, including per-second video duration;
- History -> open/repeat -> builder bridge;
- Wallet and checkout remain explicit user actions;
- Profile, Partner and Support remain reachable.
