# KSU incident: Seedance 2.5 legacy MPO reference rejection (2026-10-24)

## Incident, root cause, and scope

Baseline `main` and production image: `2d1987d58e506373c0f114de6151ae88810ac7b0`.

Three Seedance 2.5 jobs in the six-hour incident window failed before any Neironych request ID was assigned with `Seedance image references must be JPEG or PNG`. A read-only inspection of the three original generation inputs found the same product-owned `.jpg` in each: its declared extension was JPEG, but Pillow decoded its bytes as `MPO` (two-frame JPEG/MPF), 6000x4000, 5.15 MB. `inspect_file()` rejected `Image.format == "MPO"` despite the stored media being a JPEG-family source. Independently, converting its primary frame with EXIF orientation into standard JPEG passed the unchanged Seedance 2.5 file validator.

The issue is **not** missing user refs, a Neironych HTTP failure, or a Seedance model outage. The originally uploaded reference library is the source of truth; editing its URL or data would break historical trends and repeats.

## Reuse / design

Existing:
- `ReferenceStaticStorage` holds durable public ROXY URLs and a shared reference volume.
- `NeironychGenerationProviderService._freeze_new_submission()` normalizes the video contract, validates reference files, and freezes an idempotent immutable wire payload before any provider POST.
- `validate_reference_payload()` verifies bytes, dimensions, durations and SSRF guards and **continues to require true JPEG/PNG**.
- KIE transport already caches conversion derivatives for some non-JPEG types, without replacing the original library item.

Missing: a Neironych-specific provider-safe transport representation for legacy product-owned MPOs mislabeled as JPEG. No schema, model, admin, price, user or API change is required; no prefactor needed.

Implementation:
1. Before validation/freeze, inspect locally owned image refs for actual `MPO` format, not extension or MIME.
2. For MPO only, save the first frame as a normal, EXIF-orientation-corrected RGB JPEG to a content-addressed `/uploads/refs/normalized/` URL. Use a file on the same durable reference volume and atomic replace to avoid partial reads. Reuse on later repeats. Enforce the same byte/dimension rules on the derived file.
3. Mutate only the transient provider payload; persisted generation params, trend references and source file remain unchanged. External hostnames are not treated as local media.
4. Keep ordinary JPEG/PNG unchanged and keep WEBP/unknown file rejection until the provider contract supports it. A failed local validation happens before provider spend and follows the existing refund flow. Cache/disk failures are retriable errors rather than silently weakened validation.

Acceptance:
- Original MPO-JPEG failed before fix; a synthetic legacy MPO case at the real adapter submission-snapshot seam now freezes a stable converted JPEG URL. Repeat gives the same URL; original params and bytes are unchanged.
- Ordinary JPEG continues to use the original URL. Dimensions, unsupported formats, URL security and other references stay protected.
- No provider API was charged and no production DB/media rows were modified to implement or test the fix.

## Verification matrix

| Area | Coverage / decision |
| --- | --- |
| Unit/domain | Byte-format and image limits remain covered by `tests/test_neironych_reference_validation.py`. |
| Provider contract | The tests exercise the actual Neironych freeze/snapshot seam with legacy MPO and ordinary JPEG. |
| Idempotency/retries | Repeated generation uses the same content-addressed derived URL; existing snapshot identity unchanged. |
| API/DB/auth | N/A: no HTTP surface, SQL schema, or access boundary changed; all user IDs and original references remain unchanged. Existing CI guards retain coverage. |
| Media security | `owned_path()` rejects external lookalikes and remains the only source for locally normalized images; current URL-guard tests retained. |
| Mini App/bot E2E | No UI or transport event change; existing product CI and a later actual admin test are required for full end-to-end proof. |
| Observability | Current generation ID, provider attempts, safe error strings and request IDs remain; no raw media or signed URLs logged. |
| No-hardcode/admin | Transport format is a provider contract, not a mutable product setting; admin routes/prices are untouched. |
| Performance | One local format probe per image and one conversion per unique MPO content hash. Existing 60-second bounded validation remains, with an independently bounded normalization step. |
| Rollback | Revert this PR/code to disable normalization. Original refs are never changed; cached immutable normalized JPEGs are inert and may remain safely. |
| Deploy | Do not merge/deploy without user authorization and exact-head CI, review, merged-main CI and deploy SHA evidence. |

## Separate incident not hidden by this fix

One other Seedance 2.5 job was first rejected by Nexus HTTP 402 and then failed at Neironych after approximately 30 minutes with upstream message `Video generation timed out before a final result was available.` A subsequent read-only Neironych status check returned `done`, `billed_seconds=15`, and a video. This is a **different** provider-status/reconciliation discrepancy; changing an already-refunded customer task or replaying it is outside this format fix and requires a separate, guarded reconciliation audit. Do not claim it was fixed by MPO normalization.

## Execution evidence

- RED: pre-fix `pytest ... -k seedance_existing_mpo` failed on `ReferenceValidationError: ... JPEG or PNG` at `inspect_file`.
- GREEN: isolated worktree `APP_ENV=test KSU_ALLOW_TEST_DATABASE=1 python -m pytest -q tests/test_neironych_reference_validation.py` → **18 passed**; no production database use.
- Skills: local `code-showcase-systematic-debugging`; remote Bambale0/skills `diagnosing-bugs` and `tdd`; Bambale0/claw architecture/safety, dev-agents-pack debugger/test guidance; wondelai `working-with-legacy-code` seam coverage; agentskills standard (progressive discovery); anthropics catalog inspected, no relevant production backend/video specific skill.

- PR #558 review identified P1: compressed oversize MPO could decode before model limits and exhaust worker memory. Regression first failed in three size/ratio cases before frame decoding; the fix now shares the exact Seedance 2.5 dimensions guard with `inspect_file()` and checks twice before any frame conversion. P2 cache-hit decoding was separately eliminated. Both checks verified against the latest worktree, including an additional Seedance 2.0 MPO safety-bound regression; exact-head CI and security/code review must finish before merge.
