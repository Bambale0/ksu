# ROXY Public Landing — independent marketing website

**Canonical origin:** `https://ksuapi.xn--e1aikcel5c5a.online/` (the hostname is configured at the reverse proxy).

## Strict ownership and routes

- `GET /` and `HEAD /` serve `app/web/site/index.html` directly from FastAPI.
- `/site-assets/*` serves independent `app/web/site/assets/` files (CSS and WebP).
- `/landing` and `/landing/*` are removed (404), including old redirect HTML/CSS.
- `/mini-app/*` continues to use the **existing** Next.js static export; **no Mini App source, styles, auth, providers or builds are changed by this website PR**.
- The only intentional connection to the app is an ordinary link to `/mini-app/`. Its URL preserves whitelisted referral query parameters `startapp`, `start_payload` and `ref` when users click. The website does not import app JavaScript or use the app authentication.
- Keep runtime billing, wallet, webhook and admin unchanged.

## Visual system — editorial revision

The public-facing brand is **ROXY AI STUDIO**. The first screen retains the dark media mosaic and chrome-lilac R; the page below it uses visual editorial pacing rather than repeated SaaS cards. Design intent: an art-directed creative studio / visual culture journal, not a generic AI-template landing.

- The capabilities section is an intentionally asymmetric split between a photographic editorial spread and a typographic feature list. Its imagery is **moodboard content**, not a before/after promise.
- The process is three horizontally ruled editorial lines, rather than feature-card clones.
- The gallery is a **live read-only projection of active curated trends** sorted by the existing `admin_trends.payload.usage_count`. No static illustrative content, fake filters or hardcoded trending IDs are shown.
- FAQ uses native details/summary; final CTA is an open editorial treatment without purple gradient callout-card framing.
- The desktop header switches to a functioning `details` mobile/tablet navigation at `1000px`, including the 661–1000px range that formerly had no navigation.
- Only standalone `app/web/site/index.html` and `app/web/site/assets/styles.css` are modified. The Mini App remains an independent destination.

### Visual QA checklist

Compare at viewport widths 320, 390, 768, 1024 and 1440px. Confirm no horizontal overflow, header menu remains reachable, visible text does not overlap images, headings keep an intelligible hierarchy, and each CTA carries the `startapp`, `start_payload` and `ref` query parameters where present. Validate both keyboard focus and reduced motion.


- Images are design-only AI-generated concepts and **not** actual customer results or public trend footage. The `3840×2160` canvas is upscaled from generated source imagery; it is not a native 4K generation.
- Assets `site-assets/atlas-1920.webp` and `site-assets/atlas-3840.webp` use CSS `image-set` so retina displays can choose higher density.
- No external CDN, third-party fonts, autoplay or obligatory WebGL. Mobile menu uses native HTML details/summary.
- Must keep keyboard navigation, focus indicators, reduced motion, no horizontal overflow, and legible mobile typography.

## Deployment verification

- Run `pytest -q tests/test_public_site.py` and the full required KSU gates, release by exact commit SHA.
- Verify `/` returns HTTP 200 HTML with ROXY marketing, `/site-assets/styles.css` and both WebP assets return 200, and `/landing/` returns 404.
- Check `/mini-app/` and `/mini-app/release.json` remain available **without redirecting to the public site**.
- Check desktop and 320/390/768px mobile, CTA/referral link, and browser console before declaring production release.


## Live popularity gallery (2026-11-23)

The independent landing uses `app/web/site/assets/popular-trends.js`, not any code from `frontend/mini-app/`.

- `GET /api/v1/public-site/popular-trends?limit=6` is an anonymous **read-only** FastAPI endpoint in `app/api/v1/public_site.py`.
- Reads only active `admin_trends` with safe, public HTTP(S) preview media; reuses `TrendService.public_view` to reject obsolete/invalid model recipes. It emits **only** `id,title,media_type,preview_kind,preview_url,poster_url,usage_count` rather than private prompts, provider parameters or wallet information.
- Ranking is by descending `usage_count`, then newest creation time. KSU increments this counter on trend runs (including workflows), but **administrators can also edit it**; it is an existing product counter, not independently verified analytics or a last-24-hours leaderboard.
- Cache: Redis 90 seconds (best effort), HTTP cache 30 seconds. Admin activation/deactivation and popularity changes therefore become visible after TTL; there are no hardcoded trending IDs.
- Video clips play muted, inline, looped and **only while visible**. Offscreen and page-hidden clips pause. Respect `prefers-reduced-motion` and Save-Data. Images use native lazy loading. Remote video formats are detected from the public preview filename/URL rather than presuming every video trend has a playable motion clip.
- Each tile navigates to the existing `/mini-app/trend/?id=<uuid>` (not a new Mini App feature), preserving allowed referral query keys. If the app is unauthenticated, its existing sign-in flow takes over.
- Empty/error states explain what happened; retry is explicit. No private generations or customer posts are returned by this endpoint.
- `tests/test_public_site_popular_trends.py` covers ranking, safe URLs, data minimization, anonymous access and cache; `tests/test_public_site.py` enforces JS/gallery contract. Browser QA covers desktop/mobile cards, video pause/autoplay and retry.

The /mini-app source tree, its own trend catalog, billing and user sessions are not modified by this feature.


## Visual polish (2026-11-23)

The public website remains a dependency-free FastAPI-served HTML/CSS/JS site. We deliberately **did not install React, Radix, Tailwind or shadcn/ui** because they belong to the component architecture of a React application, whereas this independent landing already uses native HTML controls and no frontend build.

- Applied the interaction/keyboard/hover principles demonstrated by shadcn/ui (readable button sizes, visible focus, truly interactive controls only) without adding a JavaScript framework.
- Followed the `anthropics/skills/frontend-design` guidance: less tracked uppercase metadata, fewer ornamental accents, simpler copy, typographic hierarchy and one distinctive hero rather than repeated template chrome.
- Rebalanced the six living trend tiles: desktop two editorial rows; tablet/mobile a two-column rhythm with featured first and last cards. No sixth card stretched 100% of a desktop row.
- Trimmed the oversized section headings and decorative footer glow; preserved the existing ROXY hero art direction.
- Removed decorative arrows from nonclickable feature and process descriptions, retaining the actual navigation links and step semantics. Fixed the FAQ answer to correctly confirm that beginners can use ROXY.
- Preserved the live `/api/v1/public-site/popular-trends` API, muted viewport-gated video playback, referral parameters, direct trend links, no-user-session public access and `/landing/` = 404.
- New static regression assertions in `tests/test_public_site.py`; browser screenshots at 320, 390, 768, 1024 and 1440 widths must be reviewed for overflow, sticky navigation, hierarchy, captions and mobile stacking.

References: `shadcn-ui/ui` Button and Accordion primitive source; `anthropics/skills/skills/frontend-design/SKILL.md`; KSU `AGENTS.md`.
