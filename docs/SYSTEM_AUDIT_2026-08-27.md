# ROXY system audit — 2026-08-27

## Purpose

This audit expands the maintained Mini App release matrix from 300 named user scenarios to **450 named scenarios** and runs it together with the repository's existing focused Playwright specs, backend regression and production release gates.

The goal is not a synthetic test-count milestone. The extra scenarios target contracts that recently changed or have high production impact: cross-user publication actions, hidden prompt privacy, Telegram link fallback, admin-controlled Trends, dynamic pricing, reference/history restore, publication, wallet and mobile layouts.

## Production baseline entering the audit

The audit branch was created from production-tested `main` SHA:

```text
b6f9d36b9783c144d560e99e86eb881f87fe7427
```

That SHA corresponds to the inline Trend-management rollout and was deployed successfully by **Deploy Production #318** before this audit branch was created.

Audit PR: **#286 — test: expand ROXY system audit to 450 scenarios**.

## Matrix structure

Existing matrix:

```text
300 isolated user scenarios
```

Additional matrix:

```text
30 distinct system-risk contracts × 5 viewport classes = 150 scenarios
```

Viewport classes:

```text
320 × 568
360 × 740
390 × 844
430 × 932
768 × 1024
```

Combined named matrix:

```text
450 scenarios
```

The Chromium command runs all Playwright Chromium specs in `frontend/mini-app/e2e`, so the raw Playwright count is intentionally **greater than 450**. The number 450 refers to the two maintained scenario matrices, not every focused spec in the directory.

A separate mandatory step runs the responsive suites under mobile WebKit for iPhone/iPad behavior.

## Added risk coverage (301–450)

The 150 added scenarios cover:

### Feed / privacy / cross-user actions

- foreign-user Repeat when the public prompt is hidden;
- no hidden-prompt disclosure in details/actions;
- Telegram publication share request/link behavior;
- like → unlike state cycle;
- `Подписки` tab behavior;
- comments loading.

### Curated Trends / admin

- inline admin control visible only to admin users;
- ordinary-user absence of the admin button;
- manager list/status rendering;
- required-field browser validation;
- durable image/video preview upload path;
- hide → restore cycle.

### Catalog / pricing

- explicit variant price for image models;
- explicit variant price for video models;
- explicit variant price for music;
- prompt tools discovery;
- image/video Trend launch.

The price scenarios consume API/catalog values rather than frontend constants, protecting the Admin Tariffs → catalog → UI contract.

### Generation / history / references

- clean new-create prompt state;
- live quote visibility;
- generation submission/queued state;
- saved reference selection;
- history settings restoration;
- video duration-control contract.

### Partner / publication / wallet / navigation

- referral `/start` fallback link through the actual copy action;
- author-profile `/start` fallback;
- referral reward ledger;
- profile → feed publication;
- card/wallet package surface;
- primary navigation integrity and feed entry.

## First expanded run: evidence and findings

The first Chromium invocation on PR #286 executed:

```text
629 total Playwright tests
619 passed
10 failed
```

The 10 failures represented **two distinct new scenario assumptions repeated across all five viewport classes**, not ten independent product failures:

1. **Trend create validation** — the test expected a React `role=alert` after submitting an empty form. The actual production form uses native HTML5 `required` validation, which stops submit before the React handler. The scenario was corrected to assert the real browser contract: the required title input is invalid/value-missing, submission keeps the form open and focuses the invalid field.
2. **Partner referral fallback** — the test expected the referral URL to be printed as visible text. The current product intentionally displays the author-profile link and exposes the referral link via **Скопировать реферальную ссылку**. The scenario was corrected to execute the real copy action and assert the exact clipboard value `t.me/<bot>?start=ref_...`.

No production code was weakened or changed merely to satisfy these test assumptions. The checks were aligned with the existing user-facing contract while preserving the underlying fallback/privacy requirements.

## Mandatory non-browser coverage

The audit PR also remains subject to the repository's normal required gates:

- CI: TypeScript, Next build, Ruff, Python compile, migrations and full backend/product regression;
- ROXY real-browser E2E;
- Admin Console;
- Batch Generation;
- ROXY Release Gate;
- Mini App Chromium + mobile WebKit Playwright.

The first audit cycle already confirmed the non-Playwright required gates green before the two scenario assumptions above were corrected.

## Release rule

This audit is accepted only when:

1. the current PR head passes every required gate;
2. the 450-scenario Chromium step passes without deleting/marking the new scenarios skipped;
3. iPhone/iPad WebKit responsive audit passes;
4. the PR is merged to `main` without replacing runtime protections with test-specific bypasses;
5. `Deploy Production` succeeds for the exact merge SHA;
6. production health checks pass and `/mini-app/release.json` equals that merge SHA.

A green PR without an exact-SHA production deploy is not considered a completed production audit.

## Maintained test files

```text
frontend/mini-app/e2e/roxy-user-scenarios.spec.mjs
frontend/mini-app/e2e/roxy-system-risk-scenarios.spec.mjs
.github/workflows/miniapp-playwright.yml
```

The workflow step is named:

```text
Run 450-scenario Mini App audit
```

Do not reduce the matrix back to 300 or convert the added risk cases into skipped/inert assertions to make a release green.
