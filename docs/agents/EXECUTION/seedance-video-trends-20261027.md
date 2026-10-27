# Seedance 2.5 video-reference trend audit

Baseline main/production e9037324a096ea3992cd5f63e8044811a4a5bf5a.
Confirmed ordinary model input supports reference_video aliases -> reference_video_urls
-> provider-specific reference_videos/frozen submission, with trusted metadata and ownership.
Curated TrendService intentionally rejects all video inputs/tags; public run only accepts
image references; Mini App filters uploads to image/*. Bot links open the same Mini App.

Plan: add required user-uploaded video slots inferred from @VideoN for Seedance 2.5.
Keep preview display-only and reject static video URLs in recipes (personal reference
cleanup must never silently invalidate shared templates). Existing persistent audio stays
unchanged. Separate structural recipe preflight from full runtime trusted validation;
no placeholder may reach GenerationService.create or debit. Existing video-reference
price multiplier stays authoritative, including template preview/quality costs.
No route/catalog/price/permission/moderation or schema changes.

Acceptance: admin save -> public listing -> typed upload -> authenticated run -> real
DB generation/outbox -> exact provider frozen payload; repeat preserves typed inputs.
Malformed/missing/foreign/unprobed/oversized/too-long video rejects before billing.
No paid provider HTTP; use MockTransport, isolated PostgreSQL and browser route mocks.
Rollout: independent PR after full tests, exact SHA deployment and non-charging live validation.

Guidance: KSU AGENTS/.agents pytest/verification, Bambale0/skills diagnosing-bugs/TDD,
claw backend-integration, dev-agents-pack debugger, wondelai Release It, anthropics
webapp-testing. agentskills catalog adds no task-specific provider guidance.


## Verified implementation
- Reproduced the @Video1 save rejection before changing production code.
- Admin API save -> public get -> two explicit customer runs -> real PostgreSQL
  debits -> Neironych MockTransport POST/frozen reference_videos body all pass.
- Foreign/missing/unverified/31-second/oversized video fails before any debit.
- Two Chromium journeys pass: video-only and photo+video, upload/remove/re-add,
  disabled launch, exact typed request payload and zero page errors.
- 159 focused backend/provider/pricing/audio-lifecycle tests pass; TypeScript passes.
- Full CI and production/live verification pending; no paid generation made.
