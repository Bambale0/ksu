# Feed domain

## Mapping from the existing KSU model

The feed is a public presentation and interaction domain over the existing `Generation` aggregate. It is not a second generation/task system.

| Feed concept | KSU source of truth |
| --- | --- |
| post / task | `Generation` UUID |
| author | `Generation.user_id -> User` |
| public author/referral code | existing `User.telegram_id` (`ref_<telegram_id>`) |
| profile | `User` + existing profile/social services |
| output media | ready `MediaAsset` owned by KSU |
| private history state | `GenerationHistoryState`; independent from publication |
| likes | existing `GenerationLike` composite primary key |
| moderation blur/remove | existing `GenerationModerationState` |
| comments | `FeedComment`, explicitly scoped to `feed` or `profile` |
| derivative/remix ledger | `FeedRemixEvent` + lineage on `Generation` |

## Publication state

`Generation.publication_scope` is the semantic source of truth:

- `private`: not published;
- `profile`: visible on the author profile only;
- `feed`: visible on the author profile and eligible for public discovery.

`is_public_feed` and `is_profile_visible` are query projections kept consistent by the feed service.

Public discovery and profile discovery are deliberately separate repository queries. Profile queries never filter only by `is_public_feed`.

## Derivatives

A derivative has `source_feed_gen_id != NULL`.

- it cannot be published back to the public feed;
- the prompt-library publication guard rejects it;
- its feed/profile card always returns an empty `prompt`;
- reference arrays are empty;
- `prompt_actions_allowed` is false;
- remix restores the source prompt and safe model parameters server-side, then creates a new `Generation` with `source_feed_gen_id`, `parent_generation_id` and `action_type=remix`.

The source prompt is never accepted from the client during remix.

## Surface authorization

Every interaction receives or derives a surface:

- `feed`: the item must currently be a valid public-feed publication;
- `profile`: the item must currently be profile-visible (`feed` or `profile` scope).

Like, unlike, share, comment and remix revalidate this on the server. A UUID alone does not grant access.

## Sorting

- `recent`: `feed_published_at DESC`;
- `top_day`: 24-hour window, then score;
- `top`: global score.

Current score:

`likes + shares * 5 + remixes * 7`

## Deep links

The existing Telegram ID referral code is reused:

- `feed_<generation_uuid>_ref_<telegram_id>`;
- `posts_<telegram_id>_ref_<telegram_id>`;
- `remix_<generation_uuid>_ref_<telegram_id>`.

A post deep link tries the public card first and then the profile card, so profile-only posts do not depend on public discovery. `remix_*` executes the server-side remix flow instead of only rendering a preview.

## Media

Publication requires at least one ready KSU-owned `MediaAsset`. Cards prefer product-owned presigned media. A provider HTTPS result URL is retained only as a legacy delivery fallback when object-storage delivery cannot be constructed.

## Compatibility boundaries

- private history hiding does not unpublish a work;
- the existing owner-only history/social endpoints are retained;
- feed APIs are separate and surface-aware;
- existing `GenerationLike` is reused instead of creating `feed_generation_likes`.

## Known compromises

1. **Referral code:** KSU has no separate stable public referral-code column. Feed deep links reuse the existing `User.telegram_id` referral code so there is one referral identity system.
2. **Author photo:** the current user/profile schema has no authoritative avatar URL, therefore feed cards return `author_photo_url: null` rather than inventing or caching Telegram profile photos.
3. **Input references:** output media is durably owned by KSU, but historical input references are still stored as generation URLs/parameters. Remix restores them server-side, yet a future input-media ingest layer would improve long-term reproducibility.
4. **Preview/thumbnail:** no separate thumbnail pipeline is introduced in this port; `preview_url` is currently the first ready result view.
5. **Share counting:** shares are an explicit counter and are intentionally not idempotent; each accepted share action increments it. Likes remain idempotent.
6. **Comment anti-spam:** comments are whitespace-normalized, length-limited, HTML-escaped and surface-authorized. A dedicated per-user comment rate limiter is not introduced in this slice.
7. **Adult classification:** the feed enforces `is_adult_content` by preventing public discovery (a feed publish request is downgraded to profile), but this port does not introduce a new NSFW classifier. The flag must be set by the existing/future moderation pipeline.
8. **Prompt library:** KSU currently has an admin prompt-library/moderation contour but no user-facing "publish this generation as prompt" write path. The derivative guard exists in the shared feed domain and is tested; any future prompt publisher must call it before persistence.
