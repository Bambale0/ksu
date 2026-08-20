# History, likes and subscriptions

This module implements the current owner-scoped History/social contract while preserving the privacy boundary: generation history is private and owner-scoped.

## History hide / restore

Generation rows are financial/provider records and are never physically deleted by the user-facing History flow.

Visible History hide remains authoritative through:

```text
DELETE /api/v1/generations/{generation_id}/history
```

It persists `GenerationHistoryState.hidden_at` in PostgreSQL. The Mini App asks for explicit confirmation before calling it and removes the card from visible History only after a successful server response.

Hidden History is also a server-backed product surface rather than browser-only state:

```text
GET /api/v1/generation-history/hidden?limit=<n>
PUT /api/v1/generations/{generation_id}/history
```

`roxy-history-management.js` exposes `История / Скрытые`; `Скрытые` is loaded from the backend every time the management surface opens, so hidden items survive page reload, Telegram WebView restart and another device session. `Вернуть` calls the owner-scoped PUT restore endpoint and clears `hidden_at` instead of recreating the generation.

The empty visible History state includes the product CTA `Создать контент`.

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

Because the product currently has no public content feed generated from private History, Profile offers an exact `@username` lookup rather than weakening the owner-only generation endpoint.

## Mini App integration

`app/web/mini_app/social.js` and `roxy-history-management.js` extend the existing generation/history renderer.

The product adds:

- Like / Unlike on succeeded result detail;
- explicit History hide confirmation;
- persisted `Скрытые` list and `Вернуть` restore;
- empty History create CTA;
- Profile subscriptions section;
- exact public-author lookup and subscribe/unsubscribe actions.

All social/history mutations use signed `Telegram.WebApp.initData` in `X-Telegram-Init-Data`. Hidden/social truth is not stored as the authoritative copy in `localStorage` or `sessionStorage`.

## Schema

Migration `0008_history_social` adds:

- `generation_likes`;
- `user_subscriptions`;
- indexes for user/author history;
- `subscriber_user_id <> author_user_id` check constraint.

`GenerationHistoryState` is the current durable hide/restore state for owner History.

## Release acceptance

- Hide one succeeded generation and reload the Mini App: it must stay absent from visible History.
- Open `Управление → Скрытые`: the same generation must be returned by the backend and displayed.
- Press `Вернуть`, reload again: it must reappear in normal History and disappear from `Скрытые`.
- Another user must not be able to hide/list/restore the owner's generation.
