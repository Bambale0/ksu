# GitHub production deployment

`Deploy Production` (`.github/workflows/deploy-production.yml`) deploys the current `main` commit to the production Docker Compose host after the required main-branch checks are green.

## Trigger

Automatic deployment starts after the `CI` workflow completes successfully for a `push` to `main`.

The deployment then waits for all three production gates for the exact same commit:

- `CI`
- `Admin Console`
- `Batch Generation`

A manual `workflow_dispatch` is also available. Manual runs always resolve the current `main` HEAD; arbitrary historical SHAs are intentionally not accepted.

A completed CI run for an older commit cannot overwrite a newer production release: before SSH starts, the workflow compares the target SHA with the current `main` HEAD and skips superseded runs.

## Required GitHub Actions secrets

Create these in **Repository → Settings → Secrets and variables → Actions** (repository secrets or secrets available to the `production` environment):

| Secret | Required | Example / meaning |
|---|---:|---|
| `DEPLOY_HOST` | yes | production host name or IP |
| `DEPLOY_USER` | yes | unprivileged SSH deployment user |
| `DEPLOY_PATH` | yes | absolute path to the existing `ksu` clone, e.g. `/srv/ksu` |
| `DEPLOY_SSH_KEY` | yes | private SSH key used by GitHub Actions to connect to production |
| `DEPLOY_KNOWN_HOSTS` | yes | pinned OpenSSH host-key line(s) for the production host |
| `DEPLOY_PORT` | no | SSH port; defaults to `22` |

`DEPLOY_KNOWN_HOSTS` is required deliberately. The workflow does **not** trust an SSH key discovered dynamically during deployment.

Generate the pinned line from a trusted administration machine and verify the fingerprint out of band before saving it as a secret, for example:

```bash
ssh-keyscan -H -p 22 YOUR_HOST
```

Do not copy an unverified key from an intercepted network connection.

## Production host prerequisites

The deployment user must be able to:

1. SSH non-interactively using the configured key.
2. Read/write `DEPLOY_PATH`.
3. Run `git fetch origin main` inside the existing clone.
4. Run `docker compose` without an interactive sudo password.
5. Read the production `.env` file indirectly through Docker Compose; `.env` remains on the server and is not copied into GitHub Actions.
6. Write `DEPLOY_PATH/backups/`.

The existing clone must keep its own read access to the GitHub repository (for a private repository, use a server-side read-only deploy key or another narrowly scoped credential).

Do not give the GitHub Actions SSH key root access. Prefer a dedicated deployment user with only the Docker/repository permissions required by this application.

## What a deployment does

For the exact tested SHA the remote script performs:

```text
git fetch --prune origin main
git reset --hard <tested-main-sha>
docker compose config -q
docker compose up -d postgres redis
pg_dump -> backups/predeploy-<timestamp>-<sha>.dump
docker compose build app + all workers
docker compose run --rm app alembic upgrade head
docker compose up -d --remove-orphans app + all workers
```

Runtime services recreated by the workflow:

- `app`
- `generation-worker`
- `media-worker`
- `payment-worker`
- `creator-partnership-worker`

PostgreSQL and Redis volumes are not recreated. Pre-deploy dumps older than 14 days are pruned from the local `backups/` directory; production still needs an independent off-host backup policy.

## Post-deploy gates

The workflow waits for and verifies locally on the production host:

```text
GET http://127.0.0.1:8000/health/ready
GET http://127.0.0.1:8000/health/operational
GET http://127.0.0.1:8000/health/live
HEAD http://127.0.0.1:8000/mini-app/
```

If deployment fails after entering the repository, the workflow prints `docker compose ps` and the last 200 log lines from the application/workers into the GitHub Actions log.

There is intentionally no automatic database downgrade or blind code rollback after a failed migration. Production migrations are forward-only unless a reviewed recovery plan explicitly says otherwise.

## First activation

After the workflow is merged into `main`:

1. add the required GitHub Actions secrets;
2. confirm the server clone can `git fetch origin main` as `DEPLOY_USER`;
3. confirm `docker compose ps` works non-interactively for that user;
4. run **Actions → Deploy Production → Run workflow** once;
5. confirm the deployment summary and health checks are green.

After that, every successful push/merge to `main` is deployed automatically after all required checks for that same commit succeed.
