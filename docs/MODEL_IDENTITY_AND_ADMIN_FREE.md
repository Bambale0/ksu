# Model identity and admin-free billing contract

**Status:** current runtime contract, 2026-08-20.

This document defines two customer-safety invariants that apply across the ROXY Mini App and backend: the model shown to the user must correspond to the provider model actually submitted, and active ROXY administrators do not spend customer-wallet ROX on AI product actions.

## Model identity

A ROXY generation has three deliberately separate identities:

1. `model_id` — stable ROXY product/runtime model ID used by the API and Mini App.
2. customer presentation — title/product/family/version metadata used only for UI grouping and labels.
3. `provider_model` — exact upstream callable model/variant that the worker will submit.

Customer labels never decide provider routing.

At generation creation ROXY snapshots the exact provider model into generation parameters as `_provider_model`. The worker prefers that immutable snapshot. `_kie_model` is retained for compatibility/audit; only historical rows that predate provider snapshots may fall back to the current catalog mapping.

This prevents a queued task from silently changing upstream model if the catalog is edited between quote/create and worker submission.

Veo 3.1 is the special case: the selected `veo_model` variant is the actual provider snapshot. Market-backed generation models snapshot the catalog's exact `kie_model`. Suno/music snapshots the configured Suno model at task creation.

Internal fields beginning with `_` are never sent as provider input. Provider adapters still validate the public payload independently at submission time.

### Current explicitly locked Kling mappings

| ROXY model ID | Provider model |
| --- | --- |
| `kling-2.5-turbo-pro-t2v` | `kling/v2-5-turbo-text-to-video-pro` |
| `kling-2.5-turbo-pro-i2v` | `kling/v2-5-turbo-image-to-video-pro` |
| `kling-avatar-standard` | `kling/ai-avatar-standard` |
| `kling-avatar-pro` | `kling/ai-avatar-pro` |

The current Kie documentation also lists Seedream 5.0 Lite/Pro, Nano Banana 2/2 Lite, GPT Image 2, Grok Imagine video/image routes, Kling 2.5 Turbo Pro, Kling AI Avatar, Kling Motion, Kling 3.0, Seedance 2.0/2.5 and Wan 2.7. Provider documentation remains authoritative for callable schemas; ROXY tests lock the subset it exposes.

## Customer presentation and grouping

`app/services/model_presentation.py` is keyed by exact runtime model ID. It controls only customer-facing titles and grouping.

Kling products are intentionally separated:

- `kling-video` — ordinary Kling video versions;
- `kling-motion` — motion-control products;
- `kling-avatar` — audio-driven avatar products.

The Mini App family picker consumes server `presentation` metadata rather than inferring a product family from a repeated visible label. A new model without an explicit presentation entry remains reachable as a singleton instead of being guessed into another family.

## Active administrators are free

An active administrator is a user with an active `AdminAccount`. For such a user, the **customer wallet cost** is `0.00 ROX` for AI product actions while the retail price is preserved for audit/display.

Covered spend paths:

- normal image/video generations;
- Suno/music generation;
- Prompt Tools (`image_analysis`, `prompt_builder`);
- Batch Generation and failed-item retry;
- Trends, because execution delegates to the normal generation service and trend catalog prices are user-aware;
- Feed remix, because remix execution delegates to the normal generation service.

The generation/task records retain retail metadata and an `admin_free` marker. Zero-cost actions do not create a customer wallet debit. A zero-cost failed task therefore does not manufacture a refund. A zero-cost admin remix also does not award a paid prompt-repeat bonus to the source author.

### What admin-free does *not* bypass

Admin-free is not unlimited provider usage. The following remain active:

- per-user generation/tool rate limits;
- active-generation/concurrency limits;
- provider submission rate limit;
- circuit breaker/provider availability controls;
- schema validation and media limits;
- durable outbox/recovery/terminal-state rules;
- provider-side billing to the ROXY operator account.

The feature changes customer-wallet accounting only.

## API/UI behavior

Signed Mini App requests attach Telegram `initData` to same-origin `/api/v1/*` calls. This lets catalog/quote endpoints resolve whether the current user is an active administrator without making those endpoints inaccessible to unsigned public previews.

For active administrators:

- catalog/quote customer price is zero;
- retail price remains available separately;
- Mini App zero-price badges render as `Бесплатно`;
- `/api/v1/me` exposes the admin billing mode;
- customer wallet/payment copy uses `ROX`, not legacy `кр.` terminology.

Public denomination remains **1 ROX = 1 RUB**.

## Release acceptance

Before merge/release verify:

1. Every exposed runtime model has a non-empty provider ID and customer presentation.
2. The four current Kling mappings above match exactly.
3. A stored `_provider_model` wins over a later catalog mapping change.
4. `_provider_model`, `_kie_model`, `_admin_free`, retail price metadata and every other underscore-prefixed field are absent from the provider input payload.
5. Active admin quote/create is 0 ROX for generation, music, Prompt Tools, Batch/Retry and Trends; Feed remix inherits the same behavior.
6. No wallet debit/refund transaction is created merely to represent a zero-cost admin action.
7. Non-admin quote/debit behavior is unchanged.
8. Resource/rate/provider safety gates remain enabled for administrators.
9. Kling Video, Kling Motion and Kling AI Avatar are not collapsed into one customer family.
10. Mini App shows `Бесплатно` rather than `0 ROX` for active-admin model pricing and shows wallet denomination as ROX.
11. All existing current-provider contract tests, generation reliability tests, Batch Generation tests and Admin Console tests pass.
12. Production is not declared complete until the merged SHA is actually deployed and the Mini App release SHA/health/E2E evidence matches it.
