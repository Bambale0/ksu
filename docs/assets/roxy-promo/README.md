# ROXY promo slide assets

These files mirror the current runtime binaries used by the ROXY home carousel.

## Files

```text
partner-referrals-runtime.png
creator-rewards-runtime.png
```

Runtime counterparts:

```text
app/web/mini_app/roxy-partner-referrals-slide-source.png
app/web/mini_app/roxy-creator-rewards-slide-source.png
```

## Approved source compositions

Partner/referrals master:

- supplied master size: 1672×941;
- RX / ROXY branding;
- laptop/dashboard composition;
- headline: `ДО 35% С ПОПОЛНЕНИЙ РЕФЕРАЛОВ`;
- supporting copy: `Твой трафик. Твой доход. ROXY.`;
- CTA: `СТАТЬ ПАРТНЁРОМ`.

Creator/rewards master:

- supplied master size: 1672×941;
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

Original uploaded PNG master fingerprints recorded during implementation:

```text
partner: sha256 8c03e745ef79d9b1d01f9a82c2426e61c723384c54c7e464bdec8189deaa501f
creator: sha256 8a1869f857cdb7379accd8acbb7417ae100fd4e2413b397cc5defae43b44e434
```

These hashes identify the supplied source files used for visual approval. The packaged runtime PNG mirrors are byte-for-byte copies of those approved assets.
