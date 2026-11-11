# Kling 4.0 soundtrack routing and KIE credit incident — 2026-11-11

## Evidence / reproduce
- Production `tanyapi` runs immutable KSU `c69030e76fd5482d034460c847735698bad1593f`.
- `generation_provider_routes` revision 10 has `kling-4.0: [neironych,kie]`, zero user-scoped Kling overrides.
- Representative production generations included video references with `keep_original_sound=true`; they were snapshotted on Neironych but pre-spend downgraded to KIE with `Neironych Kling cannot preserve elements, voices or original-sound controls`. Several subsequent KIE createTask requests returned `Credits insufficient` (certain no-task rejection). Some earlier KIE jobs succeeded.
- Independent provider balance query was HTTP 200 with 119.73 KIE credits at time of inspection; this is **not** enough evidence for every duration/quality because KIE supplier price changes and balance may move.
- Vendor KIE docs `https://docs.kie.ai/market/kling/v4-reference-to-video` explicitly state `keep_original_sound=false` is default and only acts when `video_urls` are provided. Current Neironych reviewed API doesn't implement original video audio preservation.
- Alternative hypotheses eliminated: model defaults in code remain KIE, but production DB overrides them; no per-user overrides; `keep_original_sound` is the actual capability trigger in task metadata. Other edge cases (elements/voices, auto T2V, HTTP inputs, model keyframes) remain distinct.

## Scoped implementation
- Audit `.agents/` not present in versioned GitHub branch; `.clinerules` directory exists. Consulted repository AGENTS, CONTEXT, model contracts, runtime routes, KIE upstream docs and tests.
- Skill evidence: `Bambale0/skills` README (engineering skill registry); `Bambale0/claw/.agents/skills/backend-integration/SKILL.md`; `wondelai/skills/release-it/SKILL.md`; `Bambale0/dev-agents-pack/.github/agents/04-api-integrator.md`; `agentskills/agentskills/README.md` (format only); `anthropics/skills/skills/webapp-testing/SKILL.md` (existing Playwright CI preferred). No changes to the common `Bambale0/start` baseline.
- RED regression tests added before backend changes (false flag, true flag, route, admission, provider-error handling).
- Explicit false is omitted from Neironych native wire only, not original request snapshot; true with video and named elements/voices preselect KIE before wallet/outbox; unsupported single-provider routes fail before debit; public toggle explains the policy.
- KIE certain 402 is localized and refunded using existing idempotent ledger path. Ambiguous responses are not treated as no-task.
- No migration, supplier rates, credentials, retail tariff or admin DB route changes. No automatic retries of rejected KIE paid tasks.
- Test matrix: focused unit/provider/DB; full CI; six workflows including ROXY E2E/Playwright; exact-head review; release-health and read-only production route/asset checks. Paid smoke requires budget because KIE supplier account currently short for some tasks.

## Risk / rollback
- Tasks already accepted on KIE retain frozen provider; no automatic job migration.
- KIE can reject requests with `keep_original_sound=true` until operator replenishes account. No silent audio downgrade and no fake success claim.
- Follow existing immutable deploy gates, rollback to previous image and retain ledger; no destructive migration.
