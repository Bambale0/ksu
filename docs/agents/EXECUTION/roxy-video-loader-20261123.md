# ROXY loading video — 2026-11-23

- **Baseline:** main @ `798c82248db73969c3a7cf10c5e7ad88eaaf52a2` (read from current connected GitHub / isolated checkout).
- **Existing:** `TelegramAuthBoundary` has initial auth splash; `AppEntryGate` resolves start payload; `RoxySocialApp` and `RoxyApp` show `Splash` until `booting` becomes false. `RoxySocialApp` ends boot on `api.me()` settle; models fetch is independent.
- **Partial:** current CSS `.splash` offers orbit/progress placeholders but no responsive video; app already removes the loading element on readiness.
- **Missing:** muted responsive MP4/WebM source with static fallback, reduced-motion behavior and coverage.
- **Reuse:** existing readiness state and static Next export `/mini-app/` base path. No new API, provider, auth, pricing or persistence changes.
- **Prefactor:** extract one `RoxyLoadingVideo` component shared by main boot and browser/TG authentication splash; keep non-boot deep-link redirect/status screens unchanged.
- **Security and data:** four bundled public video files contain only ROXY branding; no secrets, media API URLs, user data or external CDN.
- **Migration:** none. Static bundle increases by ~4.2 MB across four variants, but browser selects only one video source; no critical-path JS imports of video.
- **Test seams:** Playwright launch with delayed `/api/v1/me` response; assert splash video attributes and source media fallbacks; release response and assert splash disappears even before playback ended; reduced-motion/error fallback.
- **Configuration:** no business knobs. Videos are public versioned build assets, not runtime-changing tariffs or backend settings.
- **Observability:** existing `ClientErrorReporter` tracks app errors; video load failures are cosmetic and degrade to branded static screen rather than blocking app startup.
- **Acceptance:** phones 9:16, wide screens 16:9, WebM preferred/MP4 fallback, muted/playsInline/autoplay/loop, no wait for six-second end, fail-safe when media blocked, no regression on landing/deep links.
- **Release/rollback:** isolated PR from main; run TS build, Playwright, inspect CI; rollback by reverting commit. No production rollout before checks.
- **Plan:** test red → component/CSS + assets → targeted green + build → PR → production verify only after merged/deployed.