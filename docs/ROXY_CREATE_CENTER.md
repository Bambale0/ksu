# ROXY Create Center

**Status:** synchronized with shipped runtime on 2026-08-20.

The primary `Создать` route is media-first. Users choose the output class before choosing a concrete model.

## Current product flow

```text
Создать
  ├─ Фото  → photo product/model flow → schema builder → quote → generation
  ├─ Видео → video product/model flow → schema builder → quote → generation
  └─ Музыка → dedicated ROXY music surface
```

Photo and Video are separate flows. Selecting Video must stay in the Video flow and must not bounce through the Home screen.

The media flow loads `/api/v1/generations/models`, filters by `media_type`, groups related backend variants into user-facing products where appropriate, and then opens the existing schema-driven builder for the selected concrete model.

The model-selection surface also collapses repeated public model families into one top-level card. A user first sees `Nano Banana`, `Seedream`, `Seedance`, `WAN`, `GPT Image`, etc., and chooses the concrete public version directly inside that card with compact version chips. For example, Nano Banana can expose `Base`, `Pro`, `2`, `2 Lite`; Seedream can expose `3.0`, `4.0`, `4.5`, `5.0 Lite`, `5 Pro`; Seedance versions are handled by the same generic family rule rather than by a separate hardcoded screen.

The family picker is presentation-only: it groups already-rendered product cards by the backend-provided/public family label, remembers the selected version per media type and family, and delegates opening to the original product card. It does not duplicate schema, quote, debit, provider or generation logic. Families with only one product stay visually unchanged. Current short version sets use segmented/chip selection; if a family grows beyond five versions, the chip row becomes horizontally scrollable instead of widening the screen.

WAN 2.7 is present in both media categories: video variants and a dedicated photo generation/edit product (`wan-2.7-image` / Kie `wan/2-7-image`).

## Builder ownership

The Create Center and product-selection layer do not own billing or provider validation. The generic builder remains responsible for:

- model `ui_schema` rendering;
- scenario state;
- references/uploads;
- model-specific parameters;
- fresh server quote;
- generation submission;
- result/history hand-off.

The backend remains authoritative for model availability, validation and price. The client never turns a displayed model card price into a trusted debit amount.

## Navigation

- Create entry opens the media chooser.
- Photo opens only the photo product flow.
- Video opens only the video product flow.
- Back from a model builder owned by the ROXY generation flow returns to the selected Photo/Video product screen.
- Telegram BackButton follows the same nested navigation intent.
- Leaving Create closes the nested flow without duplicating or replacing the global product shell.

## Pricing display

Product cards may show `price_credits`/public ROX metadata from `/api/v1/generations/models`, including `от … ROX/с` for per-second products. This is informative only. The current quote from `POST /api/v1/generations/quote` and the server-side create recalculation are authoritative.

Published Admin Tariffs can change runtime generation prices without redeploying this screen; therefore the Create Center must always consume current backend data.

## Prompt helper

The builder can use the existing paid prompt-builder lifecycle for prompt improvement and prompt-from-reference tasks. It keeps normal idempotency, wallet debit/refund and task processing rules and cannot override generation pricing.

## Music boundary

Music has its own ROXY music generation surface and must not be faked through image/video model IDs. Audio provider/schema/pricing/history behavior remains owned by that dedicated domain.

## Regression expectations

Tests must protect at least these customer contracts:

- media-first Create entry;
- independent Photo/Video routing;
- no `home` hop in `chooseMedia` for Video;
- model list filtered by backend media type;
- repeated public families collapse into one top-level card while preserving every concrete product as an inline version choice;
- a family-version change updates the displayed selected product and is remembered independently for Photo/Video;
- version chips remain keyboard/focus accessible and keep at least a 44 px mobile touch target;
- the family-presentation layer delegates to the original product and never owns quote/debit/provider submission;
- server schema builder reuse rather than a second generation implementation;
- builder Back returns to the active media flow;
- WAN 2.7 photo appears only when its backend image model is available.
