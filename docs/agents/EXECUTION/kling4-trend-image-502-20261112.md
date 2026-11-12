# Kling 4.0 trend image slots + admin 502 resilience · 2026-11-12

## Observed production incident
- Screenshots: on iPhone ROXY trend creation with title «МОИ СЛЕЗЫ», model Kling 4.0 references, initially displays `Undeclared reference @image_2` then `HTTP 502`.
- Production container/mini-app SHA: `bb36a322664489fede7dfd9371b4dedc280497b0`.
- Read-only production logs confirm multiple `POST /api/v1/trends/manage` 422 at 2026-11-12 04:20, 04:24 and 06:40 UTC, and `GET /api/v1/trends/manage` 200. No 502 observed from application logs during the checked period. Failure to load a separate API is independent of recipe validation; don't call it the same root cause.
- Read-only SQL confirms no saved `admin_trends` row matching «СЛЕЗЫ», consistent with failed saves.
- Existing `TrendService.normalize_recipe` derives required references only for Seedance, not Kling4. A Kling prompt mentioning @image_2 can therefore reach template validation with one synthetic image, giving `Undeclared reference`.
- Mini App's v1 editor did not infer image slots from the prompt. The admin load code conflated `Promise.all` for managed catalog and optional public catalog; a failed public catalog could reject all model data and raw `HTTP 502` leaked into the active form through shared error state.
- Separate pinned-video feature remains in **draft PR #588**, not merged as of this inspection. This change does not pretend to deliver that unrelated feature, expose hidden media or treat preview as provider video reference.

## Fix, compatibility and invariants
- For one-stage **Kling 4.0 only**, accept `@image_1/@image_2` and compact `@Image1/@Image2`, require contiguous indices, and infer required/minimum image count (2 for this example). Never silently count preview as input; a `@video_1` in this one-stage recipe is still explicitly invalid with a Russian message because the pinned-video capability has not shipped.
- Admin form synchronizes ordered image uploads and validates before API write; persisted legacy recipes with different counts are not rewritten and other models' recipe rules remain unchanged.
- Server still validates independently (never trust browser metadata) and uses exactly the inferred count of placeholder images when preflighting the provider; missing references are translated to actionable Russian.
- Managed trend list is authoritative; public model catalog enrichment failure is optional. A failed managed load shows a retryable loading error rather than a fake empty catalog or raw HTTP status in the form. Browser E2E cover iPhone 502 and two-image save.
- No ROX price/route/payment changes, no token/key access, no paid generation tests, no database migration/destructive writes.

## Engineering sources
Read current KSU `AGENTS.md`, implementation and prior incident docs; repository-local `.agents/AGENTS.md`, `README.md`, `SKILLS_INDEX.md` absent on GitHub (may be workstation-local). Inspected `Bambale0/skills` README (engineering/TDD approach), `Bambale0/claw/.agents/skills/frontend-qa/SKILL.md`, `wondelai/skills/release-it/SKILL.md`, `Bambale0/dev-agents-pack/.github/agents/04-api-integrator.md`, `agentskills/agentskills` README (format; no app-specific flow), and `anthropics/skills/skills/webapp-testing/SKILL.md`. Follow small changes, reproducible tests and exact-SHA release gates.

## Release checklist
RED regression tests first, then targeted backend and browser, typecheck/build, exact-head CI/Admin/Batch/ROXY E2E, PR review, merge, six full main gate workflows including Chromium and WebKit, immutable exact-SHA deploy, production ready/live/operational + mini-app release + read-only smoke of new recipe. No production claim until proven.
