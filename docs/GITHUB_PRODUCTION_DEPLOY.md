# GitHub production deployment

`Deploy Production` (`.github/workflows/deploy-production.yml`) deploys the current `main` commit to the production Docker Compose host only after the complete production gate is green for that exact SHA.

## Trigger and exact-SHA gate

Automatic deployment starts after the `CI` workflow completes successfully for a `push` to `main`.

The deployment then waits for all production gates for the exact same commit:

- `CI`
- `Admin Console`
- `Batch Generation`
- `Mini App Playwright E2E`
- `ROXY E2E`
- `ROXY Release Gate`

`ROXY Release Gate` runs for every `main` push so an otherwise valid production deployment cannot wait on a workflow skipped by path filters.

A manual `workflow_dispatch` is also available. Manual runs resolve the current `main` HEAD; arbitrary historical SHAs are intentionally not accepted.

Before SSH starts, the workflow compares the target SHA with current `main`. A completed workflow for an older commit cannot overwrite a newer production release.

**CI success alone is not proof of production delivery.** The deploy workflow must reach the host, pass its database/deployment gates, prove all production runtime services are running, prove every Python application process uses the exact immutable release image, and verify the exact Mini App release SHA. Missing required deployment secrets fails the workflow; incomplete SSH configuration never produces a successful no-op.

## Required GitHub Actions secrets

Create these in **Repository → Settings → Secrets and variables → Actions** (repository secrets or secrets available to the `production` environment):

| Secret | Required | Meaning |
|---|---:|---|
| `DEPLOY_HOST` | yes | production host name or IP |
| `DEPLOY_USER` | yes | unprivileged SSH deployment user |
| `DEPLOY_PATH` | yes | absolute path to the existing `ksu` clone |
| `DEPLOY_SSH_KEY` | yes | private SSH key for the deployment user |
| `DEPLOY_KNOWN_HOSTS` | yes | pinned OpenSSH host-key line(s) |
| `DEPLOY_PORT` | no | SSH port; defaults to `22` |

`DEPLOY_KNOWN_HOSTS` is required deliberately. The workflow does **not** trust a host key discovered dynamically during deployment.

Generate the candidate line from a trusted administration machine and verify the fingerprint out of band before saving it:

```bash
ssh-keyscan -H -p 22 YOUR_HOST
```

Do not give the Actions SSH key root access. Prefer a dedicated deployment user with only the Docker/repository permissions needed by ROXY.

## Production host prerequisites

The deployment user must be able to:

1. SSH non-interactively using the configured key.
2. Read/write `DEPLOY_PATH`.
3. Run `git fetch origin main` inside the existing clone.
4. Run `docker compose` without an interactive sudo password.
5. Let Docker Compose read the production `.env`; the file stays on the host and is not copied into Actions.
6. Write `DEPLOY_PATH/backups/` for the pre-migration archive/checksum.
7. Create/use the compose-managed `db_backups` Docker volume for periodic backups.
8. Keep an existing `ADMIN_SECURITY_KEY` of at least 32 characters in the host `.env`. The deploy validates it before changing the checkout and validates the running app afterward; it never generates, replaces, prints or changes permissions on credentials. Missing/short keys require a separate explicitly authorized operator setup.
9. Keep tracked files clean. Deployment stops on staged/unstaged changes or untracked/ignored paths that collide with the target release; operator work is never reset or cleaned automatically.

The server clone must keep its own read access to the GitHub repository.

## Immutable application image contract

`app` and every Python worker declare the same Compose image:

```text
ksu-app:${KSU_IMAGE_TAG:-local}
```

During production deployment the workflow exports `KSU_IMAGE_TAG=<tested-main-sha>`, builds `app` exactly once, and records the resulting Docker image ID. The same tag is then used by:

- `app`
- `generation-worker`
- `media-worker`
- `prompt-tool-worker`
- `payment-worker`
- `notification-worker`
- `admin-support-worker`
- `admin-campaign-worker`
- `creator-partnership-worker`

The containers are force-recreated. Before any API health gate can make the deployment green, Docker inspection must prove every service above is running **and** its `.Image` ID equals the image ID built for the release SHA.

This prevents the old split-brain failure mode where a new API container could coexist with a worker still running code from an older release.

`backup-worker` intentionally uses the official PostgreSQL image and is checked for runtime availability, not application-image identity.

## What a deployment does

For the exact tested SHA, the remote script performs:

