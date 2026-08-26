# ROXY release integrity

Production must never run a mixture of application revisions.

## Release invariant

`app`, `generation-worker`, `media-worker`, `payment-worker`, `notification-worker`, `admin-campaign-worker`, `prompt-tool-worker`, and `creator-partnership-worker` are one release unit. Every one of those services must run the same `ksu-app:<git SHA>` image built for the exact `main` commit being deployed.

A production deployment is successful only when all of the following are true:

1. CI, Admin Console, Batch Generation, Mini App Playwright E2E, ROXY E2E, and ROXY Release Gate have completed successfully for the exact target SHA.
2. The target SHA is still `main` HEAD when deployment begins.
3. The pre-migration PostgreSQL backup is non-empty and readable by `pg_restore --list`.
4. One application image is built as `ksu-app:<target SHA>`.
5. All Python application services are force-recreated from that image.
6. Docker reports the exact same image ID for every Python application service.
7. `/health/ready` succeeds.
8. `/health/operational` reports a fresh heartbeat for every long-running Python worker.
9. `/mini-app/release.json` contains the target SHA.
10. `backup-worker` is running.

If any invariant fails, the release is failed even if the customer-facing `app` container itself is responsive.

## Worker health

The canonical application/worker lists live in `app/core/runtime_services.py`. Compose, deploy, and operational health are regression-tested against that contract. Workers without their own frequent heartbeat are launched through `app.workers.heartbeat_runner`.

A worker must not be removed from operational health simply to make a deployment green. Fix the worker or its heartbeat instead.

## Legacy media backfills

Reference/feed backfills run after the application health gate. Some pre-durable-media provider URLs can be permanently expired. A backfill reporting `failed=N` is therefore reported as partial maintenance rather than silently described as a clean backfill. These failures must be investigated separately; they do not prove that the newly deployed runtime is unhealthy.

## Incident check

For a suspected split release, compare the running image ID of every application service:

```bash
export KSU_IMAGE_TAG="$(git rev-parse HEAD)"
expected="$(docker image inspect "ksu-app:${KSU_IMAGE_TAG}" --format '{{.Id}}')"
for service in app generation-worker media-worker payment-worker notification-worker admin-campaign-worker prompt-tool-worker creator-partnership-worker; do
  cid="$(docker compose ps -q "$service")"
  actual="$(docker inspect "$cid" --format '{{.Image}}')"
  printf '%-28s %s\n' "$service" "$actual"
  test "$actual" = "$expected"
done
```

Do not treat a green `/health/ready` as proof of release integrity; it intentionally checks only the API dependencies. `/health/operational` plus the image-ID invariant is the production runtime gate.
