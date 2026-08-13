# Versioned onboarding

The product now has one durable onboarding state shared by Telegram bot and Mini App.

## Configuration

```text
ONBOARDING_ENABLED=true
ONBOARDING_VERSION=1
ONBOARDING_TITLE=...
ONBOARDING_BODY=...
ONBOARDING_RULES_URL=
ONBOARDING_PRIVACY_URL=
```

`ONBOARDING_VERSION` is an opaque deployment-controlled string. Changing it makes the current onboarding incomplete again for users who completed an older version. No schema migration is required for a content/version update.

Title, body and optional external links are deployment-owned. The code deliberately does not claim that a button constitutes acceptance of legal terms or store invented legal-consent flags. If the business requires formal consent semantics, the exact legal text/version and evidence requirements must be defined separately.

Only HTTPS rules/privacy URLs are returned to the Mini App. Invalid or non-HTTPS values are omitted.

## Storage

Migration `0009_versioned_onboarding` adds `user_onboarding`:

```text
user_id             PK/FK users.id
completed_version   varchar(64)
completed_at         timestamptz
created_at           timestamptz
updated_at           timestamptz
```

There is one row per user. Completion is idempotent for the current version. A version bump updates the same row.

## User API

Authenticated bootstrap endpoints:

```text
GET  /api/v1/onboarding
POST /api/v1/onboarding/complete
```

The status response contains:

- enabled;
- current version;
- completion state/version/time;
- configured title/body;
- safe optional rules/privacy URLs.

The completion endpoint writes the current configured version and returns fresh server state.

## Server gate

Authenticated user resolution enforces onboarding centrally for new business mutations.

Allowed without current onboarding completion:

- all GET/HEAD/OPTIONS reads;
- DELETE reversal/removal operations;
- onboarding bootstrap/completion;
- `/me` and preferences;
- support;
- notification read-state actions;
- explicit cancel/history-restore recovery actions.

Blocked until current completion include new generation, payment/top-up intent, promo redemption, upload, new subscription/like and new withdrawal requests.

The response is:

```http
428 Precondition Required
```

with:

```json
{
  "detail": {
    "code": "onboarding_required",
    "version": "<current>"
  }
}
```

This central policy prevents a stale Mini App or direct API call from bypassing the gate while still allowing users to cancel/reverse existing actions and contact support after a version bump.

## Telegram bot

`/start` creates/synchronizes the Telegram user as before, then checks the same `OnboardingService` state.

Incomplete users see configured title/body, optional URL buttons and explicit `🚀 Начать`. The callback stores the current onboarding version before showing the normal main menu.

The legacy bot generation callback and an already-active prompt FSM both re-check onboarding. This matters when a user presses an old inline button or the deployment bumps the onboarding version while a prompt flow is already open.

## Mini App

`onboarding.js` is mounted before the other progressive Mini App extensions.

For authenticated Telegram sessions it immediately makes `#appShell` inert and loads server status. Incomplete onboarding is rendered as an accessible modal-style overlay with:

- configured title/body;
- optional explicit rules/privacy buttons;
- `Начать` completion button;
- retry state when status cannot be confirmed.

The links are opened only on a direct user click. The module also observes `428 onboarding_required`; if the version changes while the Mini App is already open, it re-fetches status and restores the gate.

Normal browser/demo mode without signed Telegram `initData` is not falsely treated as an authenticated onboarding session.

No onboarding truth is stored in `localStorage`, `sessionStorage` or `initDataUnsafe`.

## Deployment / CI

The repository `.env.example` enables onboarding. CI sets `ONBOARDING_ENABLED=false` for the pre-existing endpoint regression suite so unrelated tests do not need fake onboarding rows. Dedicated onboarding tests explicitly enable the setting and cover versioning, policy, safe links, bot keyboard and Mini App behavior.
