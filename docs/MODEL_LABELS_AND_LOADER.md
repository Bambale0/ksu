# Model labels and ROXY loader

Updated: 2026-08-21

## Model cards

Customer-facing model cards must stay simple:

- full product name;
- one short outcome-focused description;
- price pill.

Do not repeat reference support on every card. Reference files are a baseline capability
for current ROXY generation products and mode selection is handled by backend routing.

Price display is role-aware:

- active admin users receive `price_rox = 0.00` and may see `Бесплатно`;
- regular users receive the retail ROX price.

The canonical copy is kept in `app/services/model_family_catalog.py`, while provider
IDs and payload routing remain separate from UI labels.

## Loader

The ROXY splash loader is CSS-only. It should keep a stable symmetrical shape:

- centered RX mark inside the animated circle, not beside or above it;
- one clean circular loader composition;
- two rotating neon arcs around the logo;
- subtle particles inside the ring;
- animated ROX progress line;
- `prefers-reduced-motion` support.

Avoid dense radial spoke effects that can visually break into a distorted wheel on
small Telegram WebView screens.

## Feed publication timing

Publishing a finished generation is allowed as soon as Kie returns result URLs. Public
feed/profile discovery must still return only rows backed by ready `MediaAsset` records.
This keeps the user action responsive while ensuring public cards download media through
ROXY server routes instead of temporary provider URLs.
