# Mini App audit — 2026-10-24

Request: audit and debug the Mini App using Playwright.
Baseline: `main@665b340cd4c1cafa1aaae30bd95a70cb56755a7f`.
The existing checkout matches remote main. No clone, merge, deployment, production
mutation, paid generation or real support message was performed.

## Findings and corrections

| ID | Priority | Reproduction / cause | Correction |
| --- | --- | --- | --- |
| S1 | P1 | Open A, open B, finish A last: A replaces B. Detail requests were applied without selection ordering. | Apply success/error/loading completion only for the current selection version. |
| S2 | P1 | Type a reply in A, select B: A's text appears in B. One reply state was shared by all tickets. | Keep drafts by ticket ID in component memory; clear only the successfully sent draft. |
| S3 | P1 | Dismiss or switch a dialog while a request/reply is pending: completion reopens the old ticket. | Dismissal invalidates requests; create/reply/close/reopen follow-up refreshes respect newer navigation. |
| S4 | P2 | Select a slow/failing ticket: old actions remain usable, with no detail loading state or targeted retry. | Replace old content with a loading status; show a safe detail error and retry; keep dismissal available. |

No P0 or P3 finding was confirmed in the exercised scope. The counts describe
confirmed findings, not proof that every production interaction is defect-free.

Each of S1, S2, S3 and S4 was demonstrated by a failing browser test before its
correction. S3 also has failing reply-completion probes for both dismissal and
switching to another ticket. Additional guards cover stale errors, normal
close/reopen and completing a new ticket after selecting another conversation.
Mutation inputs are disabled until completion so edits cannot be overwritten by
a pending successful submission. Existing API payloads and ownership checks are
unchanged. Drafts survive ticket switches, not reloads.

## Browser and integration evidence

- Initial full Chromium baseline: **858 passed, 0 failed/skipped/flaky**, 625.6s.
  Command: `npx playwright test --project=chromium --workers=2
  --output=/tmp/ksu-miniapp-audit-baseline --reporter=json`.
- The pre-existing local dependencies contained Next **16.3.1**, while the lockfile
  pins **16.3.3**. Reinstalled from the unchanged lockfile before final static-build
  verification. React/ReactDOM 19.2.8; Playwright test runtime 1.56.1, matching CI.
- Regression seam: actual built UI, accessible controls, controlled HTTP ordering,
  submitted payloads and resulting dialogs. Synthetic Telegram identity and API
  responses prevent production writes. Console/page errors fail the new suite;
  only explicitly injected 503 resource errors are permitted in their two tests.
- The focused final static-export run includes all nine new support scenarios,
  production-readiness, support-contact and customer-backend-parity suites. Final
  results and exact-head full Chromium/WebKit CI are recorded in the delivery PR.
- **11 backend tests passed** in 4.14s against a dedicated PostgreSQL 17 container
  after `alembic upgrade head`: `test_profile_support_notifications.py` and
  `test_support_direct_link_contract.py`. Includes durable preferences, notification
  ownership, ticket ownership, in-progress replies, close/reopen and contact rules.
- Next 16.3.3 static production build succeeded for all 24 routes. Typecheck is
  required alongside the exact-head CI checks.
- Local WebKit launch fails before application startup due to absent GTK,
  GStreamer and other host libraries. The new suite is explicitly included in the
  existing CI mobile WebKit step. Chromium does not establish Safari correctness.
- A development-server rehearsal was unsuitable for existing production-readiness
  fixtures: dev-only toolbar, Strict Mode duplicate requests and missing development
  API paths caused failures. Those results are retained separately and are not
  reported as a successful production test. Final verification uses static export.

The initial full suite covers catalog/create forms, trend administration and
personalization, references/uploads, quote/payment races, history/generation
actions, feed/social/profile, auth/deep links/back navigation, responsive surfaces,
onboarding and sanitized client error reporting. These browser fixtures verify
client behavior; they do not prove external providers, payments or real sessions.

## Read-only deployed smoke

Public `/mini-app/` was opened in clean Chromium sessions at widths 320, 390 and
768px. Each returned HTTP 200 and the expected ROXY landing content, with no page
exception, HTTP response >=400 or horizontal document overflow. All non-GET
requests were intercepted locally. Screenshots were visually inspected.
This is an unauthenticated landing-page check, not an authenticated Telegram smoke
or verification that the proposed fixes are deployed.

## Dependency health follow-up

`npm audit --json` reports one critical dependency (`next`) and two high-severity
dependencies (`sharp`, `source-map-js`) in the existing locked dependency graph.
These are package advisory severities, not demonstrated Mini App exploit paths.
The [Next.js advisory](https://github.com/vercel/next.js/security/advisories/GHSA-2464-fhr4-w9xw)
describes image-optimization RCE; the
[sharp advisory](https://github.com/lovell/sharp/security/advisories/GHSA-wq5f-xc86-pv6w)
describes affected librsvg versions. Other Next advisories include server cache,
Server Actions and development-server paths. The package audit also reports
[source-map-js denial of service](https://github.com/advisories/GHSA-68fv-2mgg-jv7q).

Repository evidence limits exposure: `next.config.mjs` uses `output: "export"` and
unoptimized images; `Dockerfile` copies only the export into the Python runtime,
without Next/node_modules. Thus the identified Next server endpoints are absent
from this documented runtime. This is not a blanket clean-security claim. Refresh
the locked dependency graph in a separate, tested maintenance change; do not run
an automatic force upgrade or expose `next dev` publicly.

## Verification matrix and delivery boundary

UI selection/drafts/retry: browser public seam. DB/repository and authorization:
existing API regression plus exact-head CI. Migrations: N/A, unchanged schema.
Provider contracts: N/A, no integration changes or calls. Retry/idempotency:
stale responses, submission payloads and busy state; backend operation contracts
unchanged. API: existing support endpoints. E2E: Chromium and CI mobile WebKit.
Deployability: typecheck/static build and CI. Observability: console/network
evidence and existing safe error reporting; no new payload logging. Admin/config:
no new mutable business setting. Performance/query shape: no database queries
added; no comparative CWV/INP or speed improvement claim. Recovery: revert these
frontend changes; no migration/data rollback. Physical iOS/Android WebViews and
authenticated production journeys remain outside available browser evidence.

Final head SHA, CI URLs and independent Standards/Spec review findings belong to
the delivery PR so their evidence can be updated without changing the tested tree.
Merge and deployment require a separate user instruction.

## Guidance

- Local `.agents`: AGENTS, README, relevant SKILLS_INDEX entries,
  `frontend-ux-audit` and full checklist; reproduce real interactions and async states.
- `Bambale0/skills`: diagnosing-bugs, TDD, code-review; controlled RED/GREEN browser
  loops and independent Standards/Spec review. Existing user/repository instructions
  already authorize these public browser/API seams.
- `Bambale0/claw`: UX/UI/frontend audit; mobile, stale state, errors and console.
- `wondelai/skills`: clean-code; explicit, narrow state/error handling and tests.
- `Bambale0/dev-agents-pack`: debugger; confirm causes before patching.
- `agentskills/agentskills`: README inspected, progressive disclosure applied;
  no Mini App-specific debugging skill found.
- `anthropics/skills`: webapp-testing; browser reconnaissance, screenshots and logs.

All mandatory sources were fetched remotely against current default branches.
No unavailable repository or fallback; a dev-pack path lookup was corrected to
`.github/agents/12-debugger.md` on its default branch. Start baseline unchanged.
