# ROXY Public Landing — independent marketing website

**Canonical origin:** `https://ksuapi.xn--e1aikcel5c5a.online/` (the hostname is configured at the reverse proxy).

## Strict ownership and routes

- `GET /` and `HEAD /` serve `app/web/site/index.html` directly from FastAPI.
- `/site-assets/*` serves independent `app/web/site/assets/` files (CSS and WebP).
- `/landing` and `/landing/*` are removed (404), including old redirect HTML/CSS.
- `/mini-app/*` continues to use the **existing** Next.js static export; **no Mini App source, styles, auth, providers or builds are changed by this website PR**.
- The only intentional connection to the app is an ordinary link to `/mini-app/`. Its URL preserves whitelisted referral query parameters `startapp`, `start_payload` and `ref` when users click. The website does not import app JavaScript or use the app authentication.
- Keep runtime billing, wallet, webhook and admin unchanged.

## Visual system

- Dark full-bleed asymmetric media mosaic and lilac chrome `R` in the hero.
- Independent static content: hero, tools, creative process, visual gallery, FAQ, final CTA, footer.
- Images are design-only AI-generated concepts and **not** actual customer results or public trend footage. The `3840×2160` canvas is upscaled from generated source imagery; it is not a native 4K generation.
- Assets `site-assets/atlas-1920.webp` and `site-assets/atlas-3840.webp` use CSS `image-set` so retina displays can choose higher density.
- No external CDN, third-party fonts, autoplay or obligatory WebGL. Mobile menu uses native HTML details/summary.
- Must keep keyboard navigation, focus indicators, reduced motion, no horizontal overflow, and legible mobile typography.

## Deployment verification

- Run `pytest -q tests/test_public_site.py` and the full required KSU gates, release by exact commit SHA.
- Verify `/` returns HTTP 200 HTML with ROXY marketing, `/site-assets/styles.css` and both WebP assets return 200, and `/landing/` returns 404.
- Check `/mini-app/` and `/mini-app/release.json` remain available **without redirecting to the public site**.
- Check desktop and 320/390/768px mobile, CTA/referral link, and browser console before declaring production release.
