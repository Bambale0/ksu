# ROXY Home & Catalog content contract

ROXY Home promo slides are server-authoritative. The Mini App never hard-codes commercial promo copy.

## Home promo source

The public endpoint is:

`GET /api/v1/discovery/home`

It reads the currently published CMS document with slug:

`roxy-home-promos`

The existing internal-admin CMS lifecycle is used to create a draft and publish a version. No second promo database or privileged browser endpoint is introduced.

If the CMS document is missing, unpublished or invalid JSON, the server returns the built-in safe ROXY defaults so Home still renders.

## CMS body schema

The CMS document body is JSON:

```json
{
  "slides": [
    {
      "id": "creator-partnership",
      "eyebrow": "Зарабатывай с ROXY",
      "title": "Партнёрская программа",
      "body": "Индивидуальные условия для авторов и каналов.",
      "cta": "Узнать условия",
      "action": {"type": "route", "target": "profile"},
      "image_url": "https://cdn.example/roxy/creator.webp"
    },
    {
      "id": "trend-week",
      "eyebrow": "В тренде",
      "title": "Попробуй новый шаблон",
      "body": "Готовый сценарий для быстрого старта.",
      "cta": "Открыть тренды",
      "action": {"type": "trends"}
    }
  ]
}
```

Up to 8 slides are accepted.

Supported route targets:

- `home`
- `catalog`
- `create`
- `history`
- `profile`
- `wallet`

`image_url` is optional and must use HTTPS. Invalid actions fall back to `catalog`; invalid image URLs are dropped.

## Catalog product boundary

`Каталог` is a discovery surface, not a renamed Feed. It aggregates:

- curated trend/templates from `/api/v1/trends`;
- a preview of public photo/video community work from `/api/v1/feed`;
- entry to Prompt Tools.

The existing Feed keeps its own publication, moderation, likes/comments/remix and photo/video playback contracts. Catalog only previews and routes into that surface.

## Creator partnership boundary

The Home partnership slide is acquisition/navigation only. Custom creator terms, approvals and monthly ROX grants are implemented by the separate Creator/Influencer partnership epic (#45); they must not be confused with the automatic 30% / 5% referral economy.
