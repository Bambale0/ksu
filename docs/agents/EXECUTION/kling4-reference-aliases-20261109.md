# Fix Kling 4.0 reference aliases — 2026-11-09

## Evidence and audit (before production-code changes)
- Baseline: `main@aff35968cb9a7117db516fc70bb7da6443157f9f`; production `ksu-app-1` image `ksu-app:aff35968cb9a7117db516fc70bb7da6443157f9f` on `tanyapi`.
- Incident: 2026-11-09 production `POST /api/v1/generations/quote` returned HTTP 422 multiple times, including request IDs `c93a5670-0623-4f30-b679-6f23f377ad73`, `e01c5d39-3d14-4abb-9b07-5a256c5d2c79`, `40a2ea6b-1c43-41ea-bf39-4ae0709a927c`. Log payloads omit model and validation reason, so these events cannot individually be attributed to this error by correlation ID alone.
- The customer's iPhone Mini App screenshot reports `Undeclared reference @image1` for Kling 4.0 with image and video references.
- Read-only reproduction in the actual production runtime: `normalize_kling4_input("kling-4.0/reference-to-video", {"prompt":"@image1","duration":5,"image_urls":["https://example.invalid/test.png"]})` raises `Kling4ContractError: Undeclared reference @image1`; changing only the prompt to `@image_1` succeeds.
- Root cause: the shared `kling4_contract._mentions` accepts only the provider's canonical `@image_N/@video_N` declarations while users enter natural `@imageN/@videoN`. The common `ModelCatalog.prepare` contract is applied in both quote and create before debit and provider dispatch. The generated task persists `clean["prompt"]`.
- Exists/reusable: strict reference count and named-entity validation; provider Kie and Neironych adapters; existing quote/create and billing/rollback/outbox flows; user-upload ownership and measured video duration enforcement; server-driven tariff/admin configuration.
- Missing: safe normalization of unambiguous compact image/video aliases; regression tests at billing/contract/provider boundaries; end-user guidance in docs.
- Alternatives checked: missing image upload (canonical prompt accepted with same image); video duration failure (different error and checked later); renderer-only fault (direct backend repro disproves).
- No prefactor, schema migration, admin setting, provider-route change, pricing change, or new secret required. Do not touch billing or force paid test generations.

## Acceptance criteria
1. When an uploaded image/video exists in its specific numbered slot, Kling 4.0 reference-mode accepts `@image1/@Image1/@video1/@Video1` and translates to canonical `@image_1/@video_1` before validation, pricing, storage, and provider transport.
2. Canonical names, case-sensitive named element/voice references, punctuation adjacent to tags, and untouched input objects keep their semantics. Existing named element `image1` takes precedence over shorthand, avoiding a silent role switch.
3. Missing slots (`@image2` with only 1 image), zero/leading-zero indices, incomplete suffixes (`@image1abc`), keyframe-only model, unsupported `@` tags and all other strict caps remain rejected before debit/provider.
4. Existing admin-configurable price and provider routing remain unchanged.
5. Exact-head test/CI + guarded PR merge, immutable image deployment and read-only production quote/normalizer smoke confirm release. No paid user generation.

## Verification matrix
- Unit/domain: new normalization and negative/boundary regressions, existing Kling contract suite.
- API/quote: `GenerationService.prepare_request` quote service regression; production log/status check.
- Provider/immutable job: existing `GenerationProviderService._input_for` and Kie/Neironych adapter tests; test persisted prompt using existing DB-backed create seam if available.
- DB/auth/billing: existing scoped-owner and no-debit checks; no new write path. Retain idempotency/retries/reconciliation unchanged.
- Frontend: no client source change; main-user flow validated at service/HTTP seam, Playwright existing Kling E2E in CI.
- Migration/config: N/A; no new tables or parameters or tariff constants.
- Security: preserve owner-scope media checks, fail-closed undeclared tags; no raw prompts or user identifiers in logs.
- Observability: retain request ID with 422; monitor number of `/generations/quote` HTTP 422 post-release.
- Performance: bounded prompt scan <=8000 characters, reference maxima unchanged.
- Rollback: revert small commit through protected main/immutable release; existing provider routing unchanged.

## Instruction/skill audit
- KSU `AGENTS.md`, `CONTEXT.md`, `docs/kling-4.md`, `.clinerules/skills/systematic-debugging` and `test-driven-development` checked; `.agents/` is not versioned/currently absent on GitHub (workstation-local).
- Primary `Bambale0/skills` diagnosing-bugs and tdd read; external `Bambale0/claw` AGENTS/code audit and `Bambale0/dev-agents-pack` PR review checklist read; `wondelai/skills` release-it read; `anthropics/skills` webapp-testing reviewed for existing Playwright checks; `agentskills/agentskills` format guidelines inspected, no application-specific Python guidance.
- Remote GitHub connector for code; SentinelX only to inspect actual production/runtime/test state and guarded release. No unnecessary clone.

## Execution ledger
1. Capture RED reproduction on production runtime (read-only) — complete.
2. Scoped regression tests committed first; confirmed RED via production runtime direct `GenerationService.prepare_request(None, @image1)`, which produced `InvalidModelParametersError: Undeclared reference @image1.` (exit=1).
3. Shared contract updated after RED: only existing image/video slot aliases normalized, explicit element/voice names win, strict Unicode boundaries and 8000-char post-normalization cap remain.
4. Focused tests, integration/browser coverage, independent diff review — pending CI.
5. Open PR, exact-head CI, protected merge, deploy verified SHA, and production smoke — pending.
