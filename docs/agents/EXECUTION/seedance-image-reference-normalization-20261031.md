# Seedance / Neironych image-reference normalization — 2026-10-31

## Fresh audit

- Baseline: `main` / production `e52109718e2ae9624fbf7de951e621f7b128cafa`; branch
  `fix/seedance-image-ref-normalization-20261031`.
- Confirmed production cases (read-only inspection, no URLs or image bytes copied):
  - `523f4b46-d1df-4e60-879b-fc1ab1ec194e` contains one valid 1280x1707 WebP and
    failed locally with `Seedance image references must be JPEG or PNG` before a
    provider task was created.
  - `86ea5e0c-7600-47b8-8dc2-ba8609d5709e` contains one HEIC plus one valid JPEG;
    the HEIC is not decoded by the current Pillow-only path and the generation failed
    locally with `Seedance image reference is not a valid JPEG/PNG` before provider POST.
  - Both rows are `failed`, provider `neironych`, have no external task/snapshot, cost
    300 ROX, and already have one debit plus one automatic refund. Historical wallet
    entries will not be rewritten.
- Exists/reuse: shared Neironych Seedance snapshot boundary, bounded/SSRF-guarded reference
  download, byte and dimension validation, immutable content-hash transport storage, atomic
  publish, EXIF transpose for legacy MPO, generation outbox retries, idempotent debit/refund,
  and the separate admin Seedance upload/submission queue.
- Partial: only product-owned MPO files are converted. Valid WebP/HEIC/AVIF/TIFF and files
  whose extension or declared MIME disagrees with their bytes are rejected. Admin direct
  uploads validate bytes but reject rather than normalize unsupported image formats.
- Missing: one format-by-bytes normalizer used by ordinary, trend, repeat and admin paths;
  HEIF decoding support; regression coverage for the two UUID failure classes, false MIME,
  corrupt JPEG, EXIF orientation, order, size/time bounds, storage atomicity, retry and
  no-second-charge behavior.

## Intended behavior and boundaries

- Immediately before the first immutable Neironych Seedance request is frozen, inspect every
  image reference by decoded bytes, not URL suffix or Content-Type. Preserve valid JPEG/PNG
  URLs. Convert decodable unsupported images to an immutable provider-only JPEG/PNG transport
  copy in the same order, with EXIF orientation applied. Never mutate the original reference,
  generation parameters, trend/repeat recipe or other-provider input.
- Apply the same byte normalizer to the direct admin Seedance media upload before requesting a
  provider upload ticket. Video/audio behavior remains unchanged.
- Corrupt or undecodable input fails before provider POST with a safe validation error. Network,
  timeout and storage failures remain retryable through the existing worker/outbox boundary and
  never create a second generation/debit.
- No provider route, price, permissions, schema, migration, public URL hardcode, credential,
  customer prompt, or unrelated production data change.

## Acceptance criteria

1. Actual JPEG/PNG bytes remain unchanged even with a wrong suffix/MIME.
2. WebP and HEIF references become valid JPEG/PNG provider URLs; original bytes/URLs remain
   unchanged, reference order is stable, and EXIF orientation is reflected in output geometry.
3. Corrupt JPEG, decompression/dimension/byte overflow, redirect/SSRF, timeout and failed atomic
   storage paths fail closed without provider POST.
4. Ordinary generation, trend, repeat and admin submission paths share the normalizer rather
   than duplicating URL/provider-specific conversion rules.
5. Snapshot/idempotency semantics remain immutable. Retried normalization reuses the same
   content-addressed result and does not create another wallet debit.
6. Exact-head CI, review, merge, deploy and exact production revision/health/worker checks pass.
7. Only after deploy, the two named failed rows are replayed through an audited, no-charge path;
   no other production writes occur. Historical refunds are neither reversed nor repeated.

## Verification matrix

- Unit/domain: byte detection, JPEG/PNG pass-through, WebP/HEIF conversion, corrupt JPEG,
  EXIF transpose, order, dimensions and byte limits — required.
