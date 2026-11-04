# Mini App audit implementation — 2026-11-04

## Scope and baseline

- Baseline main: `81ac57608e1807b0c7f81a681032b790c1ceb077`.
- Branch: `fix/miniapp-audit-20261104`.
- User explicitly authorized implementation of the preceding UI/layout/logic/design audit and professional team development. Deliver reviewed, tested source changes and a PR; no production changes, paid requests, financial mutations, broadcasts or migrations.
- Source discovery used connected GitHub. A clean local checkout is needed for build, browser regressions and visual comparison; it is not a production working tree.
- Existing open canonical-home/catalog PRs are stale on older bases. Preserve current route/deep-link behavior and improve the present composition rather than merge unrelated old branches.

## Fresh audit and reuse

The prior deployed-frontend audit exercised seven routes across eleven viewports with mocked API/Telegram data. Confirmed failures: models HTTP 500 becomes an indefinite loading screen; history HTTP 500 becomes a false empty state and rejected Promise; quote error has no explicit retry; model sheet does not control focus or Escape; labels are tiny; Nano Banana truncates at 320px; CSS replaces meaningful contextual hints; internal technical copy is visible. Catalog and service sections repeat across a very long discovery screen.

Existing seams: `RoxySocialApp`, route feature loader, typed `api` methods and HTTP error messages, history pagination, model families, sequence-protected quote effect and submit guards, CSS design tokens, catalog feature hub, customer parity routes, current Playwright fixtures/config. No provider, auth, billing, pricing or backend API invention is needed. No broad pre-refactor is required.

## Acceptance

1. Model failure shows a recoverable error; retry loads the form without restarting the Mini App; a truly empty catalog is distinct from loading/error.
2. History distinguishes loading/empty/error, retains existing works on refresh failure, retries safely and emits no uncaught rejection; stale replies cannot overwrite a newer request.
3. Quote failure offers retry with the same description/parameters; launch stays blocked until the current quote is valid. Existing quote freshness and double-submit protection remain.
4. Model sheet moves focus inside, traps Tab/Shift+Tab, closes on Escape, restores focus and preserves scrolling behavior.
5. Typical model names/prices fit 320/360px; nav and metadata are readable; contextual instructions remain meaningful; customer copy contains no internal backend wording.
6. Catalog reduces duplicate discovery blocks while retaining access to every existing feature and keeping current routes/deep links. Forms and responsive grids use existing tokens.
7. No payment/provider/auth/schema behavior changes; public browser/auth fallback and critical existing generation paths retain their contracts.

## Team ownership

- Logic developer: `roxy-social-app.tsx`, a focused dialog/helper if necessary, `e2e/audit-recovery.spec.mjs`.
- Visual developer: existing CSS, catalog/parity feature composition and copy, partner input presentation, `e2e/audit-design.spec.mjs`.
- Controller: execution ledger, integration, dependencies/local runner, source publication and CI evidence.
- Independent reviewer: Standards and Spec review against final diff; authors resolve findings before final exact-head checks.

## Verification matrix

| Category | Decision / evidence seam |
|---|---|
| Unit/domain | Browser-level component state regressions; no duplicate implementation-mirroring unit tests |
| Database/repository | Unchanged; existing exact-head CI backend regression |
| Authorization/access | Unchanged server boundary; existing auth/onboarding browser checks and CI |
| Migrations | N/A: no schema change |
| Provider/external contract | N/A: provider requests/contracts unchanged; API boundary mocked in browser tests |
| Idempotency/retry | Existing double-submit/freshness suites plus quote retry and single-submit regression |
| API integration | Existing typed endpoints retained; HTTP failures/recovery covered at browser boundary |
| Frontend E2E | New failing regressions, focused adjacent suites, responsive matrix, Chromium and available WebKit/CI |
| Smoke/deployability | Typecheck/static build; local exported frontend. No production release claim |
| Observability/audit | No secrets/new tracking; eliminate unhandled error and show actionable user state; retain existing reporter |
| No-hardcode/admin | No mutable business values added; model/price/catalog data remain server-owned |
| Performance | Avoid duplicate surfaces; verify lazy readiness and no new startup blocking; no speculative metrics claims |
| Rollback/recovery | Ordinary code revert; no DB/config rollback required |

## Risks and mitigation

- Legacy imperative feature insertions and quote guards may depend on DOM structure: retain essential selectors and run adjacent suites.
- CSS changes can affect standalone routes/keyboard behavior: inspect mobile/landscape and existing responsive/keyboard tests; avoid hiding functionality to reduce length.
- Retry responses can race navigation/refresh: use request sequencing and cleanup at the existing request boundary.
- Real iOS/Telegram keyboard and safe areas cannot be proven by Chromium viewport emulation; report remaining platform limits.

