# KSU Mini App Studio shell

## Purpose

The Studio shell is the product-composition layer for the existing KSU Mini App. It does **not** replace the generation renderer, pricing, payment, history, Feed, Telegram viewport, or server-authoritative model contracts.

The implementation is intentionally additive:

- `app.js` remains the schema-driven generation renderer;
- `shell.js` remains the compatibility shell for the original create/history/wallet/profile views;
- `shell-integration.js` mounts the Studio shell and workspace enhancement layers after the existing product modules;
- `studio-shell.js` provides the Studio composition and compatibility nav markup;
- `roxy-customer-navigation.js` is the **single customer navigation/router state owner**;
- `studio-workspace.js` closes reusable-reference and post-generation product loops without duplicating model validation.

## Customer navigation ownership

The canonical customer navigation is:

1. **Главная**;
2. **Каталог** — opens the catalog/discovery product surface backed by the Feed route;
3. **Создать**;
4. **История**;
5. **Профиль**.

On mobile and inside Telegram these routes are exposed through a five-item bottom navigation. On desktop they use the matching primary sidebar entries.

`studio-shell.js` still creates compatibility button markup with `data-studio-route` because older shell integrations depend on those DOM hosts. It no longer acts as a competing customer router once ROXY navigation is mounted. `roxy-customer-navigation.js` **adopts** the existing buttons in place, labels/maps them to the ROXY route set and intercepts their clicks in capture phase before legacy Studio click handlers can mutate route state.

Important invariants:

- customer navigation does not rebuild/replace the main menus with `replaceChildren`;
- `roxy-economy.js` never owns or rewrites customer navigation;
- `roxy-customer-navigation.js` owns browser-history state, active-route state, deep-link startup and Back behavior;
- customer navigation synchronizes from explicit route/product events; it does not watch the whole `body` with a mutation observer;
- legacy `feed` maps to the customer `catalog` surface rather than becoming a second visible primary route.

Secondary routes reuse existing product surfaces: Wallet/top-up, Trends, References, Presets, Batch, Prompt Tools, Partner and Support.

## Create workspace

The Studio layer turns the current builder into a result-centric workspace without changing generation business logic.

Desktop composition:

```text
ControlsPane                     ResultPane
----------------------------     ----------------------------
Model                            empty / processing / result
Scenario                         repeat / share / download
Dynamic ui_schema fields         publish profile / feed
Saved references                 save result as reference
Quote
Generate
```

The existing `#resultCard` is moved at runtime into the result pane. DOM IDs and generation handlers remain unchanged, so `app.js` continues to own generation state and rendering.

On narrow screens the same DOM becomes a single-column controls → result flow.

## Schema-driven model contract

The Studio modules contain no model-family switch statements and no model IDs. Model capabilities still come from:

```text
/api/v1/generations/models
        -> ui_schema
        -> app.js renderer
        -> server quote
        -> generation admission
```

When Studio needs to reopen a persisted model, it resolves `model_id -> family` from the current server catalog before selecting the compatibility shell card. The server catalog remains authoritative.

## References and presets

References support:

- list;
- register by HTTPS URL;
- image/video/audio kind;
- delete;
- choose a saved reference directly from every dynamic media upload field.

The Create reference picker does not hardcode model fields. It progressively enhances the `ui_schema`-rendered `.upload-row`, reads the field's native `accept` contract, filters reusable references by media kind, and feeds the selected URL through the existing upload URL path. Normal `app.js` limits and validation still apply.

Presets support the full persisted lifecycle:

- list;
- create from the current generation draft;
- edit an existing preset through `PUT /api/v1/reference-presets/presets/{preset_id}`;
- restore/apply into the schema-driven builder;
- delete.

The edit surface can update name, prompt, billing seconds, params JSON and references JSON while keeping the preset's model identity explicit. After save it reloads the server list; preset truth is not confined to browser memory.

Video preset duration is preserved through `billing_seconds`. Applying a preset stores the draft using the same local keys used by `app.js`, remembers the selected model and lets normal initialization sanitize the draft against current server `ui_schema`, avoiding a second client-side model validator.

## Result product loop

The core renderer provides repeat/change, native share and open/download actions. Studio adds continuation actions after a successful generation:

- **В профиль** -> `POST /api/v1/feed/{generation_id}/publish` with `publication_scope=profile`;
- **В ленту** -> the same endpoint with `publication_scope=feed`;
- **В референсы** -> registers the first generated media URL through `/api/v1/references`.

Studio never decides derivative/trend publication policy in the browser. Feed service authorization and downgrade rules remain authoritative.

## Feed compatibility

`feed.js` remains the Feed transport/rendering implementation. Prompt actions are backend-driven: if a feed/trend item returns `prompt_actions_allowed=false`, the UI does **not** render `Повторить` for that card. The browser does not infer permission from card type alone.

## Telegram integration

The Studio layer keeps existing Telegram shell contracts:

- signed `Telegram.WebApp.initData` via `X-Telegram-Init-Data`;
- no `initDataUnsafe` for API authentication;
- existing BackButton handling in compatibility/product modules;
- Telegram content-safe-area variables and `env(safe-area-inset-*)` fallbacks;
- reduced-motion support.

## CI contract

CI validates:

- JavaScript syntax for Studio/product scripts;
- ROXY customer navigation is the single router state owner and performs no menu `replaceChildren` rewrite;
- customer navigation has no body MutationObserver hot path;
- Music has no subtree MutationObserver patch loop;
- persisted hidden History and restore contracts;
- preset create/edit/apply/delete server/UI contract;
- feed `prompt_actions_allowed` guard;
- primary Studio routes;
- schema-driven model behavior;
- References/Presets integration;
- result publication/reference actions;
- signed Telegram auth usage;
- safe-area/reduced-motion CSS;
- the full regression suite.

## Manual acceptance checklist

Before merging a Studio/navigation UI change, verify at minimum:

- Desktop >=1024px: one visible primary sidebar navigation owner;
- Mobile/Telegram: one five-item bottom navigation, no transient duplicate/rewrite flicker;
- Home → Catalog → Create → History → Profile and browser/Telegram Back;
- deep-link startup to supported child routes;
- Create model switching, quote, submit, progress and result;
- References list/register/delete/use;
- Presets create/edit/apply/delete, including per-second billing duration;
- History hide → reload → `Скрытые` → `Вернуть` → reload;
- trend/feed card with `prompt_actions_allowed=false` has no `Повторить`;
- Music model/result/history behavior remains correct without subtree mutation observers;
- Wallet/payment/Profile/Partner/Support remain reachable.
