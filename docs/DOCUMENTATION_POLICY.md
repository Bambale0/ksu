# Documentation maintenance policy

All maintained documentation uses `docs/README.md` as the index and `docs/CURRENT_STATE.md` as the cross-domain shipped-state snapshot.

Rules:

1. Runtime/backend validation is authoritative over stale prose.
2. Generation model/schema details come from `ModelCatalog` and `/api/v1/generations/models`.
3. Generation prices come from server pricing resolution and the latest published Admin Tariffs configuration; frontend copy is never a billing authority.
4. Every runtime-affecting change must update the relevant maintained documentation in the same PR before merge. This includes behavior, model/provider contracts, pricing, environment variables, worker/recovery semantics, payments, referrals, security, deployment and operations. A follow-up docs PR is an exception for repairing pre-existing drift, not the normal workflow.
5. New production features update the relevant domain document and `ROXY_RELEASE_ACCEPTANCE.md` in the same change when the acceptance contract changes.
6. Security-sensitive admin or provider behavior must be documented in the security/runbook family, not only in UI comments or code comments.
7. Environment/configuration additions or removals must keep `.env.example`, runbooks and deployment documentation synchronized; example files must never contain live credentials or secrets.
8. Historical `parity-*` plans remain historical records and must not silently override current product contracts.
9. Superseded maintained documentation and dead runtime paths should be removed once their replacement is merged and verified. Historical records may remain only when clearly marked historical and absent from the current source-of-truth path.
10. Merged short-lived branches are repository debris and should be pruned after merge. Automated pruning may delete only a local branch whose current tip still exactly matches a merged PR head SHA, has no open PR and is not a protected environment/release branch. Divergent/reused branches require inspection before deletion. See `REPOSITORY_HYGIENE.md`.
11. Legacy runtime code must not be retained merely as a fallback after its replacement is proven and merged. Remove obsolete imports/routes/config/docs/tests together, while preserving required database migration history.
12. Approved visual assets belong in the repository or documented asset mirror. User-approved artwork must not be generatively reconstructed when exact preservation is required.

Documentation sync date for this policy: 2026-08-20.
