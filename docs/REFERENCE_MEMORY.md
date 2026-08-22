# ROXY reference memory

ROXY keeps reusable user media separately from the state of the current generation form. This ports the proven `banano_kling:tanyapi` reference-library behavior without reintroducing implicit draft persistence.

## Product contract

- Uploading image, video or audio through a generation field saves it to the user's reusable reference library.
- A new generation always starts from the selected model's current `ui_schema.defaults`. Saved references are **not** automatically inserted into a new form.
- Saved references appear next to compatible `file` / `files` controls and are added only after an explicit user click.
- `Использовать настройки` may intentionally restore references from an owned previous generation. This is distinct from a normal new-generation launch.
- Removing a reference from the current form does not delete it from the reusable library.
- Deleting a saved reference soft-deletes only the library entry; it does not mutate already-created generation history.

## Persistence and deduplication

`user_references` stores one logical reusable reference with:

- owner and media `kind` (`image`, `video`, `audio`);
- current provider-safe HTTPS `source_url`;
- SHA-256 `file_hash` when the file came through the Mini App upload endpoint;
- original filename and content type;
- source marker (`mini_app_upload`, `manual`, etc.);
- `created_at`, `updated_at` and `last_used_at`.

The upload endpoint hashes the original bytes before provider upload. Re-uploading identical bytes for the same user and media kind reuses the existing logical reference even when Kie returns a different URL. URL-level idempotency is kept for manually registered references that do not have a hash.

## Recency and retention

Reference selection updates `last_used_at`. The library is ordered by real use recency and keeps up to 12 ready references per media kind. The higher limit than the Tanya donor is deliberate: ROXY models can accept large multi-reference sets, so a three-item donor limit would discard useful inputs too aggressively.

Pruning is a soft delete of the library row. Input media currently uses the Kie upload URL; product-owned S3 ingest remains authoritative for completed generation results. Therefore pruning a reference entry does not attempt to delete upstream provider media.

## API

- `GET /api/v1/references?kind=image|video|audio&limit=N` — list the current user's library.
- `POST /api/v1/references` — manually register an HTTPS reference.
- `POST /api/v1/references/touch` — mark selected reference URLs as recently used.
- `DELETE /api/v1/references/{id}` — remove a reference from the user's library.
- `POST /api/v1/uploads/kie` — upload media and automatically register/hash-deduplicate it as reusable reference memory.

All reference lookup, selection and deletion remains owner-scoped on the backend. The frontend library is convenience UI, not an authorization boundary.

## Fresh-create invariant

The reference library and the creation draft are intentionally separate domains:

```text
Reusable library
  └─ explicit user selection ──> current generation draft ──> provider payload

New generation
  └─ ui_schema.defaults only
```

No "last reference", previously uploaded file, prompt or old form state may silently enter a normal fresh generation. That invariant is covered together with the explicit saved-reference picker by `tests/test_reference_memory_ux_contract.py`.
