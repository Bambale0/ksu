# ROXY PostgreSQL backups

ROXY runs a dedicated `backup-worker` alongside PostgreSQL. The worker uses `postgres:17-alpine`, matching the database major version and providing the native `pg_dump` / `pg_restore` toolchain without adding database clients to the application image.

## Runtime contract

Production deploy explicitly starts `backup-worker` as a runtime service. The worker depends on healthy PostgreSQL but the customer-facing `app` does not depend on backup completion, so a large dump cannot hold the application startup path open.

The worker reads `DATABASE_URL`, normalizes only the SQLAlchemy `postgresql+asyncpg://` scheme for libpq tools, and creates a custom-format dump every three hours by default. If a dump/validation attempt fails, the worker retries after **60 seconds** until it produces a verified archive; the normal three-hour interval resumes only after success.

A periodic archive is published only after all of these conditions succeed:

1. `pg_dump --format=custom --no-owner --no-privileges` exits successfully;
2. the temporary archive is non-empty;
3. `pg_restore --list` can parse the archive catalog;
4. a SHA-256 checksum is generated;
5. the verified temporary files are renamed inside the private backup volume;
6. `latest.dump` / `latest.dump.sha256` are switched to the newly verified archive;
7. old timestamped archives are pruned to the configured retention count.

The worker sets `umask 077`, so newly created dump/checksum files are private by default. Temporary files left by an abruptly killed predecessor are never treated as backups and are removed when the worker starts again.

Configuration:

```dotenv
DB_BACKUP_INTERVAL_SECONDS=10800
DB_BACKUP_RETENTION_COUNT=16
DB_BACKUP_ON_START=true
```

The compose-managed directory is `/backups` in the private `db_backups` Docker volume. It must never be mounted into the public app/web root.

## Production release backup

The GitHub production deploy still creates a separate **pre-migration** host-side archive before `alembic upgrade head`. That archive must be non-empty, parse successfully through `pg_restore --list`, and receive a SHA-256 sidecar before the deploy is allowed to continue.

This is intentionally separate from the long-running worker:

- the pre-deploy archive protects the exact migration boundary;
- `backup-worker` provides periodic operational snapshots after the release;
- neither mechanism by itself is off-host disaster recovery.

## Verify the latest periodic backup

Check the worker and newest verified archive:

```bash
docker compose ps backup-worker
docker compose exec -T backup-worker sh -c 'ls -lh /backups/latest.dump /backups/latest.dump.sha256'
```

Verify checksum from inside the volume:

```bash
docker compose exec -T backup-worker sh -c 'cd /backups && sha256sum -c latest.dump.sha256'
```

Verify that PostgreSQL can parse the custom archive:

```bash
docker compose exec -T backup-worker pg_restore --list /backups/latest.dump >/dev/null
```

A checksum/catalog check proves that the stored bytes are internally readable; it is **not** a substitute for an actual restore drill.

## Restore drill

Perform restore drills only in an isolated/disposable database, never by overwriting production in place.

Example against the compose PostgreSQL service:

```bash
docker compose exec -T postgres createdb -U ksu ksu_restore_test

docker compose exec -T backup-worker \
  pg_restore \
  --no-owner \
  --no-privileges \
  --dbname=postgresql://ksu:ksu@postgres:5432/ksu_restore_test \
  /backups/latest.dump
```

Then point a disposable application environment at `ksu_restore_test` and run integrity/smoke checks for at least users, wallets, payments, generations/outbox, media metadata, partner/referral state and current Alembic revision. Remove the test database afterwards:

```bash
docker compose exec -T postgres dropdb -U ksu ksu_restore_test
```

For a production restore drill with different credentials, use the isolated target database's own connection string rather than copying production secrets into shell history.

## Off-host durability

`db_backups` is a Docker volume on the application host. It protects against some database-level corruption and operator mistakes, but it does **not** protect against total host/storage loss.

The repository does not automatically upload database dumps to Telegram, chat systems or the media bucket. Production operations must copy/snapshot verified backups into a dedicated encrypted off-host durability layer with an explicit retention/access policy.

**Do not send database dumps through Telegram or other chat transports.** They contain durable product/accounting state and may contain personal/customer data.

The S3-compatible media bucket is a separate durability domain. PostgreSQL backups contain media metadata/object keys, not the media object bytes themselves; media versioning/replication/backups must be managed independently.

## Incident behavior

If `backup-worker` restarts or reports repeated `backup failed` messages:

1. do not delete the most recent verified archive;
2. inspect `docker compose logs --tail=200 backup-worker`;
3. verify PostgreSQL readiness and free disk space;
4. verify `DATABASE_URL` is a PostgreSQL URL reachable from the compose network;
5. run checksum/catalog validation on the last known-good archive;
6. expect failed attempts to retry every 60 seconds rather than waiting a full scheduled interval;
7. restore service before allowing the backup age to exceed the operational recovery objective;
8. escalate immediately if both local and off-host copies are stale/unavailable.

Do not work around backup failures by weakening archive validation or publishing an unverified temporary file as `latest.dump`.

## Release gate

For a production migration/release:

1. required CI/Admin/Batch checks must be green for the exact `main` SHA;
2. the deploy-created pre-migration archive must pass non-empty + `pg_restore --list` validation and receive its checksum;
3. Alembic may then upgrade to `head`;
4. production runtime must start `backup-worker` alongside app/workers;
5. post-release operations should confirm that a periodic `latest.dump` is produced and reaches the configured off-host durability layer;
6. restore drills must be performed regularly and recorded operationally.
