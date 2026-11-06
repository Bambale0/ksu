# Download descriptor expiry follow-up — 2026-11-06

## Pre-edit evidence and scope

PR review thread PRRT_kwDOT1THts60bxX5 reports retained download URLs.
DownloadsPage currently stores generation media descriptors until a list refresh
and passes their download_url directly to a native popup or ordinary anchor.
LocalMediaStorage signs URLs using the existing media_presign_ttl_seconds setting
(default 900); verification rejects an expired capability. S3 descriptors are
also time-limited. A long-open page therefore retains a previously valid but
now unusable download URL.

Existing GET /api/v1/media/{asset_id} already authenticates CurrentUserDep,
checks exact asset ownership and returns fresh id, generation_id, status,
download_url and download_filename. customerRequest sends Telegram authentication
and cache:no-store. No backend or TTL configuration change is needed.

Authorized frontend scope: fetch that descriptor for each explicit download
request; verify both selected IDs, ready status and a nonempty safe HTTP(S) URL/
filename; never fall back to a cached descriptor when refresh fails. Use an
action button instead of an expired href, show per-asset busy/error state,
deduplicate an in-flight request and cancel it when its component disappears.
Keep native cancellation final and synchronous native errors eligible for the
browser attachment fallback. Do not alter preview MIME, expiry or ownership.

Verification planned before source edits: expire a previously rendered capability
on the real loopback HTTPS attachment server, then require a fresh authenticated
descriptor and actual filename/bytes in Chromium and WebKit. Also cover
controlled metadata delay beyond transient activation, native cancellation and
throw, missing/mismatched/unsafe descriptors, HTTP errors and retry, repeated
requests, concurrent clicks and removal during refresh. Existing generation
delivery tests must retain their stale-list protection with the new action UI.

Official reference checked: https://core.telegram.org/bots/webapps#downloadfile
documents the native popup and acceptance callback. The explicit user-interaction
note on that page belongs to openLink. Actual Telegram device behavior remains
separate from browser API-contract tests.

No live customer request, production state change, outgoing message, commit or
push is part of this slice.

## Implementation

DownloadsPage now renders a per-asset DownloadButton. Every explicit request
fetches the existing owner-authorized media descriptor through customerRequest;
the handler accepts only the selected asset/generation IDs, ready status and a
nonempty HTTP(S) URL without embedded credentials plus a nonempty filename.
There is no client TTL, expiry bypass, background polling or stale-URL fallback.

The synchronous request ref deduplicates rapid clicks before React renders the
disabled state. The button displays preparation and a retryable per-asset error.
Removing the asset aborts its request, and controller identity checks suppress
late actions/state writes. A supported native request keeps its existing cancel
semantics. Unsupported/throwing native clients receive the fresh attachment in
the current browsing context, avoiding an asynchronous popup or a large blob
copy in memory. Preview/storage code and the Telegram helper are unchanged.

## Complete test-reference inventory

A whole-content scan of all 352 source files under frontend/mini-app/e2e and tests
(including the API-committed/untracked files in the execution worktree) searched
/mini-app/downloads, Скачать, download_url and link-role selectors. Thirteen
files matched; the complete local inventory is retained with the test artifacts.

| Matched area | Assessment/action |
| --- | --- |
| e2e/media-download.spec.mjs | Updated native/browser download contracts and new expiry/error/concurrency cases. |
| e2e/generation-delivery.spec.mjs | Preserved late-list-response race; replaced obsolete href assertion with a visible action, then actually refreshed/downloaded the selected asset. The provider-result fallback link remains unchanged. |
| e2e/customer-backend-parity.spec.mjs | Downloads page and responsive availability check retained and executed. No fixture mutation required because the scenario does not request a download. |
| e2e/admin-pagination.spec.mjs; e2e/browser-landing.spec.mjs | Unrelated admin/Telegram launch links; unchanged. |
| tests/test_customer_backend_parity.py; tests/test_generation_delivery_ux_contract.py | Source/API capability checks remain compatible; no assertions changed. |
| tests/test_generation_actions.py; tests/test_notification_delivery.py | Bot download labels, outside this page; unchanged. |
| tests/test_kie_upload_resilience.py | Provider upload download_url parsing, outside this page; unchanged. |
| tests/test_local_media_storage.py; tests/test_media_storage.py; tests/test_media_download_contract.py | Server descriptors/signatures/expiry/MIME/ownership contracts; backend unchanged. |

## Verification and freeze

- Initial stale-capability RED: 2 failures, job_346aad72b1b6. This first fixture
  invalidated the retained URL explicitly. The fixture was then tightened to
  model actual expiry rather than only a changed capability identifier.
- Final expiry RED: **2 failed**, job_713578b701ab, against the immutable pre-fix
  build. The old descriptor is initially accepted by a controlled server clock;
  after the clock advances its expires timestamp is in the past. The native
  call used the expired URL, and the real HTTPS browser request returned 404
  without a download. Trace inspection confirmed the 404 URL with expiry
  1793955197. The signature is synthetic; this is a frontend expiry regression,
  not a claim to exercise production HMAC or storage. Existing backend tests
  cover actual signature/expiry authorization.
- Fresh isolated build and TypeScript validation: **GREEN**, 24 static pages,
  job_6890615f959e. The official Playwright 1.56.1 image and existing dependencies
  were used with networking disabled and no production service mounts.
- The first combined run passed all 26 non-error scenarios but found 20 test
  selector failures: a global alert query also selected Next's route announcer.
  Error assertions were scoped to the downloads transaction list. Their message,
  retry and no-stale-action assertions were preserved; product code did not change.
- Final combined browser result: **46 passed, 1.0 minute**, job_1651b7f25abc:
  23 Chromium and 23 mobile WebKit cases. Twenty download cases per engine plus
  three existing downloads compatibility scenarios per engine.
- Real HTTPS attachment tests assert completed downloads, exact filename/bytes,
  no Telegram authentication header on the attachment request and retention of
  the downloads page. Both fallback modes work after a six-second metadata
  response delay. Native error is actually invoked before fallback; native
  cancellation causes no browser request.
- Metadata cases verify authentication and cache:no-store, HTTP 403/404/503,
  missing URL, wrong asset/generation, unready media, rejected javascript/data
  URLs, retry, fresh issuance on each explicit click, a selected asset that is
  not first, duplicate-click deduplication and abort after asset removal.
- Node syntax and git diff --check passed. Parent and engineering independently
  reviewed the source and personally retrieved the final GREEN result.

Changed files (frozen for the parent snapshot):
frontend/mini-app/app/downloads/page.tsx;
frontend/mini-app/e2e/media-download.spec.mjs;
frontend/mini-app/e2e/generation-delivery.spec.mjs;
docs/agents/EXECUTION/downloads-descriptor-expiry-20261106.md.

No backend, configuration, preview MIME, signature or ownership behavior changed.
No production call, outgoing message, commit or push was performed. Native
Telegram behavior is verified through its documented browser API contract;
an actual Telegram-device download remains outside this verification.
