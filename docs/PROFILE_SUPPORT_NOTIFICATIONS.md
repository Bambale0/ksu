# Profile, notifications and support

This document defines the user-facing Profile-side flows implemented in the Telegram Mini App.

## Identity boundary

Telegram identity is server-authenticated and read-only in the product UI:

- `telegram_id`
- `username`
- `first_name`
- `last_name`
- Telegram language metadata

Those values are synchronized from Telegram authentication and are not stored as editable application profile fields. The Mini App therefore does not present fake local edits that would be overwritten on the next authenticated Telegram session.

Application-owned preferences are stored separately in `user_preferences`:

- `ui_language`: `auto`, `ru`, `en`
- `notifications_enabled`
- `marketing_notifications`
- `profile_discoverable`

API:

```text
GET /api/v1/me/preferences
PUT /api/v1/me/preferences
```

The backend validates the language allow-list. Browser storage is not an authority for any preference.

## Notification inbox

Authenticated endpoints:

```text
GET  /api/v1/notifications?limit=50
POST /api/v1/notifications/{notification_id}/read
POST /api/v1/notifications/read-all
```

Every query and mutation is scoped to the authenticated user. The Mini App renders the server unread count both in the notification section and as a compact Profile navigation badge.

Read state is persisted only on the backend. A reload or another Telegram client therefore receives the same authoritative state.

Disabling notifications is a delivery preference; it does not destroy the existing inbox history.

## Support lifecycle

Authenticated endpoints:

```text
POST /api/v1/support/tickets
GET  /api/v1/support/tickets?limit=50
GET  /api/v1/support/tickets/{ticket_id}
POST /api/v1/support/tickets/{ticket_id}/messages
POST /api/v1/support/tickets/{ticket_id}/close
POST /api/v1/support/tickets/{ticket_id}/reopen
```

All ticket reads and mutations require both ticket ID and authenticated owner ID.

User-visible state machine:

```text
open ---------> in_progress
 |                  |
 | reply            | reply
 | close            | close
 v                  v
closed <---------- active
  ^
  |
  | reopen
  |
resolved
```

More precisely:

- `open`, `in_progress`: user may reply and close;
- `resolved`, `closed`: user may reopen;
- reopening returns the ticket to `open`.

This deliberately matches the existing admin workflow where the first support reply may move a ticket from `open` to `in_progress`. User replies must remain possible after that admin transition.

The detail endpoint returns the complete ordered message thread with author reduced to `user` or `support`; internal admin identity is not exposed.

## Mini App placement

Preferences, notifications and support are mounted inside the existing `Profile` top-level view. They do not add another bottom-navigation destination.

Files:

```text
app/web/mini_app/profile-tools.js
app/web/mini_app/profile-tools.css
app/web/mini_app/shell-integration.js
```

The module:

- sends raw signed `Telegram.WebApp.initData` only through `X-Telegram-Init-Data`;
- never authenticates with `initDataUnsafe`;
- does not persist ticket, notification or preference truth to `localStorage` / `sessionStorage`;
- includes explicit Telegram-context, loading, empty and error states;
- refreshes visible Profile data after Telegram activation / network restoration.

## Database migration

`0007_user_preferences` adds the application-owned preference record keyed 1:1 by `users.id` with `ON DELETE CASCADE`.

Notifications and support continue to use the existing `notifications`, `support_tickets` and `support_messages` tables.

## CI contract

The main CI pipeline validates `profile-tools.js` with Node syntax checking, applies the full Alembic migration chain to PostgreSQL, and executes regression tests covering:

- preference validation and durability;
- notification ownership and read state;
- support ownership;
- the `in_progress` reply regression;
- close/reopen transitions;
- signed Telegram authentication and absence of browser business-state persistence.
