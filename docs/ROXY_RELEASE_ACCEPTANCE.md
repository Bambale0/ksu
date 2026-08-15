# ROXY Release Acceptance

This document is the release checklist for the customer Mini App. The automated contract is implemented in `scripts/check_roxy_release.py` and `tests/test_roxy_release_acceptance.py`.

## Automated gate

A release candidate must pass all of the following before production promotion:

- all Mini App JavaScript parses with Node;
- canonical ROXY routes exist for Home, Catalog, Create, History, Profile and native child screens;
- legacy `trends.html`, `prompt-tools.html` and `batch.html` URLs forward into the canonical shell;
- no global `window.fetch` monkeypatching in Feed/Social;
- no whole-document TreeWalker text rewriting in Brand/Economy;
- Brand has no full-DOM MutationObserver;
- Economy/Music do not observe the whole body subtree;
- customer Mini App source contains no legacy `Ксю`, `КСЮ` or ` кр.` labels;
- primary navigation uses the shared SVG line-icon runtime;
- Telegram safe-area, VisualViewport keyboard handling, BackButton and browser history contracts remain present;
- touch targets are at least 44px and mobile form controls keep 16px font size;
- horizontal overflow protections remain enabled;
- FHD density layer remains packaged;
- mature UI tokens, focus-visible and reduced-motion handling remain packaged.

## Viewport acceptance matrix

The required visual matrix is:

- 360×800 — compact Android phone;
- 390×844 — common iPhone viewport;
- 430×932 — large phone;
- 1366×768 — compact desktop/laptop;
- 1920×1080 — FHD desktop.

For every viewport verify Home, Catalog, Create, Result, History, Feed, Wallet, Profile and at least one child screen. There must be no horizontal scrolling, clipped primary controls, media escaping the viewport, or bottom navigation overlapping editable fields.

## Physical Telegram acceptance

Before a production release, run one pass on a real Telegram iOS client and one on a real Telegram Android client:

- cold start from the bot launcher;
- deep start to a child route;
- Telegram BackButton through child → parent → home;
- browser/history back-forward where available;
- open keyboard in prompt, comment, support and payment-email fields;
- rotate / resize where supported;
- background and reactivate the Mini App;
- disconnect/reconnect network while a server request is pending.

## Critical product flows

Run these end-to-end against the release environment:

- image generation: model → settings → quote → upload/reference → run → result → history;
- video generation with per-second billing;
- music generation and audio playback;
- Trend run with required references;
- Prompt Tools task and polling;
- Batch quote/run/retry;
- publish to Profile/Feed, like, comment, share and allowed remix;
- hidden History → reload → restore;
- preset create → edit → apply → delete;
- Notifications read-one/read-all and visible badge;
- Support create → reply → close → reopen;
- public Author profile → subscribe/unsubscribe;
- promo redemption and insufficient-ROX recovery;
- payment create → provider redirect → return → terminal status/balance refresh;
- referral withdrawal create/cancel.

## Failure policy

Do not promote when the automated release gate fails, when a primary route cannot be recovered after cold start, when Telegram BackButton exits instead of stepping back inside the app, when money/ROX state is ambiguous after payment, or when a generation/result action is shown despite being unsupported by the backend capability contract.
