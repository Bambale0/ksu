# Feed domain

**Status:** current runtime contract on **2026-08-27**.

The feed is a public presentation and interaction domain over the existing `Generation` aggregate. It is not a second generation/task system.

## Current Mini App surface

`Лента` is a full-screen TikTok-style vertical `scroll-snap` surface. The current customer experience includes:

- `Для вас` and `Подписки` tabs;
- autoplay/pause behavior for visible video cards;
- likes and unlike;
- comments;
- Telegram share;
- author/profile navigation;
- server-owned Repeat/remix actions;
- details/actions sheet without exposing hidden source data.

The older Pinterest/grid feed is not the production feed contract.

## Mapping from the existing KSU model

| Feed concept | KSU source of truth |
| --- | --- |
| post / task | `Generation` UUID |
| author | `Generation.user_id -> User` |
| public author/referral identity | existing Telegram/user referral identity |
| profile | `User` + profile/social services |
| output media | ready product-owned `MediaAsset` where available |
| private history state | `GenerationHistoryState`; independent from publication |
| likes | `GenerationLike` |
| moderation blur/remove | `GenerationModerationState` |
| comments | `FeedComment`, explicitly scoped to `feed` or `profile` |
| derivative/remix ledger | `FeedRemixEvent` + generation lineage |

## Publication state

`Generation.publication_scope` is the semantic source of truth:

- `private`: not published;
- `profile`: visible on the author profile only;
- `feed`: visible on the author profile and eligible for public discovery.

`is_public_feed` and `is_profile_visible` are query projections kept consistent by the feed service. Public discovery and profile discovery are separate queries; profile-only publication must not depend on public feed membership.

After a successful feed publication the Mini App offers sharing immediately.

## Hidden prompt vs Repeat

Prompt visibility and repeatability are separate contracts.

For an ordinary public source generation:

- the feed DTO may return `prompt: ""` because the author has hidden the prompt;
- `prompt_actions_allowed` can still be true;
- another user may receive **Повторить**;
- the server restores the original prompt and safe settings internally;
- the source prompt is never sent to or accepted back from the repeating client.

Therefore **hidden prompt does not imply disabled Repeat**. Tests must verify that a foreign user's hidden-prompt publication can be repeated without the prompt appearing in the public DTO/UI.

Curated trends and restricted derivative records use stricter rules and may deliberately return `prompt_actions_allowed=false`.

## Derivatives / remix

A remix/derivative carries lineage (`source_feed_gen_id`, `parent_generation_id`, action type). The server owns source prompt/settings restoration and does not accept a source prompt from the browser.

Restricted derivatives cannot be republished as if they were an unrelated original source. Their feed/profile DTOs continue to protect prompt/reference data according to the derivative policy.

## Surface authorization

Every interaction receives or derives a surface:

- `feed`: the item must currently be a valid public-feed publication;
- `profile`: the item must currently be profile-visible (`feed` or `profile` scope).

Like, unlike, share, comment and repeat/remix revalidate access on the server. A UUID alone is not authorization.

## Sorting

- `recent`: `feed_published_at DESC`;
- `top_day`: 24-hour window, then score;
- `top`: global score.

Current score remains derived from engagement (`likes`, weighted shares and remixes) by the feed service. Clients do not calculate ranking truth.

## Share/deep-link contract

A publication share endpoint returns a usable Telegram link for the specific work. Link generation follows the shared Mini App link contract:

1. use a Telegram Direct Mini App `startapp` link only when a real BotFather Mini App short name is configured;
2. otherwise fall back to a bot start link carrying the same payload, for example `https://t.me/<bot>?start=feed_<id>...`;
3. never synthesize a default `/app` short name.

This fallback also applies to profile/referral links. The Mini App share action opens Telegram share when available and uses a WebView-safe copy fallback when needed.

Legacy payload families remain supported as required by existing links, including feed/post/profile/remix payloads. Deep-link resolution must always preserve authorization and hidden-prompt rules.

## Media

New publication paths prefer product-owned durable media. Cards use product-owned view URLs where available; historical provider HTTPS URLs may remain a compatibility fallback for legacy records while migration/repair tooling localizes usable media.

## Compatibility boundaries

- private history hiding does not unpublish a work;
- existing owner-only history/social endpoints are retained;
- feed APIs are surface-aware;
- likes stay idempotent;
- share counting is intentionally an accepted-action counter rather than an idempotent like state;
- prompt hiding must not accidentally disable legitimate cross-user Repeat;
- a share link must not depend on a configured Direct Mini App short name.

## Known compromises

1. **Author photo:** the current user/profile schema does not require an authoritative durable Telegram avatar; a card may return no photo rather than invent one.
2. **Historical input references:** older generation inputs may still contain URL-form references. Server-side repeat/remix restores safe values, while current reusable-reference/media paths are moving toward product ownership.
3. **Preview/thumbnail:** there is no independent thumbnail pipeline for every historical record; the first usable result/view may serve as preview.
4. **Comment anti-spam:** comments are normalized/length-limited/surface-authorized; resource controls remain server-owned.
5. **Adult classification:** public feed eligibility respects existing moderation/adult flags; this domain does not invent a separate classifier.

## Release acceptance

The system-risk browser matrix explicitly covers foreign-user hidden-prompt Repeat, sharing, like/unlike, comments, subscription tab behavior and prompt non-disclosure across five viewport classes. Mobile WebKit remains a separate required responsive audit.
