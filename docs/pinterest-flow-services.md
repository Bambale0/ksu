# Pinterest Flow in Services

Pinterest Flow is a dedicated customer service surface in the ROXY Mini App.

- Entry point: `/mini-app/services/`
- Runner: `/mini-app/pinterest-flow/?id=<trend-id>`
- API catalog: `GET /api/v1/services/pinterest`
- API item: `GET /api/v1/services/pinterest/{trend_id}`
- API run: `POST /api/v1/services/pinterest/{trend_id}/run`

Pinterest service recipes reuse active admin trend records whose title or tags identify them as Pinterest. They are excluded from the generic customer Trends API and exposed through Services instead.

Reference order is server-owned and must not be changed by the client:

1. Pinterest scene/composition reference.
2. Primary identity reference.
3. Up to five supporting identity angles.

The runner also requires height, weight and explicit confirmation that the user may use the identity references. The curated recipe prompt remains server-owned and hidden from customer responses.
