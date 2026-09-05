# Durable media storage

**Status:** runtime contract for product-owned generation media introduced with migration `0006_durable_media_storage` and stored on the KSU host.

## Runtime contract

Provider result URLs are temporary ingestion sources, never the durable product copy. When Kie reports a successful generation, KSU writes `media_assets` and `media_ingest_jobs` in the same PostgreSQL transaction that marks the generation succeeded. The dedicated `media-worker` downloads each result and persists it below the server-owned media root.

```text
Kie success callback / reconciliation
        |
        v
Generation + MediaAsset + MediaIngestJob COMMIT
        |
        v
media-worker claim (FOR UPDATE SKIP LOCKED)
        |
        +--> validated public HTTPS download
        +--> bounded temporary file + SHA-256
        +--> atomic copy into static/uploads/media
        |
        v
MediaAsset status=ready + local object key/hash/size
```

The Docker runtime already bind-mounts `./static/uploads:/app/static/uploads` into the API and media worker, so generated files survive container recreation on the production host just like feed/reference files. `static/uploads/media` is intentionally **not** mounted with FastAPI `StaticFiles`: unpublished user generations remain private.

The default root is:

```dotenv
MEDIA_LOCAL_ROOT=static/uploads/media
```

`MEDIA_LOCAL_ROOT` is optional; the default above is used when it is absent.

## Private and public delivery

Local media has two delivery modes:

- private/history result URLs are short-lived HMAC-signed KSU URLs;
- published feed/profile media is served through `/api/v1/media/{asset_id}/public`, which re-checks publication scope and moderation before reading the file.

The HMAC key is domain-separated from the persistent production `ADMIN_SECURITY_KEY`, which the deployment workflow already guarantees. No extra media secret is required.

Authenticated downloads use:

```text
GET /api/v1/media/{asset_id}/download
```

Ownership failures return 404. Signed URLs expire according to `MEDIA_PRESIGN_TTL_SECONDS`; the setting name is retained for backward compatibility with legacy S3 media.

## Required configuration

Host-local storage does not require S3 credentials. Relevant runtime settings are:

```dotenv
MEDIA_LOCAL_ROOT=static/uploads/media
MEDIA_WORKER_POLL_SECONDS=5
MEDIA_INGEST_LEASE_SECONDS=600
MEDIA_INGEST_MAX_ATTEMPTS=5
MEDIA_INGEST_MAX_BYTES=1073741824
MEDIA_INGEST_CONNECT_TIMEOUT_SECONDS=10
MEDIA_INGEST_READ_TIMEOUT_SECONDS=180
MEDIA_INGEST_MAX_REDIRECTS=5
MEDIA_PRESIGN_TTL_SECONDS=900
MEDIA_LEGACY_RECONCILE_SECONDS=60
```

The production host must retain and back up `static/uploads`. A container/image rebuild must never be treated as the media backup. The directory should be included in host snapshots or encrypted off-host backups together with the database backup policy.

## Atomicity and retries

Downloaded provider media is streamed into a temporary file while SHA-256 and size are calculated. The worker then copies into a temporary file inside the destination directory and uses an atomic rename to the deterministic final key:

```text
generations/<user_id>/<generation_id>/<ordinal>-<sha-prefix>.<ext>
```

If the worker dies after the file write but before the database commit, the retry converges on the same deterministic path rather than creating a new product object.

A host-storage failure is treated as an operational delivery problem. It does not turn a successfully paid generation into a provider failure and does not issue a generation refund. The ingest job is retried while the temporary provider URL remains available.

## Source-download safety

The media worker does not blindly fetch arbitrary URLs. Every source and redirect target must:

- use HTTPS;
- have no embedded username/password;
- resolve to public IP addresses;
- stay within the configured redirect count;
- fit under `MEDIA_INGEST_MAX_BYTES`;
- return an image/video type, recognized media extension, or the supported audio types handled by the music ingest worker.

The process does not buffer a full video/audio file in application memory.

## API behavior

Generation detail/history behaves as follows:

1. before the server-owned asset is ready, the provider URL remains a compatibility fallback;
2. once the local asset is ready, the KSU signed URL takes precedence;
3. `result_storage` becomes `owned`;
4. `media[]` contains asset id, view URL, authenticated download endpoint, MIME type, size and ordinal.

Published feed/profile serializers use the stable publication-gated KSU route instead of a private signed URL.

## Legacy S3 compatibility

Older `media_assets` rows may still contain a real S3 bucket and object key. KSU keeps the S3 reader/presigner for those rows only. `S3_BUCKET`, region/endpoint and credentials are therefore **optional legacy configuration**, not a prerequisite for new generations.

If legacy S3 remains configured, its private-bucket rules still apply. Do not grant public `s3:GetObject`. Telegram Web downloads may require the legacy bucket CORS response:

```http
Access-Control-Allow-Origin: https://web.telegram.org
```

Old S3 installations that use multipart upload should retain a lifecycle rule with `AbortIncompleteMultipartUpload` so abandoned multipart parts do not accumulate. These rules do not apply to new host-local generation media.

When legacy S3 configuration is deliberately removed, history can temporarily fall back to the original provider URL for old S3 rows if that URL is still alive. New local rows are unaffected.

## Recovery

`media-worker` periodically repairs succeeded generations that have a provider result URL but no `MediaAsset` rows. Queue claims use `FOR UPDATE SKIP LOCKED`; expired leases are reclaimable. Image/video and audio ingest both target the same private host-local root.

The production deploy keeps the existing bind mount:

```text
./static/uploads:/app/static/uploads
```

That mount must remain present for `app`, `generation-worker`, `media-worker`, and any worker that writes reference/feed media.

## Monitoring

Important metrics:

```text
ksu_media_assets{status}
ksu_media_ingest_jobs{status}
ksu_media_ingest_oldest_pending_seconds
ksu_worker_up{worker="media-worker"}
ksu_distributed_event_count{event="media_ingest_processed"}
ksu_distributed_event_count{event="music_audio_ingest_processed"}
ksu_distributed_event_count{event="music_audio_worker_loop_error"}
ksu_distributed_event_count{event="media_reconcile_failure"}
ksu_distributed_event_count{event="media_worker_loop_error"}
```

Alert if the media worker heartbeat is stale or the oldest pending/processing ingest remains old enough to threaten provider URL expiry. Also monitor host disk utilization because generated media now intentionally lives on the KSU server.
