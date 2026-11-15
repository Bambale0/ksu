# KSU workflow field presets: photo, height and weight (2026-11-15)

## Audit / current baseline
- Repository `main` baseline: `b81f86193f7dac50b8e06953cf896fec1885318d`. Branch: `fix/ksu-photo-height-weight-fields-20261115`.
- Screenshot: an admin assigned id `person_photo` to a numeric “Рост” field. Existing workflow editor allows changing the canonical photo slot into a scalar; no one-click repair or ready numeric presets.
- Existing contract: v2 two-step photo→video, per-step catalog/quote, image `@Image1`, scalar `{{height}}`/`{{weight}}`, up to 16 inputs. Prompts auto-add scalar inputs as generic *text*. No backend/schema/provider change is required.
- Reuse: `WorkflowInputEditor`, typed `TrendAdminInput`, prompt synchronization, server input validation, Playwright E2E browser seam.

## Scope and expected behavior
- Visible photo/height/weight presets in admin workflow step 1.
- `person_photo` must stay typed image; existing malformed draft can be repaired explicitly without auto-overwriting stored recipes.
- `height`/`weight` become number fields with legible labels, help and requiredness; correct existing custom labels are preserved.
- Clicking a preset must never add duplicate IDs or exceed 16 fields, and must not rewrite an admin-authored hidden prompt.
- Verify create/edit and PATCH payload from the existing browser seam, including recovery from screenshot's mistyped `person_photo`, preservation of previously configured fields, no unexpected network writes.

## Safety / rollout
- Only UI editor and E2E test change, no migration, payments, tariff, provider or saved-template rewrites.
- Admin RBAC and backend authoritative validation remain in place.
- GitHub exact-head test matrix: typecheck/build, ROXY Release Gate, relevant Playwright Chromium/WebKit, CI, after merge exact-SHA deploy and read-only smoke. No paid provider calls.
- Rollback: revert isolated UI commit; saved trend payload formats remain backward compatible.
- Sources inspected: KSU AGENTS, README, workflow spec, .agents unavailable on remote branch; Bambale0/skills TDD and implement; Bambale0/claw frontend QA; wondelai microinteractions/release-it; Bambale0/dev-agents-pack AGENTS; agentskills/agentskills AGENTS (format only); anthropics/skills webapp-testing.