```text
validate existing ADMIN_SECURITY_KEY without modifying .env
require a clean tracked worktree and index
git fetch --prune origin main
git checkout --detach --no-overwrite-ignore <tested-main-sha>
verify HEAD == <tested-main-sha>
write app/web/mini_app/release.json with <tested-main-sha>
export KSU_IMAGE_TAG=<tested-main-sha>
docker compose config -q
docker compose up -d postgres redis
pg_dump -Fc -> backups/predeploy-<timestamp>-<sha>.dump
require non-empty archive
pg_restore --list < predeploy dump
write SHA-256 sidecar
build one ksu-app:<tested-main-sha> image via the app service
record the immutable image ID
docker compose run --rm app alembic upgrade head
force-recreate all runtime services + backup-worker
require every runtime service to be running
require every Python application service to use the exact release image ID
```

Long-running services use `restart: unless-stopped`. `/health/operational` requires fresh heartbeats from generation, payment, media, prompt-tool, notification, admin-support, admin-campaign and creator-partnership workers.

PostgreSQL and Redis data volumes are not recreated. Ordinary deployment preserves all existing pre-deploy dumps/checksums in the host `backups/` directory and all existing release image tags. It creates and verifies a new release backup but does not apply age-based deletion or image pruning. The non-forced checkout preserves non-conflicting untracked/ignored `.env` and uploaded media; only the generated Mini App release marker is rewritten after the exact-SHA switch.

Periodic backups are kept separately in the private `db_backups` volume according to the existing `DB_BACKUP_RETENTION_COUNT` policy. This patch does not change the periodic backup worker or its retention settings.

Local retention is not off-host disaster recovery. See `DATABASE_BACKUPS.md` for periodic backup, restore-drill and off-host requirements.

## Post-deploy gates

The workflow verifies on the production host:

```text
every required runtime service is running
every Python application service has image ID == ksu-app:<tested-main-sha> image ID
APP_BASE=http://127.0.0.1:$(docker compose port app 8000 | awk -F: 'END {print $NF}')
GET $APP_BASE/health/ready
GET $APP_BASE/health/operational
GET $APP_BASE/health/live
HEAD $APP_BASE/mini-app/
HEAD $APP_BASE/admin-app/
GET $APP_BASE/mini-app/release.json == {"sha":"<tested-main-sha>"}
verify ADMIN_SECURITY_KEY is configured in the running app
```

The SHA check makes delivery observable: a green deployment means the running Mini App is serving the commit the workflow intended to deploy. The image-ID gate additionally proves that asynchronous workers are serving the same code.

Mini App responses use no-store/no-cache behavior so Telegram WebView cannot keep an old HTML/JS/CSS release indefinitely after a successful deployment.

If deployment fails after entering the repository, diagnostics include `docker compose ps` and recent logs for all current runtime services, including `backup-worker`.

There is intentionally no automatic database downgrade or blind code rollback after a failed migration. Alembic downgrade is never performed implicitly; prefer a reviewed forward fix or a controlled database restore/recovery plan.

## Separate explicit manual maintenance

Neither automatic deployment nor its manual `workflow_dispatch` runs historical media backfills, removes old release images, or deletes old pre-deploy archives/checksums. A release is not permission to do maintenance.

Maintenance requires a separate explicit operator decision covering the exact command, affected archives/images/records, recovery plan and intended scope. Before deleting anything, inventory disk usage, verify recoverable/off-host backups, and retain every release needed for rollback. There is deliberately no automatic pruning command in this workflow; disk capacity must be checked before deployment and managed separately.

The existing `scripts.backfill_reference_static` and `scripts.backfill_feed_static` modules remain packaged in the runtime image for separately approved manual use. They can download historical media and update stored URLs; `--limit` limits the scan and is not a dry-run option. Inspect the selected script and its current options before proposing a run. No backfill is implied by a healthy release, and no maintenance command is executed by these instructions.

## Backup-specific release evidence

A production release should leave evidence of two distinct protections:

1. **pre-migration boundary:** the deploy log says the pre-deploy custom archive was created and verified before Alembic;
2. **ongoing operations:** `backup-worker` is running and subsequently publishes a checksummed/parseable `/backups/latest.dump`.

The release workflow does not claim that the local Docker volume has been copied off-host. Off-host transfer/snapshot freshness must be verified by operations separately.

## First activation / recovery checks

After a deployment:

1. confirm free disk capacity for both `DEPLOY_PATH/backups/` and the Docker volume store;
2. confirm `docker compose ps` works non-interactively as `DEPLOY_USER`;
3. run **Actions → Deploy Production → Run workflow** if an explicit deployment is needed;
4. confirm all six exact-SHA workflow gates are green;
5. confirm the pre-migration archive validation, all-runtime-service check, immutable image-ID parity, API health checks and Mini App SHA check are green;
6. verify `/backups/latest.dump` checksum/catalog after the worker completes its first backup;
7. confirm old pre-deploy backups and rollback image tags remain present; schedule any needed maintenance as a separate explicitly approved task;
8. confirm the verified backup reaches the configured encrypted off-host durability layer.
