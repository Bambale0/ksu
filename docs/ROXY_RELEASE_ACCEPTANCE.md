# ROXY release acceptance

**Baseline:** 2026-08-27.

A ROXY change is production-complete only after every applicable required gate passes on the final PR/main SHA and `Deploy Production` verifies that exact SHA in production.

## Required GitHub gates

Current required contours:

- **CI** — TypeScript/Next build, Ruff, Python compile, migrations, focused domain tests and full backend/product regression;
- **ROXY E2E** — production-like API/workers/providers plus real browser journeys;
- **Mini App Playwright E2E** — Chromium scenario/focused-spec audit plus mobile WebKit responsive audit;
- **ROXY Release Gate** — release-contract checks;
- **Admin Console** — privileged UI/security regression;
- **Batch Generation** — batch contour regression.

Do not merge by deleting, skipping or weakening a failing scenario that represents the intended production contract.

## Mini App browser gate

The maintained named matrix is:

```text
300 existing isolated user scenarios
150 additional system-risk scenarios
------------------------------------
450 named matrix scenarios
```

The additional 150 are 30 distinct contracts repeated across five viewport classes. Chromium also runs other focused specs in `frontend/mini-app/e2e`, therefore the raw Playwright count is greater than 450.

Required workflow steps:

```text
Run 450-scenario Mini App audit
Run iPhone/iPad WebKit responsive audit
```

## High-risk acceptance contracts

At minimum a release affecting these domains must preserve:

### Create / models / pricing

- clean fresh Create unless an explicit history/feed reuse action is chosen;
- backend `ui_schema` drives fields/options;
- each model variant displays backend price metadata;
- published admin tariff, model catalog, quote and debit use the same resolver;
- latest published generation pricing is observed across API workers/restarts;
- image, video and music/Suno stay inside the same pricing governance.

### Feed / publication

- TikTok-style feed remains the production feed surface;
- foreign-user Repeat can use a hidden source prompt without disclosing it;
- share/comment/like/repeat actions re-authorize the feed/profile surface;
- publication sharing returns a usable Telegram link;
- no-short-name fallback uses `t.me/<bot>?start=<payload>`, never synthetic `/app`.

### Trends

- public curated recipe never exposes hidden prompt/provider parameters;
- inline admin controls are absent for normal users;
- every inline admin write rechecks active `AdminAccount` + `social.moderate`;
- create/edit/duplicate/hide/restore use the same curated store;
- preview upload is durable/product-owned;
- trend generation goes through normal generation pricing/outbox/recovery.

### History / references

- owner history remains distinct from publication state;
- explicit restore/repeat reconstructs safe server-owned settings;
- reusable references remain user-scoped and durable where supported.

### Wallet / partner

- payment state is server-authoritative;
- no client-created financial truth;
- referral/profile links preserve their start payload in Direct Mini App or bot-start fallback form.

## Production deploy acceptance

After merge, `Deploy Production` must target the exact final `main` SHA and complete:

1. required main checks/waits;
2. pre-migration PostgreSQL backup/validation as configured;
3. exact commit checkout/build/deploy;
4. Alembic migration;
5. API and worker startup;
6. `/health/live`, `/health/ready`, `/health/operational` checks;
7. `/mini-app/release.json` verification against `GITHUB_SHA`.

A merged PR is **not** production-complete while deploy is queued/in-progress/failed or if the release JSON SHA differs.

## Audit evidence

For the 2026-08-27 expansion from 300 to 450 named scenarios see `SYSTEM_AUDIT_2026-08-27.md`.
