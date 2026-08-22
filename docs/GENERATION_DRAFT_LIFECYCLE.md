# ROXY generation draft lifecycle

Status: production contract for fresh-vs-reuse generation UX.

## New generation

A normal entry into Create is a fresh generation. This includes the central Create action, a media launcher on Studio, and opening a model from Catalog.

The client must initialize the selected model from its current backend `ui_schema` defaults and must not hydrate prompt, references, uploaded files, aspect ratio, resolution or advanced parameters from the previous generation. Draft values are component/session state only; model selection may be remembered for navigation convenience, but generation form contents are not persisted as an implicit future request.

Switching to another concrete model during a new-generation flow also resets that model to its current defaults. This keeps backend schema changes authoritative and prevents stale provider parameters from leaking between model variants.

## Intentional reuse

A successful private history item exposes `Использовать настройки`. This is the only customer flow that intentionally carries settings into a new draft.

The client requests:

```http
GET /api/v1/generations/{generation_id}/recreate
```

and hydrates the returned `model_id`, prompt, compatible parameters, top-level `input_url` and billing seconds into the current backend schema. Scenario selection is inferred from the populated fields and current scenario contract. If the model is no longer available, reuse is rejected instead of silently mapping to another provider model.

Changing the model after reuse exits the copied configuration for that model and initializes the newly selected model from its own defaults.

Public social `Повторить` remains a separate remix action. It starts a new backend generation from a publication and does not masquerade as the private editable-draft flow.

## Generation/result state

The Create form does not own provider task completion. After create succeeds it may show the queued task, but completion is durable backend state. The user may close ROXY immediately. Provider callback/poll reconciliation updates PostgreSQL and the independent notification worker delivers the final result to Telegram.

Telegram `🚀 Открыть в ROXY` uses `/mini-app/?route=history&generation=<id>`. The Mini App resolves that exact owned generation and opens its private preview instead of relying on whichever history item happens to be newest.
