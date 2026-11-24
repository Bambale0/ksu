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

- The capabilities section is deliberately **type-led**: a compact 2×2 editorial feature grid with no decorative photo, repeated hero artwork, or card chrome. At narrow widths it becomes one readable column. Hero and living gallery carry the imagery.
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

## Typographic capabilities redesign (2026-11-23)

The 2026-11-23 screenshot demonstrated a product-design issue, not just pixel spacing or a deployment issue: the large face portrait was repeated from the hero's 3×3 atlas, with an unrelated decorative flower overlay. Despite corrected CSS cropping, it dominated the four feature descriptions and conveyed no additional feature information. Do **not** restore the old image stage.

The `#features` section now uses a restrained asymmetric introduction followed by four text-first items in a **two-column, two-row editorial grid** (single column at ≤700px). Each option states an actual supported action. There are no invented screenshots, hover affordances on inert rows or separate JavaScript dependencies. The sole action link still points to the existing `/mini-app/` and preserves approved referral parameters via `data-app-link`.

A screenshot captured while manually scrolling beneath the sticky header is not proof that an anchor is broken. The established `html{scroll-padding-top:100px}` / mobile 84px mechanism remains the only anchor offset. Validate direct `/#features` navigation separately from mid-scroll captures.

**QA:** Compare 320, 390, 700, 768, 1024, 1440px. Verify no horizontal overflow or title clipping, 2 columns on desktop/tablet and one on narrow screens, all four text items, CTA/deep-link behavior, native focus, and reduced motion. The independent marketing site remains separate from Mini App, billing, bot and provider code.

## Public asset cache invalidation (2026-11-23)

The marketing HTML response is intentionally `Cache-Control: no-store`, but the CSS and gallery JavaScript are served through FastAPI `StaticFiles`. Unversioned asset links can remain cached across application deployments, causing clients to see a new HTML document with old styling or gallery logic.

The HTML now uses `?v=<git-blob-sha-prefix>` on `/site-assets/styles.css` and `/site-assets/popular-trends.js`. The query string does not affect `StaticFiles` path resolution; it gives each new asset content version a distinct browser/CDN cache key. `tests/test_public_site.py` derives the fingerprint from each file's actual bytes and fails CI if an asset changes without the HTML reference changing.

This change does not touch Mini App files or cache settings, user sessions, billing or generator routes. The standalone HTML remains `no-store`. If an old visual is still displayed after deployment, inspect the live document's stylesheet URL, the `200/304` response, and the origin/reverse-proxy route before attributing it to CSS caching.

## RX editorial campaign / motion system (2026-11-24)

The public `/` landing retains independent FastAPI static hosting and the existing live trend gallery, API and referral links. Its previous full-screen 3×3 image mosaic is replaced with a type-led asymmetric campaign composition modeled on the approved ROXY brand: a single hero portrait crop from the bundled atlas, glowing magenta/violet RX outline monogram, controlled geometric outlines, left-aligned copy, and five actionable creation tiles. `/mini-app/` remains an independent Next.js app; no auth/session/provider or pricing changes are in this feature.

Assets: `app/web/site/assets/experience.css`, `experience.js`, `roxy-mark.svg`; the existing fingerprinted `styles.css` and `popular-trends.js` remain separate. The new favicon is an SVG reproduction of the RX geometry from the supplied brand reference; obtaining the original vector master is preferable for perfectly faithful cross-channel logo use. A self-hosted 1200×630 PNG is used for Open Graph / social cards, incorporating RX-style geometry and approved brand colors. It is a rendered brand preview, not an image of actual customer output; no external trackers or CDNs.

The progress indicator is a fixed 3px bar with `role=progressbar` and a continuously redrawn SVG Bézier path along the page edge. The JS uses a single `requestAnimationFrame` scroll scheduler, passive scroll listeners, and CSS transforms to parallax separate hero layers and tilt the five creation tiles, live gallery cards, and feature rows via delegated pointer events. Hover tilt runs only on fine-hover devices; keyboard focus has its own visible emphasis. `prefers-reduced-motion` disables parallax, tilt, and transitions without disabling progress or navigation. Video tiles retain the independent live video IntersectionObserver implementation with no autoplay changes.

Acceptance: no overlap at 320/390/768/1024/1440px, no horizontal overflow, readable hero, no duplicate or invented trends, keyboard access to all tile links, working app CTA and referral startapp/ref forwarding, no navigation regression, CDN-busting versioned CSS/JS, and no unbounded main-thread work. CSS-only base styles remain readable if the optional motion JS fails. Revert this isolated PR to restore the previous campaign.


## Approved campaign fidelity correction (2026-11-24)

Production screenshot showed an overmagnified atlas crop and a five-line headline caused by 300% background sizing and max-width:12ch. The approved campaign reference is the user's full-resolution cyberfashion RX artwork (1648×928 presentation); the original supplied file was uploaded and the text-free right-hand image region extracted proportionally as roxy-reference-hero.webp (825×705), not the UI screenshot flattened into a page. The supplied RX logo is cropped to roxy-official-mark.webp (387×280). Both are local WebP assets; aspect ratio is preserved using contain, no synthetic replacement. The three headline lines and five custom line-art icons are actual HTML/SVG, with normal-flow cards and desktop height-aware sizing. Mobile keeps the same artwork and naturally stacked content.

