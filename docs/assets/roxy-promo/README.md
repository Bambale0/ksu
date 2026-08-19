# ROXY promo slide assets

These files mirror the current runtime binaries used by the ROXY home carousel.

## Files

```text
partner-referrals-runtime.webp
creator-rewards-runtime.webp
```

Runtime counterparts:

```text
app/web/mini_app/roxy-partner-referrals-slide-source.webp
app/web/mini_app/roxy-creator-rewards-slide-source.webp
```

## Approved source compositions

Partner/referrals master:

- supplied master size: 1536×857;
- RX / ROXY branding;
- laptop/dashboard composition;
- headline: `ДО 35% С ПОПОЛНЕНИЙ РЕФЕРАЛОВ`;
- supporting copy: `Твой трафик. Твой доход. ROXY.`;
- CTA: `СТАТЬ ПАРТНЁРОМ`.

Creator/rewards master:

- supplied master size: 1536×864;
- social/creator card composition;
- headline: `СОЗДАВАЙ. ПУБЛИКУЙ. ЗАРАБАТЫВАЙ.`;
- supporting copy: `Получай лайки и ROX за каждый повтор твоих работ.`.

## Handling policy

The supplied slides are approved final artwork. Do not:

- generate a visually similar replacement;
- redraw them as a new SVG;
- change text/font/layout/colors/objects;
- crop them to fill a container;
- apply browser filters or transforms that alter the artwork.

A quality upgrade must start from the exact supplied master and preserve composition/content. Deterministic resampling/encoding is acceptable; generative reconstruction is not.

The runtime carousel should use `object-fit: contain` so the full approved frame remains visible.

## Source integrity notes

Original uploaded JPEG master fingerprints recorded during implementation:

```text
partner: sha256 04c634ac8da45d36cb0b16e2225f15b9a88797aafe0a6000d2d5b2779496a94b
creator: sha256 ec66a711f5cd860bc265a64b59dd67ab32ac2e9962190f40d10f38a22aded1dd
```

These hashes identify the supplied source files used for visual approval. The packaged WebP mirrors have different hashes because they are encoded runtime copies.
