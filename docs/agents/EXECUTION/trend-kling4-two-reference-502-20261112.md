# Kling 4.0 ordinary trend photo slots / intermittent 502 — 2026-11-12

## Evidence and root cause

- User screenshot: admin editor of ordinary v1 template `МОИ СЛЕЗЫ`, model Kling 4.0 references, fails `Trend generation recipe is invalid: Undeclared reference @image_2`; a subsequent screenshot shows bare `HTTP 502`. They are not proven to be one request.
- Code: v1 `TrendService.normalize_recipe` only derives required image count from Seedance prompt, not Kling. UI `LegacyDraft` does not sync `@image_2` prompt with image count; `input_mode=none`, 0/1 image slots are accepted until preflight triggers Kling undeclared reference. Upstream API `_domain_error(TrendRecipeError)` already maps to HTTP 422; do not mislabel it 502.
- Code: `trendAdminApi.list()` previously used `Promise.all(managed, publicCatalog)`, making a public model enrichment 502 take down the working admin catalog. Raw `HTTP 502` was rendered by refresh and an empty list shown after a failed request. No evidence yet that a genuine backend gateway 502 is caused by the validation failure. Existing iPhone browser E2E specifically reproduces cold/late HTML 502.
- Read-only production Docker logs near screenshot local time were checked. No matching successful create request or backend 502 could be reliably correlated with the image from the provided time alone; avoid inventing a root cause for upstream failure.
- **PR #588** is a separate *unmerged draft* for immutable admin-owned pinned reference video and exactly two visitor photos. This fix does not pretend that feature was delivered, and must not silently interpret a trend preview URL as video generation input.

## Scoped remediation
1. For ordinary Kling 4 v1 only, derive minimum number of customer image uploads from canonical `@image_N` and compact `@imageN` tags. Automatically include two if `@image_2` exists. Validate actual reference capacity; reject indices above provider limit, and preserve explicit upper bounds if greater.
2. Mirror derivation in Mini App editor so choosing/writing the Kling prompt visibly creates the necessary upload fields. Never send a malformed 0/1-slot payload and never mutate other models' recipes.
3. Handle transient public model-catalog failure independently of authoritative admin managed data; when authoritative GET fails keep retry and don't falsely declare empty. Map raw 502 and unsupported reference messages to actionable Russian while preserving HTTP error semantics and backend logs.
4. Add backend unit + preflight regression and Chromium/WebKit Playwright scenarios, including 502 recovery and no unintended writes.

## Release/rollback
- No migration, wallet or provider switching, secret changes or paid generations.
- Confirm exact-head PR checks, merge-gated full E2E, release SHA and API availability. Live authenticated admin draft creation should be smoke-tested only with intentionally test-scoped data, not publish a real trend without content approval. PR #588 will require a separate gated release.
- GitHub instruction sources: KSU AGENTS.md; `.agents/AGENTS.md`, `.agents/README.md`, `.agents/SKILLS_INDEX.md` are absent remotely; `Bambale0/skills` README (engineering workflow), `Bambale0/claw` backend-integration, `wondelai/skills` release-it, `Bambale0/dev-agents-pack` API-integrator, `agentskills/agentskills` format, `anthropics/skills` browser-test procedure.