Motion: scroll-depth layers and SVG progress are retained. Pointer position moves the portrait independently of geometric outline and light ribbon; cards get local spotlight, tilt and media displacement. Static low-opacity film grain adds grunge without continuous repainting. All effects are guarded by fine-pointer/reduced-motion and scheduled through requestAnimationFrame. No new runtime libraries, trackers or third-party CDNs. References: Anthropic frontend-design (intentional identity), Bambale0/skills (small regression-tested change), claw frontend-qa (responsive/clickable checks), wondelai release-it (release verification), dev-agents-pack (QA/review), agentskills (versioned guidance). Local .agents index was not present on GitHub.

Verification: Python static contracts and Node syntax checks; actual public-site E2E across 320/390/768/1440/1648/1850 widths, card/hero geometry, reduced-motion, hover and progress. No billing, authentication, user data or provider changes in this visual PR. Separate /login migration remains a distinct authentication task (#645 is conflicting and must not be merged blindly). Exact production SHA and visual browser smoke are required before claiming fidelity or deployment.


## Hero visual system extended across the public campaign (2026-11-24)

The approved first screen is the visual source of truth. Lower sections use its system typography, violet-black background, pink/lilac light, glass surfaces and horizontal inset. Four tool descriptions receive semantic line icons; the process is a single three-step film strip, not fake buttons. The living gallery uses the real catalog and existing hover/reduced-motion behavior. Native FAQ details are styled as discrete glass surfaces. The last CTA uses the existing transparent RX asset as a restrained closing image, not repeated hero art. Footer follows the same width and palette. No new image, JS, framework or network asset is introduced. Existing CTA paths and query preservation remain unchanged until the independent web identity release.

The new browser acceptance cases cover 320, 390, 768, 1440 and 1648px, verify consistent type, surface and logo, section bounds, reduced motion, accessible native FAQ operation and existing CTA paths. Existing hero, gallery, motion and fingerprint tests are preserved. Release requires exact-head CI and live visual verification.


## Multipage public website (2026-11-24)

Public GET/HEAD pages /features, /gallery, /process and /faq are explicit FastAPI routes with the same no-store policy as /. Home remains the overview with stable legacy section anchors; navigation links open real independent documents. Each subpage has its own H1, title, canonical, description, practical content and next links. The home shell (RX header/footer and asset versions) is the source for deterministic checked-in pages: run `node scripts/build_public_site_pages.mjs` after editing it and `node scripts/build_public_site_pages.mjs --check` to verify parity. Home gallery shows 6 and standalone gallery 12, using the same public API and safe projection. Query propagation allows only startapp, start_payload and ref, bounded to 256 characters. Native Mini App entry /mini-app/ remains unchanged pending independent web identity release #645. Unknown public paths remain 404; no catch-all or framework added. Verify GET/HEAD, direct reload, active nav, back, keyboard FAQ, mobile and all real trend links.


Release verification: the existing production workflow checks every public route using GET and HEAD against the exact deployed application image and verifies the matching `data-page` identity, in addition to existing health and worker image checks. This is not a substitute for external-domain browser QA. Unknown public paths remain excluded from the allowlist.


## Legacy browser entry routing correction (2026-11-24)

Production reproduction on release 459236e8: the marketing site's Start CTA enters /mini-app/ and an unauthenticated browser sees the older TelegramBrowserLogin film mosaic. Its marketing links pointed to local #features, #how and #examples instead of the real public pages. Those header, mobile, footer and hero-arrow links now target /, /features, /process, /gallery and /faq on the same origin, passing only bounded referral keys. Login CTAs and the Telegram widget remain in the existing authentication contour; native Telegram and deep-link authentication are unchanged. Dedicated first-party /login remains part of independent PR #645. Both slash spellings of the four marketing pages now directly return the same no-store document; the canonical metadata remains slashless. This removes the observed 307 Location with an http scheme without changing global proxy trust or redirect settings. The deploy smoke now checks both spellings. Regression tests explicitly require real route navigation and GET/HEAD 200 without Location. No changes to DB or paid operations.


## Transparent hero and distinct tool pages (2026-11-24)

Hero uses the transparent cutout WebP, preserving the original reference asset for rollback. The foreground portrait has an actual alpha channel and the surrounding site lighting is independent CSS. Each hero tile opens its own standalone public route (/features/photo, /features/video, /features/text, /features/own-photo, /features/reference). Marketing start/sign-in buttons go to /login. That page uses the existing Telegram browser-auth API and existing same-tab sessionStorage format, validates existing sessions and accepts only validated UUID trend targets plus bounded referral keys. After verified authentication it opens the existing Mini App or the selected trend. No email/Yandex capability is invented; full identity remains #645. All pages use explicit GET/HEAD routes and slash aliases, deterministic generated documents, and release smoke checks. Existing original hero image and native Mini App auth remain unchanged.

Tool-page entry buttons preserve an allowlisted tool identifier through /login. The authenticated destination is the existing creation screen; photo/own-photo and video select the existing image/video category via validated create_media, while text/reference leave model selection to the user. No generation is automatically started. The WebKit release audit includes standalone pages and entrypoints.


## Public promos
Original Mini App promo WebPs reused byte-for-byte in public assets. Author rewards after hero, partner artwork replaces closing RX on shared pages. Native 16:9 without cropping, lazy decoding, responsive single column at <=1000px. Both images and CTA buttons go through /login?section=partners to existing /mini-app/?route=partners. No program rules changed. Graphic amounts are original artwork, actual eligibility governed by live program terms.
