# ROXY post-generation actions

**Status:** production contract for the Lena-style derivative workflow.

A completed generation is not a dead end. ROXY treats the result as a server-owned starting point for an explicit next action while keeping ordinary **Create** fresh and empty by default.

## Product contract

### Image results

A successful image may expose:

- `✨ Ремикс` — use the completed image as the source and ask what should change;
- `🔁 Ещё вариант` — restore the owned prompt plus compatible settings and let the user adjust them before a new run;
- `💅 Изменить образ` — focused edit presets plus a free-text instruction; the generated result is the source image;
- `🎬 Оживить` — use the completed image as an I2V source and open compatible video settings;
- `📤 Опубликовать` — open publication controls for that exact generation;
- `📥 Скачать оригинал` — direct result URL utility;
- `🚀 Открыть в ROXY` — open the exact generation in History.

### Video and audio results

Successful video/audio results expose only the general actions supported by the server catalog:

- another variant;
- new prompt;
- change parameters;
- publish;
- original/open utilities.

Image-only actions are never rendered for video/audio.

## Deep-link contract

Telegram generation actions use WebApp links scoped to both the generation and the action:

```text
/mini-app/?route=generation-action&generation=<generation_id>&action=<action>
```

The browser must not infer action state from local storage. The Mini App resolves the link against the authenticated backend action context.

## Backend API

```http
GET  /api/v1/generations/{id}/actions
GET  /api/v1/generations/{id}/action-context?action=<action>
POST /api/v1/generations/{id}/actions/{action}
```

The server is authoritative for:

- ownership;
- whether the parent is in a valid terminal state;
- available action matrix;
- compatible model candidates;
- safe reusable parameters;
- source media;
- parent lineage;
- provider routing;
- quote/debit;
- generation reliability/outbox behavior.

Unsupported actions return a conflict response and the Mini App renders a safe fallback instead of trying to improvise a workflow.

## Lineage

Every derivative generation persists:

```text
parent_generation_id = source Generation.id
action_type = normalized derivative action
```

Normalized lineage values are:

- `remix`;
- `repeat` — also used for the UI variants `new_prompt` and `parameters`;
- `edit`;
- `animate`.

Publication is not a derivative generation and does not create a child row.

## Fresh Create boundary

Ordinary Create remains separate from derivative workflows.

Opening Catalog/Create must start from the current `ui_schema.defaults` and must not silently reuse:

- the previous prompt;
- previous references;
- previous model parameters;
- a completed generation result.

Reuse happens only after an explicit user action such as Repeat/Remix/Edit/Animate or the existing owned `Использовать настройки` flow.

## Remix and edit source semantics

Remix/Edit use the **completed result** as the explicit source image. The source result is not copied into the normal fresh draft.

Edit converts the user's focused instruction into a preservation-oriented provider prompt: the selected focus may change while identity/composition/lighting/unrelated details should stay unchanged unless that focus itself is being edited.

Current focused edit presets include clothes, hairstyle, hair color, nails, background, style, details and custom.

## Repeat semantics

Repeat is not Remix.

Repeat restores the owned prompt and only parameters compatible with the selected target model. The user can then change model/settings/references before starting another run.

When the UI action is `new_prompt`, settings may be retained but the prompt field starts empty. When the UI action is `parameters`, the previous prompt remains while settings are editable. Both persist `action_type=repeat`.

## Animate semantics

Animate accepts an image result only and selects from video models whose current catalog operation can consume an image source. ROXY prefers `grok-video-i2v` when that model is available, matching the proven Lena flow, but the candidate list itself remains catalog-driven.

## Seedance derivative safety

Post-generation reference adaptation must preserve the current Seedance contracts fixed in #225.

- Seedance 2.5 reference arrays must **not** also be converted into `first_frame_url`; frame mode and multimodal-reference mode remain mutually exclusive.
- Seedance 2.0 / Fast / Mini may preserve valid hybrid first/last-frame + multimodal reference control.
- A generic result/input URL becomes a frame source only when the exact Seedance media fields do not already define the mode.

If a derivative Seedance request disappears before a Kie task is created, inspect action reference adaptation first, then the normal Seedance provider-normalization path.

## Privacy

All generation-action endpoints are owner-scoped.

Admin trend/template recipes have stronger secrecy:

- hidden prompt is never returned in action context;
- original recipe references are never returned in action context;
- Repeat/New prompt/Parameters are unavailable because they could reconstruct the recipe;
- Remix/Edit/Animate may use only the rendered result as their new visual source;
- publication keeps the existing server-side trend secrecy rules.

Public feed remix remains a separate server-side workflow. Hidden source prompts are not sent to the browser simply because a public work can be repeated.

## Telegram delivery and idempotency

The existing durable notification outbox remains authoritative. Adding action buttons does not create a second delivery path.

Successful media delivery attaches server-computed action buttons to the same completion notification. If Telegram cannot fetch/decode the provider media URL, the worker falls back to a text completion notification with the same valid utilities/actions.

Failed generations do not expose derivative actions; the user still receives the existing error/refund recovery message and an Open in ROXY utility when available.

## Mini App quote/submit

The derivative screen requests a fresh authoritative quote before enabling submit. The backend prices again when creating the child generation. A browser quote is never a trusted debit token.

Reference memory stays server-backed through `/api/v1/references` and `/api/v1/uploads/kie`; the action page does not rely on local-storage-only media state.

## Troubleshooting

### Button is missing

Check in order:

1. parent generation is `succeeded` and has a usable result URL;
2. media type is correct;
3. action is allowed for trend/template privacy state;
4. `GenerationActionService.public_candidates()` has at least one executable current model;
5. `PUBLIC_BASE_URL` is configured so Telegram can build WebApp links.

Do not hardcode a button in Telegram to bypass a missing backend capability.

### Action opens but submit returns 409

The parent may no longer be owned/available, the action may be privacy-forbidden, or the generation may not be in a valid completed state. Re-fetch `action-context`; do not reuse stale browser action state.

### Quote works but submit returns 422

Compare the final target model, `ui_schema`, and exact derivative reference adaptation. For Seedance specifically, verify that 2.5 is not receiving both frame and reference modes.

### Hidden trend recipe appears in browser payload

Treat this as a security/privacy regression. `prompt`, `source_references` and any reusable recipe parameters must remain absent/empty for hidden trend/template context. The rendered result URL itself may be returned for Remix/Edit/Animate.

## Release acceptance

Before merge/deploy:

- backend action matrix tests pass for image/video/audio;
- ownership/privacy/lineage tests pass;
- Seedance derivative routing tests pass together with #225 provider transport tests;
- Playwright covers Remix, Repeat, Edit, Animate, Publish and unsupported-action fallback;
- ordinary fresh Create regression remains green;
- durable notification/idempotency tests remain green;
- the existing Mini App scenario suite is not reduced to make CI pass.
