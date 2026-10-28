# Local media feed publication repair — 2026-10-28

## Audit baseline and incident evidence

- Baseline: `origin/main` at `530fbc4a70a2615cf9ffd2ba5ef7d547019c85b8`.
- Production returned HTTP 409 with `Не удалось сохранить медиа публикации на сервере` for generation `f9dfa630-1031-4d39-bccb-6caac066be0b`.
- The generation succeeded through Neironych. Its ready `MediaAsset` uses the server-local bucket and its 2,265,928-byte JPEG is present on disk; generation and storage are healthy.
- `feed_publication_contract` can reuse existing feed-static URLs or download public HTTPS/object-storage URLs, but it does not copy ready server-local assets into `FeedStaticStorage`. With no preserved provider URL, all publication sources are exhausted and the request fails closed.

## Scope and acceptance

1. A ready server-local `MediaAsset` can be copied into immutable feed-static storage without a network or provider request.
2. Publication rewrites the generation result to the existing `/uploads/feed` contract and retains the original private media file.
3. Missing, invalid, oversized, or unsafe local files still fail closed with the current user-facing error.
4. Object storage, provider fallback, prices, routes, permissions, balances, schemas, and existing publication behavior remain unchanged.

## Verification plan

1. RED: reproduce the 409 path with a real database generation, ready local asset, isolated media root, and isolated feed root.
2. GREEN: add the smallest safe local-file persistence path and route local-bucket assets through it.
3. Run the focused domain/static/local-storage suites, Ruff, compile checks, and inspect the diff.
4. No merge, deployment, production mutation, or paid provider call is authorized by this repair task.

## Release continuation

The user explicitly authorized a full production release on 2026-10-28. The earlier no-merge/no-deploy boundary is superseded. Release still requires rebasing on current `main`, exact-head PR CI and review, protected merge, all six exact-main workflow gates, the standard verified pre-deploy PostgreSQL backup, immutable-image deployment, and public/runtime SHA plus health verification. Do not use a paid generation as smoke evidence.

Guidance: repository `AGENTS.md`; local `.clinerules` systematic debugging, TDD, writing good tests, and verification before completion (`.agents` is absent); remote mandatory repositories were refreshed before editing. `wondelai/skills` clean-code testing and `Bambale0/dev-agents-pack` debugger guidance applied. The other mandatory catalogs had no more specific current workflow for this storage bridge.

## Local verification evidence

- RED: the isolated SQLite-backed regression failed with the production-equivalent `FeedMediaUnavailableError` before implementation.
- GREEN: the same regression passed after the local-source bridge; the copied JPEG bytes match and the private source remains intact.
- `tests/test_feed_domain.py` excluding the environment-dependent MP4 case: **9 passed**.
- `tests/test_feed_static_storage.py` + `tests/test_local_media_storage.py`: **10 passed, 1 skipped** (the skip is the pre-existing ffmpeg-gated MP4 test).
- Targeted Ruff and compileall checks passed. `git diff --check` passed.
- Running all three files together additionally reached the non-skipped domain MP4 case, which failed only because ffmpeg is not installed on this Windows host. Linux CI remains the required MP4 verification environment.

## Exact-head review hardening

PR review at `a5a6abb3d7484e6595fb245838039a532c223e6b` identified three valid release blockers. A production-style absolute signed local URL could attempt self-HTTP before disk fallback; oversized local media was fully copied before the feed limit rejected it; and an unsafe key in a multi-result set could be skipped while publishing the remaining subset. Three RED regressions reproduced those paths. The corrected flow resolves owned local assets before HTTPS fallback, performs a stat precheck plus bounded streaming copy, and fails the entire publication on any unsafe local key. Local verification after the corrections: **10 domain tests passed** with the ffmpeg-only domain case deselected; static/local storage **11 passed, 1 ffmpeg-gated skip**; targeted Ruff, compileall and diff checks passed. A new exact-head Linux CI/review cycle is required before merge.

The exact-head follow-up review at `54ec3862c0228ac3e12315ecd51028c6565c4e92` found two further valid fail-closed requirements: a partially ingested multi-result generation must not publish the ready subset, and feed-volume `OSError` failures must remain the established media-unavailable response instead of HTTP 500. Two RED regressions reproduced both paths. Owned sources are now eligible only when every expected asset exists and is ready; otherwise publication falls back to the complete provider result set. Static, owned and provider persistence all translate storage I/O failures to the existing publication error. Final local verification before the next exact-head cycle: **12 domain tests passed** with the ffmpeg-only case deselected; static/local storage **11 passed, 1 ffmpeg-gated skip**; targeted Ruff, compileall and diff checks passed.
