# ROXY remediation plan — 2026-08-25

This file is the live follow-up plan for the current `ksu` hardening pass. It is intentionally scoped to production-impacting gaps found in the active Mini App and deployment surface, not legacy dead code.

## Working method

Use the engineering workflow from `Bambale0/skills`:

1. Review the active code path first.
2. Convert findings into concrete tickets.
3. Add or preserve contract/E2E coverage.
4. Ship the smallest safe fix.
5. Re-check CI and production gates.

## P0 — production blockers

### 1. Mini App generation quantity

Status: in progress in `fix/roxy-quantity-upload-p0`.

Problem:

- Backend/API can return `max_generation_quantity` and create multiple jobs.
- The active Mini App entrypoint mounts `GenerationQuantityControl`, but the enhancer must stay aligned with backend limits and must not show stale quote data after quantity changes.

Fix direction:

- Read `max_generation_quantity` from `/api/v1/generations/models`.
- Clamp quantity to the backend-supported maximum, capped at the product UI maximum of 6.
- Inject quantity into both `/api/v1/generations/quote` and `/api/v1/generations` POST bodies.
- Force a quote refresh when the user changes quantity.

Verification:

- Playwright should prove selecting `6` sends `payload.quantity === 6` to quote/create.
- Manual smoke: create screen → choose 1/2/6 → cost changes → create request contains quantity.

### 2. Mobile file upload retry

Status: in progress in `fix/roxy-quantity-upload-p0`.

Problem:

- Native `<input type="file">` keeps its value after selection in parts of the active UI.
- Mobile/iOS retry with the same filename may not fire a new change event.

Fix direction:

- Mount a global guard after the active app entrypoint.
- Reset file inputs after the current change event has been delivered to React handlers.
- Keep existing upload logic untouched.

Verification:

- Playwright should prove same-file retry triggers upload again.
- Manual smoke: choose a file, delete it, choose the same file again.

## P1 — next fixes

### 3. Active create flow should own quantity natively

The current enhancer is safe and minimal, but the better end-state is moving quantity into `roxy-social-app.tsx` draft state and `buildPayload()` so quote/create are not driven by fetch interception.

Acceptance criteria:

- `Draft` carries quantity.
- `buildPayload()` serializes quantity directly.
- Preview/recent handling supports `created.ids` without relying on only the first generation ID.

### 4. Publish/share post-publication UX

Problem:

- After publishing to feed/profile, the user should immediately be offered the share link/action for the work.

Acceptance criteria:

- Publish success opens or highlights a share action.
- Copy/share uses the durable feed/profile link, not provider media URL.
- Toast text clearly says that the work is published and can be shared.

### 5. Trend/service placement parity

Problem:

- Pinterest/service-like flows must live only in Services/Catalog, not also in Trends.

Acceptance criteria:

- Services/Catalog marks the feature as new.
- Trends list excludes the service.
- Tests protect this placement.

## P2 — hardening backlog

- Runbook: document Mini App production gates and manual rebuild command.
- Admin: audit public settings that route into Mini App but have no backend-backed configuration.
- Security: rate-limit social actions and confirm all public media/reference routes enforce visibility rules.
- Docs: keep model UI schema, billing, and provider contract docs in sync with runtime.
