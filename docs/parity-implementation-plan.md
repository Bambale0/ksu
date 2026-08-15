# ROXY parity implementation plan

Master checklist: #145.

Implementation is intentionally incremental and merged directly to `main` in small, reversible commits.

## Phase 1 — P0 functional parity blockers

- Durable hidden-history listing and restore after reload.
- Preset edit/update UI parity for `PUT /presets/{id}`.
- Capability-driven Feed actions for trend generations.
- Notification badge compatibility with the visible ROXY navigation.
- Regression tests for the above.

## Phase 2 — Navigation and runtime ownership

- One customer navigation/router owner.
- Deterministic child routes and BackButton/browser history parity.
- Remove menu replacement races between legacy shell/economy/customer navigation.
- Replace broad DOM mutation observers with explicit events/state updates.
- Remove generation `window.fetch` interception.

## Phase 3 — Child-screen architecture

- Native shell child screens for Trends, Prompt Tools, Batch, References/Presets, Notifications, Support, Creator Partnership and public author profiles.
- Preserve scroll/filter/form state across child navigation.
- Retire duplicate standalone UX while keeping compatible entry links.

## Phase 4 — ROXY visual system

- Mature ROXY visual language, restrained texture/grunge.
- One SVG/line icon system; emoji no longer used as primary UI iconography.
- Unified action hierarchy and mobile action menus.
- Source-level ROXY/ROX terminology; remove runtime text rewriting.

## Phase 5 — Release acceptance

- Visual regression targets: 360x800, 390x844, 430x932, 1366x768, 1920x1080.
- Telegram iOS/Android BackButton, safe area, keyboard and reconnect acceptance.
- Payment-return, generation polling, media playback/download and slow-network smoke tests.
- Close #145 only when every release-blocking checklist item is either complete or explicitly accepted as deferred.
