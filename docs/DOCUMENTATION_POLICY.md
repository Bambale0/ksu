# Documentation maintenance policy

All maintained documentation uses `docs/README.md` as the index and `docs/CURRENT_STATE.md` as the cross-domain shipped-state snapshot.

Rules:

1. Runtime/backend validation is authoritative over stale prose.
2. Generation model/schema details come from `ModelCatalog` and `/api/v1/generations/models`.
3. Generation prices come from server pricing resolution and the latest published Admin Tariffs configuration; frontend copy is never a billing authority.
4. New production features update the relevant domain document and `ROXY_RELEASE_ACCEPTANCE.md` in the same change when the acceptance contract changes.
5. Security-sensitive admin behavior must be documented in the admin security/runbook family, not only in UI comments.
6. Historical `parity-*` plans remain historical records and must not silently override current product contracts.
7. Approved visual assets belong in the repository or documented asset mirror. User-approved artwork must not be generatively reconstructed when exact preservation is required.

Documentation sync date for this policy: 2026-08-20.