## Plan and progress

1. Record fresh context and guidance before code edits — complete. Mandatory `.agents`, `Bambale0/skills`, `Bambale0/claw`, `wondelai/skills`, `Bambale0/dev-agents-pack`, `agentskills/agentskills`, `anthropics/skills` refreshed. Applied frontend-ux-audit, evidence-first diagnosis, implement/TDD, independent code review and refactoring-ui heuristics; agentskills provides format/progressive-disclosure only. Shared Start baseline is unchanged and unambiguous.
2. Add public browser regressions; record RED on baseline — complete. Seven recovery assertions failed against the deployed baseline for their intended reasons. The first design run used an incomplete Telegram fixture and was not treated as product evidence; after intercepting the SDK and waiting for the app, all seven design cases failed against the unchanged local exported build (hidden instructions, 78px text in a 58px title box, tiny text, absent grouping, single-column desktop, internal copy and unstyled inputs). Baseline static build/type validation passed. A stronger carousel regression passed on baseline; motion was not changed and is not claimed as a fix.
3. Implement focused recovery/dialog and UI/composition slices — first implementation complete; verification and independent review in progress. Model loading no longer blocks unrelated navigation; history state/cursor retry catches failures; quote retry preserves the existing freshness/submit boundary; model sheet manages focus/Escape. Catalog groups secondary destinations in native disclosures, retains all routes and visible primary tools, restores contextual copy and readable responsive controls. The old source-contract wording was updated to the new public copy without weakening route assertions.
4. Typecheck/build, focused and adjacent browser suites, visual review; fix regressions.
5. Independent Standards/Spec review; publish PR and verify required checks on its exact final head SHA.

## Verification evidence before publication

- Final application snapshot built successfully with `ROXY_E2E=1`; Next static export includes all 24 routes. Explicit `next typegen` and `tsc --noEmit` passed. Local Node is 24.22.1; CI retains its existing Node 22 environment.
- The OneDrive checkout intermittently produced invalid reparse-point/module-read errors in installed dependencies. Runtime verification moved to a disposable local directory outside OneDrive. All `app`, `components` and `lib` file hashes match the canonical source checkout; no product workaround or CI relaxation was added.
- New regression coverage: nine recovery cases plus seven UI cases, **32/32 passed across Chromium and mobile WebKit**. This includes history cursor retry and a controlled stale page arriving after a newer refresh, quote retry with the same draft and one submit, and dialog focus/Escape/restore.
- Adjacent Chromium selection: **145/146 passed initially**; the existing landscape navigation limit exposed a real 70.1875px regression after adding the visible central label. Reducing only the landscape icon container from 32px to 28px preserved 11px labels and 48px button targets. Its existing assertion then passed in **both engines (2/2)**; no assertion was relaxed.
- Pure source contracts: **33 passed** with `pytest --noconftest` for six relevant contract modules. The minimal local Python environment cannot collect backend-importing contract modules because SQLAlchemy is absent; full backend/integration verification is delegated to unchanged exact-head CI.
- Existing browser copy assertions were updated to the new exact heading; grouped shortcuts now explicitly open their native disclosure before the same click/URL outcome. The create validation assertion targets the actual submit button rather than the now-labelled navigation action. Existing feature counts, destinations, price freshness and double-submit assertions remain.
- Independent Standards and Spec reviews: no open production-code findings. The initial missing stale-overlap proof was addressed with a public browser regression and independently re-reviewed. `git diff --check` passed.
- Visual comparison uses the same synthetic fixture, not customer data. At 320px the Nano Banana title now has 197px available rather than 58px and is not truncated; navigation labels are 11px. The 390px catalog document measured 3171px versus the earlier 4785px audit snapshot after grouping secondary services. This is layout evidence, not a real-user performance claim. All destinations remain accessible.
- Both new specs were added to the existing WebKit workflow selection. Existing jobs/checks, provider/auth/payment boundaries and runtime configuration are unchanged.
- After the intentional heading/disclosure/submit-target updates, **52/52 affected existing user/referral scenarios passed across Chromium and mobile WebKit**, including five viewport sizes and history reload preservation.
- Baseline pinned dependencies reported npm advisories during installation. No dependency upgrade or automatic audit fix is bundled into this UI change; static export/unoptimized images remain as configured. Dependency remediation needs separate scoped verification.

Exact-head CI outcomes and the final source SHA are recorded in the PR delivery evidence rather than committing another documentation-only tree after its checks. Production has not been changed; actual Telegram/iOS keyboard, background/reopen and real paid generation remain outside this implementation's verification.