- Database/repository: one debit/no new debit on retry/replay and immutable original parameters —
  required.
- Authorization: existing owner/admin entry guards unchanged; replay must be scoped to the two
  exact rows — required production audit.
- Migrations: N/A; no schema change.
- Provider/external contract: mocked upload ticket/storage PUT/video POST, exact normalized MIME
  and body — required; no paid call during tests.
- Idempotency/retry/reconciliation: frozen body and content-hash artifact reused; transient
  download/storage failure releases the existing outbox row — required.
- API integration: ordinary generation admission and stored reference contract unchanged —
  adjacent regression coverage required.
- Frontend/Mini App/bot E2E: no UI contract change; trend/repeat/admin service seams plus existing
  exact-head E2E are required.
- Smoke/deployability: Ruff, compileall, focused/full tests, dependency build, six exact-head
  gates, production health/release/worker/log verification — required.
- Observability/audit: safe error category and generation/provider correlation only; never log
  URLs, tokens or bytes — required.
- No-hardcode/admin: provider base URL and product media URL remain configuration/storage owned;
  supported wire formats are protocol constants — required.
- Performance: bounded stream/temp-file processing; no unbounded in-memory download; conversion
  runs off the event loop — required.
- Rollback/recovery: revert source/dependency change; existing original references remain intact;
  drain accepted tasks before any rollback — required.

## Implementation plan

1. Add RED regressions for the two production failure classes and pass-through/corruption cases.
2. Generalize the existing MPO helper into a bounded byte/URL image normalizer and add HEIF
   decoding support; turn RED to GREEN one vertical slice at a time.
3. Wire the same normalizer into admin direct uploads; prove all four entry scenarios converge at
   the shared boundary and provider calls stay mocked.
4. Add retry/storage/billing regressions, run focused then full verification, and perform separate
   standards/spec review.
5. Push PR, require exact-head CI, merge and verify exact-SHA production deployment.
6. Inspect the two rows again, perform only the audited no-charge replay, then verify provider
   task state, terminal delivery and user notification.

## Guidance applied

- Local `.agents`: `systematic-debugging`, `tdd`, `file-uploads`,
  `verification-before-completion`.
- `Bambale0/skills`: current `diagnosing-bugs`, `tdd`, and `code-review` workflows.
- `Bambale0/claw`: current `backend-integration`, `kie-seedance`, and
  `release-hardening` guidance.
- `wondelai/skills`: current `release-it` and legacy-code characterization guidance.
- `Bambale0/dev-agents-pack`: API integrator, debugger, test/QA, Python backend, tests and release
  manager guidance.
- `agentskills/agentskills`: progressive-disclosure format guidance; no Seedance-specific rule.
- `anthropics/skills`: current catalog inspected; no applicable backend/provider-release skill.

## Progress

- Audit and production reproduction complete. No provider request, wallet write or customer
  notification has occurred yet.
- RED evidence captured independently for the production WebP class, production HEIC+JPEG class,
  wrongly declared admin-upload MIME and transient external download failure.
- GREEN implementation now uses one byte-detected normalizer for owned and external references,
  bounded SSRF-checked streaming, content-addressed atomic transport storage, HEIF decoding,
  EXIF transpose, alpha-safe PNG output and JPEG output otherwise. Already validated image URLs
  are not downloaded a second time during aggregate validation.
- Ordinary generation, trend, repeat, direct admin upload and durable admin submit seams are
  covered. Corrupt JPEG, valid mislabeled JPEG/PNG, dimension/byte contracts, timeout, storage
  cleanup and original-parameter preservation are covered.
- Local focused verification: 60 tests passed; Ruff, compileall, dependency constraint install and
  `pip check` passed. The PostgreSQL debit/idempotency regression is collected locally and awaits
  the repository CI PostgreSQL service; the local machine has no Docker/PostgreSQL test service.
