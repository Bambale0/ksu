# History, likes and subscriptions

This module implements section 2.6 of the supplied product FSM while preserving the current privacy boundary: generation history is private and owner-scoped.

## History removal

Existing generation rows are financial/provider records and are never physically deleted by the user-facing History flow.

The existing endpoint remains authoritative:

```text
DELETE /api/v1/generations/{generation_id}/history
```

It writes `GenerationHistoryState.hidden_at`. The Mini App now asks for explicit confirmation before calling it, then removes the card from the visible History only after a successful server response.

The empty History state includes the product-spec CTA `Создать контент`.

## Generation likes

Social state is separate from generation/provider state:

```text
GET    /api/v1/social/generations/{generation_id}
POST   /api/v1/social/generations/{generation_id}/like
DELETE /api/v1/social/generations/{generation_id}/like
```

Current generation detail and History are owner-only. The social endpoints intentionally preserve the same ownership check instead of making `/generations/{id}` public.

A like is represented by the composite key `(generation_id, user_id)`. PostgreSQL `ON CONFLICT DO NOTHING` makes repeated like requests idempotent. Unlike is also idempotent.

The result screen renders server-authoritative `liked_by_me` and `like_count`; no like state is stored in browser storage.

## Public author profiles

Public profile visibility is explicit opt-in via the existing `user_preferences.profile_discoverable` setting.

Authenticated safe endpoints:

```text
GET /api/v1/social/profiles?username=<exact username>
GET /api/v1/social/profiles/{author_id}
```

For another user, a missing, inactive or non-discoverable profile returns `404` so the API does not reveal whether a private account exists.

Safe public shape contains only:

- internal opaque user UUID;
- display name;
- public Telegram username when discoverable;
- discoverable flag;
- self/subscription state;
- follower count.

It does **not** expose Telegram numeric ID, wallet/balance, language metadata, contact data or provider/payment data.

The owner may read their own safe public-profile shape even when discoverability is disabled so Profile can explain the current privacy state.

## Subscriptions

```text
POST   /api/v1/social/profiles/{author_id}/subscribe
DELETE /api/v1/social/profiles/{author_id}/subscribe
GET    /api/v1/social/subscriptions?limit=50
```

Rules:

- self-subscription is rejected in both API/service logic and with a database check constraint;
- subscribing requires the target to be active and discoverable;
- repeated subscribe/unsubscribe requests are idempotent;
- if an already-followed author later becomes private, the subscriptions list returns a safe `Скрытый профиль` tombstone with no name/username disclosure;
- unsubscribe remains possible for that tombstone, preventing a privacy change from trapping the follower relationship.

Because the product currently has no public content feed, Profile offers an exact `@username` lookup rather than inventing a discoverable global feed. This gives the specified `Профиль автора → Подписаться/Отписаться` flow without publishing private generation history.

## Mini App integration

`app/web/mini_app/social.js` is loaded after the existing generation/history engine.

The legacy `app.js` stays authoritative for generation creation, polling, detail and History rendering. The social module wraps `window.fetch` only to inspect successful generation responses via `Response.clone()` and associate the already-rendered cards/result with their server IDs. The original response object is returned untouched to the legacy caller.

The module then adds:

- Like / Unlike on succeeded result detail;
- explicit History removal confirmation;
- removal buttons on History cards;
- empty History create CTA;
- Profile subscriptions section;
- exact public-author lookup and subscribe/unsubscribe actions.

All social mutations use signed `Telegram.WebApp.initData` in `X-Telegram-Init-Data`. Social truth is not written to `localStorage` or `sessionStorage`.

## Schema

Migration `0008_history_social` adds:

- `generation_likes`;
- `user_subscriptions`;
- indexes for user/author history;
- `subscriber_user_id <> author_user_id` check constraint.

## Follow-up boundary

This epic does not create a public content feed. If a future discovery/feed feature is added, it must define an explicit generation-publication state and a separate safe read endpoint instead of weakening the existing owner-only generation endpoint.
