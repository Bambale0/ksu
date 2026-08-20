# GitHub production deployment

`Deploy Production` (`.github/workflows/deploy-production.yml`) deploys the current `main` commit to the production Docker Compose host only after the required main-branch checks are green.

## Trigger and exact-SHA gate

Automatic deployment starts after the `CI` workflow completes successfully for a `push` to `main`.

The deployment then waits for all three production gates for the exact same commit:

- `CI`
- `Admin Console`
- `Batch Generation`

A manual `workflow_dispatch` is also available. Manual runs resolve the current `main` HEAD; arbitrary historical SHAs are intentionally not accepted.

Before SSH starts, the workflow compares the target SHA with current `main`. A completed workflow for an older commit cannot overwrite a newer production release.

**CI success is not proof of production delivery.** The deploy workflow must reach the host, pass its database/deployment gates and verify the exact Mini App release SHA. Missing required deployment secrets fails the workflow; incomplete SSH configuration never produces a successful no-op.

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

The server clone must keep its own read access to the GitHub repository (for a private repo, use a narrowly scoped server-side read credential/deploy key).

## What a deployment does

For the exact tested SHA, the remote script performs:

```text
git fetch --prune origin main
git reset --hard <tested-main-sha>
write app/web/mini_app/release.json with <tested-main-sha>
docker compose config -q
docker compose up -d postgres redis
pg_dump -Fc -> backups/predeploy-<timestamp>-<sha>.dump
require non-empty archive
pg_restore --list < predeploy dump
write SHA-256 sidecar
docker compose build application-backed services
docker compose run --rm app alembic upgrade head
docker compose up -d --remove-orphans runtime services + backup-worker
require backup-worker to be running
```

Application images built by the workflow:

- `app`
- `generation-worker`
- `media-worker`
- `payment-worker`
- `creator-partnership-worker`

Runtime services explicitly started/recreated:

- `app`
- `generation-worker`
- `media-worker`
- `payment-worker`
- `creator-partnership-worker`
- `backup-worker`

`backup-worker` uses the official PostgreSQL image rather than the application Dockerfile, so it is intentionally a runtime service but not part of the application build list.

PostgreSQL and Redis data volumes are not recreated. Pre-deploy dumps/checksums older than 14 days are pruned from the host `backups/` directory. Periodic backups are kept separately in the private `db_backups` volume according to `DB_BACKUP_RETENTION_COUNT`.

Local retention is not off-host disaster recovery. See `DATABASE_BACKUPS.md` for periodic backup, restore-drill and off-host requirements.

## Post-deploy gates

The workflow verifies on the production host:

```text
backup-worker is running
APP_BASE=http://127.0.0.1:$(docker compose port app 8000 | awk -F: 'END {print $NF}')
GET $APP_BASE/health/ready
GET $APP_BASE/health/operational
GET $APP_BASE/health/live
HEAD $APP_BASE/mini-app/
GET $APP_BASE/mini-app/release.json == {"sha":"<tested-main-sha>"}
```

The SHA check makes delivery observable: a green deployment means the running Mini App is serving the commit the workflow intended to deploy, not merely that an API process answers.

Mini App responses use no-store/no-cache behavior so Telegram WebView cannot keep an old HTML/JS/CSS release indefinitely after a successful deployment.

If deployment fails after entering the repository, diagnostics include `docker compose ps` and recent logs for the current runtime services, including `backup-worker`.

There is intentionally no automatic database downgrade or blind code rollback after a failed migration. Alembic downgrade is never performed implicitly; prefer a reviewed forward fix or a controlled database restore/recovery plan.

## Backup-specific release evidence

A production release should leave evidence of two distinct protections:

1. **pre-migration boundary:** the deploy log says the pre-deploy custom archive was created and verified before Alembic;
2. **ongoing operations:** `backup-worker` is running and subsequently publishes a checksummed/parseable `/backups/latest.dump`.

The release workflow does not claim that the local Docker volume has been copied off-host. Off-host transfer/snapshot freshness must be verified by operations separately.

## First activation / recovery checks

After backup-worker support is merged into `main`:

1. ensure production `.env` accepts the defaults or explicitly sets `DB_BACKUP_INTERVAL_SECONDS`, `DB_BACKUP_RETENTION_COUNT`, `DB_BACKUP_ON_START`;
2. confirm free disk capacity for both `DEPLOY_PATH/backups/` and the Docker volume store;
3. confirm `docker compose ps` works non-interactively as `DEPLOY_USER`;
4. run **Actions → Deploy Production → Run workflow** if an explicit deployment is needed;
5. confirm the pre-migration archive validation, backup-worker running check, API health checks and Mini App SHA check are green;
6. verify `/backups/latest.dump` checksum/catalog after the worker completes its first backup;
7. confirm the verified backup reaches the configured encrypted off-host durability layer.
