# ROXY Mini App — Next.js + React

Status: canonical customer application architecture.
Last synchronized: 2026-11-23.

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

The design is dark-first. Violet is the main action language, pink is a brand accent. The separate unauthenticated film-mosaic landing uses chrome-lilac art while the Telegram Mini App retains its tested native chrome. Gold and Telegram blue are not part of customer chrome.

## Public marketing and application routing

The public landing and the customer application share an origin but are **different experiences**:

- `GET / ` serves the ROXY film-mosaic marketing landing with HTTP 200 **without redirecting**. Canonical user-visible entry is the bare domain `/`.
- `GET /landing/` is a backward-compatible path serving that same static marketing page and its images/CSS, not an app redirect.
- `GET /mini-app/` is the Next.js customer application. Native Telegram initData opens the app directly; valid browser sessions open the same app; unauthenticated browser visitors see a **compact application login** with the unchanged Telegram Login widget, never the full marketing landing.
- All CTA links from marketing lead to `/mini-app/` on the same origin. A narrow allowlist of referral/start parameters is transferred from the landing query/hash, avoiding dropped attribution.
- `/mini-app/route/` and other application routes keep the existing auth, dynamic models, billing, history, onboarding and delivery contracts. Do not redirect them to `/`.

The visually distinctive standalone marketing page lives in `app/web/landing/index.html`, `styles.css` and the optimized `roxy-mosaic.webp`. This is a **public marketing exception**, not a second customer application: no forms or product logic are reimplemented there. All actual customer UI remains exclusively under `frontend/mini-app/`, statically exported by Next.js and served under `/mini-app/`.

FastAPI `app/main.py` serves the landing at the root using `FileResponse` and mounts the unchanged static directories. The app's compact browser login is rendered by `TelegramAuthBoundary` → `TelegramBrowserLogin(showLanding=false)` so existing signed browser auth and Telegram web-app native paths are unchanged.

Visual direction: nearly black canvas, tight asymmetric photo/video-style mosaic, chrome-lilac `R`, editorial type and accessible CTAs. The current compressed 3×3 atlas is **design-reference artwork** and not actual customer generations; replace with published, permission-cleared sample media when available.

Tests: `tests/test_public_landing_routes.py` validates the public root, legacy alias and standalone CSS/art. `frontend/mini-app/e2e/browser-landing.spec.mjs` now checks the actual compact browser login at `/mini-app/` across 320/390/768/1280px, plus referral preservation and errors. Real release validation must verify `GET /` vs `GET /mini-app/`, the Telegram WebView native entry and latest exact image SHA.

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
