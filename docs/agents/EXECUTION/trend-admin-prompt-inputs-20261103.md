## Active Fix Execution — admin prompt references (2026-11-03)

- Baseline: main / production 28dafb3c5748ca5851f9339ae0de1c8e4d89e8da.
- Confirmed: the v2 editor starts with one photo field, accepts prompts containing three numbered photo references and sends the inconsistent recipe. Server normalization rejects it with a raw English error. Scalar personalization already supports number/text/date/select and literal {{id}} substitution; its admin editor is labelled with implementation jargon.
- Reuse: current admin RBAC/audit/API, typed inputs, model reference capacity, semantic slot IDs, parameter validation, per-step quote/debit and provider routes. No migration or tariff/configuration changes.
- Hypotheses checked: (1) missing input definitions reproduces exact error; (2) video references beyond the single bound image also reproduce; (3) missing optional middle photo silently compacts provider images without remapping prompt roles. Cover each at its public service/browser seam.
- Acceptance: pasting three photo tags creates three visible editable photo fields before save; first stays required and added refs are optional; existing fields/requiredness are preserved. Admin can add scalar fields with clear labels and literal prompt placeholders. Invalid numbering/model capacity/video tags receive Russian guidance before API write. Optional absent car must not cause clothing to take its prompt role. Required identity remains checked before quote/debit.
- Plan: failing backend and Playwright regression -> minimal editor synchronization/validation/copy -> deterministic semantic photo tag mapping -> focused backend/browser/type/build checks -> source review -> exact-head six CI gates -> merge -> exact-merge deployment and health/revision/runtime verification.
- Risks: automatic fields must be visible, bounded by model and recipe limits and never delete existing admin inputs. Prompt remapping must run once on template text before literal user substitution, never mutate the saved recipe or reinterpret user values. Existing snapshots stay immutable.
- Matrix: unit/domain + provider-input assembly covered by deterministic service tests; browser E2E covers create/edit/personalization/error; API/auth/database/idempotency/billing reuse unchanged seams plus full CI. Migration N/A (no schema); performance bounded scan <=8000 chars/16 inputs; rollout standard immutable image with previous SHA rollback; observability existing request/audit/workflow events unchanged.
- Guidance: .agents systematic-debugging/TDD; Bambale0/skills engineering/diagnosing-bugs; claw and dev-agents-pack debugger; wondelai ux-heuristics (clear labels and actionable prevention); anthropics webapp-testing. agentskills inspected: format/reference guidance only, no applicable app debugging flow. No external clones.
- Initial evidence: production normalization reproduced mismatched 1/2 photo fields and video tags; valid 2/2 and single video reference accepted. No production writes or paid generation.
- Status: regression preparation; release explicitly authorized by the user.

### Verification and review
- RED: backend optional-reference assembly produced four assertion failures and one passing all-refs control. Browser regression on unchanged UI failed with one field instead of seven and missing client validation.
- GREEN: 43 focused backend service tests passed (two PostgreSQL tests left to full CI); Ruff and diff-check passed. Existing and new Chromium editor scenarios passed 10/10 before adding the final configured-select/capacity assertions.
- Source review: publication only repairs missing definitions, never removes fields; bounds/model-capacity and video source checks precede writes. Optional reference substitution runs on template text once, before scalar insertion; missing identity still fails. Prices, admin RBAC, wallet/outbox/idempotency and provider selection unchanged. V1 editor remains V1.
- Nearby PR #490 was inspected: historical conflicting multimodal V1 Seedance work is distinct and is not included here.
- Browser verification uses the project's Playwright 1.56.1 image for WebKit system dependencies. No packages were installed into production.
- Remaining gates: both-engine workflow regression, all six exact-head CI workflows, exact merge/deploy, readiness/operational health and release markers.

## Review correction — admin prompt fields (2026-11-03)

- Original PR #578 head b3d20e22229994b7b7cf491f0846a9f21c0f20f4 passed all six gates, including 2387 backend tests, 945 Chromium cases, 280 WebKit cases and keyboard/deadline audits. Local focused both-engine workflow tests passed 98/98.
- Review identified three P2 edge cases; reproduced with one failing service regression and two failing browser regressions before repair.
- Correction: every required tagged photo must retain a prompt role; only optional trailing fields may remain unmentioned. Publication uses only the visible draft and never appends hidden inputs. A field still referenced by the prompt cannot be deleted until its reference is removed. Scalar derivation trims whitespace exactly as server substitution does.
- Verification: 44 focused service tests and Ruff pass; expanded both-engine browser regression running. Fresh exact-head six gates and production release remain required.
- Execution details: docs/agents/EXECUTION/trend-admin-prompt-inputs-20261103.md.
