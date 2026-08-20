# ROXY Mini App — Next.js + React

Status: canonical customer application architecture.
Last synchronized: 2026-08-20.

## Source of truth

There is exactly one customer UI source tree:

`frontend/mini-app/`

The customer app uses:

- Next.js 16 App Router;
- React 19;
- TypeScript;
- static export (`output: "export"`);
- Telegram WebApp SDK;
- FastAPI only as API + static host in production.

`app/web/mini_app/` is **not source code**. In git it contains only a README marker. During the Docker build that directory is deleted and replaced with `frontend/mini-app/out`.

Do not put HTML, JavaScript, TypeScript, CSS, images or compatibility shims for the customer app into `app/web/mini_app/`.

## Why the old app was removed

The previous Mini App rendered a large vanilla HTML shell and then mounted multiple JavaScript/CSS layers over it. This caused:

- legacy screens flashing during startup;
- duplicate routing and navigation;
- duplicate home/dashboard implementations;
- CSS override chains;
- hidden runtime dependencies between feature modules;
- obsolete UI contracts keeping dead files alive.

That architecture was deleted, not hidden. There is no compatibility layer between the old customer DOM and the new app.

## First paint contract

The first customer-visible frame is the React ROXY splash.

Before data is ready, the application renders only `<Splash />`. Old home, Creator Economy, old shell navigation and old builder DOM do not exist in the exported HTML/runtime.

Forbidden customer UI concepts include:

- `app.js` / `shell.js` / `studio-shell.js` as customer entrypoints;
- `roxy-approved-home`;
- `roxy-theme-compat`;
- `Creator Economy / Как заработать ROX` onboarding block;
- late CSS override layers;
- a second primary navigation implementation.

## Design tokens

Canonical tokens live in `frontend/mini-app/app/globals.css`.

| Role | Value |
| --- | --- |
| Background | `#0B0B10` |
| Deep background | `#07070B` |
| Violet | `#9B5CFF` |
| Pink | `#FF5FB7` |
| Text | `#FFFFFF` |
| Muted | `#A6A6B3` |
| Success | `#72DBA2` |
| Danger | `#FF8298` |

The design is dark-first. Violet is the main action language, pink is a brand accent. Gold and Telegram blue are not part of customer chrome.

## Primary navigation

The React app owns exactly five primary destinations:

1. `Главная`
2. `Каталог`
3. `Создать`
4. `История`
5. `Профиль`

`Создать` is the central action. `Лента` must not return as a primary navigation label.

## Main product surfaces

The current React implementation includes:

- Home with ROXY hero, format launchers and recent works;
- Catalog with backend model catalog and community works;
- Create with schema-driven model controls;
- generation result preview;
- History;
- Profile with Telegram identity, private works and public publications;
- Wallet/payment sheet;
- onboarding;
- image, video and audio/media rendering.

Additional product capabilities must be implemented as React components/screens inside this tree. Do not revive the deleted vanilla modules to add a feature back.

## Generation contract

Frontend model behavior is backend-driven:

- model catalog: `/api/v1/generations/models`;
- quote: `/api/v1/generations/quote`;
- create: `/api/v1/generations`;
- detail/polling: `/api/v1/generations/{id}`;
- media upload: `/api/v1/uploads/kie`.

The React app renders fields from each selected model's `ui_schema`.

Rules:

- do not hard-code provider capabilities into React;
- do not show a setting that the selected model does not expose;
- persist selected model and compatible drafts locally;
- preserve model scenario rules and billing duration;
- audio/music is a real model family, not a placeholder.

## Profile/privacy contract

The profile has separate `Работы` and `Публикации` surfaces.

- private works may show the owner's prompt;
- public/profile publications never expose the prompt;
- publishing uses `prompt_visible: false` and `references_visible: false`;
- Telegram photo/name/username are used when available.

## Telegram contract

`frontend/mini-app/lib/telegram.ts` owns Telegram integration:

- `initData` authentication headers;
- `ready()` and `expand()`;
- `BackButton`;
- haptic feedback;
- content safe area;
- stable viewport;
- header/background/bottom-bar color `#0B0B10`.

All interactive phone controls must remain at least 44 px. `prefers-reduced-motion` must remain supported.

## Build and deployment

The production Dockerfile has two stages:

1. Node 22 builds `frontend/mini-app` with `next build`.
2. Python runtime installs the backend, removes the repository marker directory and copies the static Next export to `app/web/mini_app`.

FastAPI continues serving `/mini-app`, so the Telegram WebApp URL does not change and no permanent Node process is required on the VPS.

## Quality gates

Every customer-app change must pass:

```bash
cd frontend/mini-app
npm install --no-audit --no-fund
npm run typecheck
npm run build
```

and from repository root:

```bash
python scripts/check_roxy_release.py
pytest -q tests/test_next_mini_app_contract.py
```

CI also runs backend migrations and the full Python regression suite.

## Contribution rule

Never restore the deleted customer application as a compatibility shortcut.

If a capability from the historical app is needed, implement it in React and call the existing backend API. The backend is the reusable production layer; the deleted DOM/CSS/vanilla customer shell is not.
