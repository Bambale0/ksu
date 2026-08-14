# ROXY Telegram / Mobile Acceptance

This document is the release checklist for the customer-feedback mobile hardening epic.

The automated test suite verifies implementation contracts. It does **not** replace a physical Telegram smoke test on real iOS and Android clients before production rollout.

## Target surfaces

Primary customer routes:

- `Главная`
- `Каталог`
- `Создать`
- `История`
- `Профиль`

Secondary route:

- `wallet` / ROX top-up, visually owned by Profile rather than a sixth primary tab.

Nested surfaces include the generation builder, generation result/detail, Feed, Creator application, checkout and supporting tools.

## Width matrix

At minimum verify browser/device widths representative of:

| Width | Acceptance focus |
| --- | --- |
| 320 px | minimum supported narrow layout, five-tab nav labels, forms, modal/content overflow |
| 360 px | common compact Android viewport, central Create ergonomics |
| 390 px | current iPhone-class viewport, keyboard and safe-area behavior |
| 430 px | large phone viewport, Catalog grids, payment controls |

Desktop/tablet remains covered by the existing `>=720px` / `>=1024px` shell layouts and sidebar.

## Telegram viewport and safe area

ROXY uses Telegram's viewport and safe-area APIs when present and CSS/env fallbacks otherwise.

Acceptance requirements:

- use `viewport-fit=cover`;
- call `Telegram.WebApp.ready()` and `expand()`;
- use `viewportStableHeight` for stable bottom-pinned UI;
- react to `viewportChanged`;
- react to `safeAreaChanged` and `contentSafeAreaChanged`;
- preserve left/right content insets on notched/rounded devices;
- keep header content below the top content safe area;
- keep the five-item bottom nav above the content-safe bottom inset.

`roxy-mobile-runtime.js` mirrors Telegram values into `--roxy-*` fallback variables so older CSS paths and browser preview remain deterministic.

## Keyboard acceptance

On mobile WebViews, the software keyboard must not leave the active control hidden under the viewport or bottom navigation.

Runtime behavior:

- tracks `window.visualViewport` when supported;
- only declares keyboard-open with a focused form control and a substantial viewport reduction;
- hides the fixed customer bottom navigation while typing;
- removes unnecessary bottom-navigation padding from content while the keyboard is open;
- scrolls the focused input/textarea/select back into the visible area;
- uses 16 px form-control text on narrow phones to avoid Safari focus zoom;
- calls Telegram `hideKeyboard()` opportunistically before route navigation where supported.

Smoke test:

1. open Create;
2. focus a long prompt textarea;
3. type enough content to produce internal scrolling;
4. switch between fields;
5. close keyboard and verify the bottom nav returns;
6. repeat in checkout email and Creator application fields.

## BackButton semantics

There are two navigation depths and they must not collapse on one Back press.

Nested builder/result state is owned by the existing shell/browser-history bridge. Top-level customer route state is owned by the mobile runtime.

Expected Telegram Back behavior:

- generation builder/detail -> previous nested shell state / Create home;
- secondary `wallet` -> Profile;
- Catalog / Create center / History / Profile -> Home when no nested shell is open;
- Home -> Telegram owns app close/minimize behavior; ROXY hides its BackButton.

The mobile runtime keeps a nested-state snapshot so a shell BackButton handler that closes a builder synchronously cannot cause the same Back press to immediately navigate a second time to Home.

## Initial route acceptance

The bot may launch the Mini App with `?route=`.

Allow-list:

- `home`
- `catalog`
- `create`
- `history`
- `profile`
- `wallet`

Unknown values must not become arbitrary DOM/routes. `wallet` activates Profile in the primary navigation.

Smoke each Telegram launcher and verify the initial route is visible without requiring a second tap.

## Home carousel and Catalog scrolling

Promotional slides use horizontal overflow with scroll snapping and contained inline overscroll.

Verify:

- horizontal swipe does not trigger accidental vertical page jumps;
- dot state follows the closest slide after the swipe settles;
- promo CTA remains at least a mobile-size touch target;
- long Catalog content scrolls independently of horizontal promo gestures;
- Catalog returns to top when explicitly reopened;
- community video previews stay inline.

## Feed / video acceptance

Public Feed video uses native controls, `playsInline` and metadata preload.

Verify:

- video does not force fullscreen on supported iOS clients;
- controls remain reachable above safe-area/bottom UI;
- long Feed scroll does not leave a stale fixed overlay/body-lock when switching primary routes;
- blurred/moderated media keeps the existing moderation treatment.

## Music / audio acceptance

Music results use native `<audio controls>` players.

Verify:

- player width never exceeds the phone viewport;
- player remains usable after provider URL is replaced by product-owned presigned storage;
- leaving the result and reopening History still renders a player;
- `Повторить / изменить` remains available through the existing generation History flow.

## Checkout acceptance

Hosted card checkout remains guarded by direct user activation and HTTPS-only URLs.

Primary behavior:

- direct user tap creates/opens the payment intent;
- use `Telegram.WebApp.openLink()` in Telegram when available;
- browser fallback uses a new tab with `noopener,noreferrer`;
- no timer/background callback is allowed to open a payment URL without a user action;
- returning to the Mini App resumes status polling/reconciliation and refreshes ROX balance on success.

Verify RUB plus any configured USD/EUR package once merchant settings are available.

## Performance / motion

ROXY keeps visual effects on capable devices but must remain usable on constrained Android WebViews.

The runtime enables low-motion behavior when:

- OS/browser requests reduced motion, or
- Telegram reports Android and the browser exposes <=4 logical CPU cores.

Low-motion mode suppresses non-essential animations/transitions and expensive backdrop blur. It does not change data, pricing or navigation behavior.

## Automated gate

`tests/test_roxy_mobile_acceptance.py` statically verifies:

- Telegram viewport setup and safe-area bindings;
- five-item bottom navigation and safe-area CSS;
- BackButton ownership boundaries;
- `?route=` allow-list startup;
- visualViewport keyboard treatment and 16 px mobile controls;
- minimum touch-target rules and reduced-motion fallback;
- Catalog scroll-snap, Feed video, shell video and music audio contracts;
- direct-activation HTTPS checkout through Telegram `openLink`.

CI additionally runs `node --check` on the mobile runtime and the full project regression suite.

## Production smoke checklist

Before deployment sign-off:

1. Telegram iOS at approximately 390–430 px width.
2. Telegram Android at approximately 360–430 px width.
3. Narrow 320 px browser/devtools regression pass.
4. Home swipe + Catalog long scroll.
5. Create Photo, Video and Music routes.
6. Prompt keyboard + upload controls.
7. One video playback and one audio playback.
8. History -> result -> BackButton.
9. Wallet -> Profile BackButton.
10. Hosted checkout opened by direct tap; return and reconciliation.
11. Creator application form with keyboard.
12. Rotate device once where Telegram permits rotation and confirm no horizontal overflow.

Any real-device failure should become a focused regression test before release rather than a one-off CSS workaround.
