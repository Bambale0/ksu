# Generation results and history

The generation UX closes the paid user loop from submission to a reusable result.

## Runtime flow

1. `POST /api/v1/generations` creates and charges a durable generation.
2. Mini App immediately renders the queued task and starts authenticated polling.
3. `GET /api/v1/generations/{id}` returns the current authoritative local state.
4. When the Kie callback/reconciliation marks the task terminal, polling updates the same result card.
5. Successful tasks expose all known `result_urls`; failed tasks show the provider error and rely on the server-side idempotent refund path.
6. `GET /api/v1/generations` provides owned cursor-paginated history.

## History contract

`GET /api/v1/generations?limit=20&before=<generation_uuid>&status=<optional>` requires Telegram user authentication.

The response contains only generations owned by the current user and excludes entries the user has hidden from history. Cursor pagination is ordered by `(created_at, id)` descending.

Each item/detail contains:

- generation ID and lifecycle status;
- model identity/title/family/media type;
- prompt;
- allowlisted model settings only;
- billed credits/RUB and billed seconds;
- result URL(s);
- error for failed tasks;
- timestamps.

Provider-private `_...` metadata and unknown provider fields are not returned as selected settings.

## Reuse / variant flow

`GET /api/v1/generations/{id}/recreate` returns a safe reusable request draft. The Mini App restores that draft into the current schema, then requests a fresh server quote before the user can submit it again.

This deliberately does **not** perform a one-click paid retry. Repricing and current-model validation happen before every new wallet debit.

## Soft hide

User-facing history never physically deletes `generations` rows because those rows are connected to wallet accounting, provider reconciliation, refunds and admin audit context.

- `DELETE /api/v1/generations/{id}/history` creates/updates `generation_history_states.hidden_at`.
- `POST /api/v1/generations/{id}/history/restore` clears that flag.

The underlying generation remains available to accounting/admin workflows and can be restored.

## Mini App result actions

The current Mini App supports:

- automatic status polling with backoff;
- image/video result preview;
- open/download via the result URL;
- browser-native share with copy/open fallback;
- history overlay with pagination;
- restore previous model settings through `recreate`.

Telegram Bot API 8.0+ also exposes `WebApp.downloadFile` and media sharing APIs. Product-owned object storage/proxy download endpoints should be introduced before relying on native Telegram file download, because Telegram documents response-header requirements that third-party provider URLs may not satisfy consistently.

## Next dependency

The next epic is durable product-owned object storage. Until that lands, Kie-hosted result URLs remain provider-managed assets and must not be treated as permanent storage.
