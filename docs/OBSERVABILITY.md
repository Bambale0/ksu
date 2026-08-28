# KSU observability runbook

**Status:** runtime contract for the observability stack implemented on 2026-08-12.

## Goals

The observability layer must answer four operational questions without exposing secrets or creating its own resource-consumption problem:

1. Is the API process alive and are PostgreSQL/Redis usable?
2. Are the generation, media and payment workers actually running?
3. Is paid generation, media delivery or payment reconciliation accumulating?
4. Can an operator correlate one request/provider operation across logs and traces?

## Health semantics

Use the endpoints for different purposes:

```text
GET /health/live         process liveness
GET /health/ready        API dependencies: PostgreSQL + Redis
GET /health/operational  generation-worker + media-worker + payment-worker heartbeats
```

`/health/operational` returning 503 is an **alert condition**, not a reason to restart an otherwise healthy API container. Keep orchestration readiness bound to `/health/ready`.

## Prometheus scrape

Endpoint:

```text
GET /metrics
```

Recommended production configuration:

```dotenv
METRICS_ENABLED=true
METRICS_BEARER_TOKEN=<random-monitoring-secret>
```

Scrape header when a token is configured:

```http
Authorization: Bearer <random-monitoring-secret>
```

Prefer also restricting `/metrics` to a private monitoring network at the reverse proxy/firewall.

Important series:

```text
ksu_http_requests_total{method,route,status}
ksu_http_request_duration_seconds{method,route}
ksu_generations{status}
ksu_generation_outbox{status}
ksu_generation_outbox_oldest_pending_seconds
ksu_media_assets{status}
ksu_media_ingest_jobs{status}
ksu_media_ingest_oldest_pending_seconds
ksu_payments{status}
ksu_worker_up{worker}
ksu_worker_heartbeat_age_seconds{worker}
ksu_distributed_event_count{event}
ksu_provider_circuit_open{provider}
ksu_resource_policy_events_total{code}
```

Do not add raw user IDs, Telegram IDs, payment IDs, generation IDs, media IDs, prompts, URLs or provider task IDs as Prometheus labels. Those are high-cardinality values and belong in logs/traces.

The API process refreshes database/Redis snapshot gauges when Prometheus scrapes `/metrics`. Worker event counts live in Redis because `generation-worker`, `media-worker`, `prompt-tool-worker` and `payment-worker` are separate processes and do not share the API process' in-memory Prometheus registry.

## Worker heartbeats

Redis keys:

```text
observability:worker:generation-worker:heartbeat
observability:worker:media-worker:heartbeat
observability:worker:prompt-tool-worker:heartbeat
observability:worker:payment-worker:heartbeat
```

Configuration:

```dotenv
WORKER_HEARTBEAT_TTL_SECONDS=180
WORKER_STALE_AFTER_SECONDS=120
```

Expected relationship:

```text
heartbeat TTL > stale-after threshold > normal worker loop/sleep interval
```

If a worker is intentionally stopped for maintenance, silence the corresponding alert rather than deleting/forging heartbeat keys.

## Cross-process event counters

Redis keys use:

```text
observability:event:<event>
```

Current bounded event names:

```text
generation_submit_success
generation_submit_failure
generation_reconcile_failure
generation_worker_loop_error
media_ingest_processed
music_audio_ingest_processed
music_audio_worker_loop_error
media_reconcile_failure
media_worker_loop_error
payment_reconcile_success
payment_reconcile_failure
payment_worker_loop_error
```

These are exposed as Prometheus gauges named `ksu_distributed_event_count` because Redis replacement/restore can reset them. Alert rules should use changes/deltas over a window rather than assuming they are permanent monotonic counters across infrastructure replacement.

## OpenTelemetry traces

Tracing is optional:

```dotenv
OTEL_ENABLED=false
OTEL_SERVICE_NAME=ksu
OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://otel-collector:4318/v1/traces
OTEL_TRACE_SAMPLE_RATIO=0.10
```

When enabled, logical service names are:

```text
ksu
ksu.generation-worker
ksu.media-worker
ksu.prompt-tool-worker
ksu.payment-worker
```

The API instruments FastAPI and HTTPX. Worker/provider calls can be correlated through structured logs and HTTP tracing. Per-operation identifiers belong in trace/log fields rather than metric labels.

Examples of trace/log-only identifiers:

```text
generation.id
generation.model_id
generation.provider
generation.outbox_attempt
media.asset_id
media.generation_id
payment.id
payment.provider
```

An unavailable OTLP collector must not become a product dependency. Keep tracing optional and route exports through a local/nearby collector when possible.

## Structured logs

Default:

```dotenv
LOG_LEVEL=INFO
JSON_LOGS=true
```

Each log record contains:

```text
timestamp
level
logger
message
request_id
trace_id
span_id
```

`X-Request-ID` is preserved when it matches the bounded safe format; otherwise the API generates a UUID. The same value is placed in the response and logging context.

Never log:

```text
Telegram initData
Authorization bearer tokens
admin session tokens
BOT_TOKEN
Kie/payment/S3 provider credentials
MFA secrets
recovery codes
payment requisites
raw sensitive provider payloads
presigned S3 query strings
```

## Baseline alerts

Repository rules:

```text
ops/prometheus-alerts.yml
```

They cover:

- stale worker heartbeats;
- old generation outbox work;
- old media-ingest work;
- Kie circuit open;
- payments stuck in `creation_unknown`;
- payments stuck in `refund_review`;
- elevated API 5xx ratio;
- increasing generation submission failures;
- increasing media worker failures;
- increasing payment reconciliation failures.

Treat these thresholds as production starting points. Tune them against real traffic and provider latency after launch; do not weaken security/accounting alerts merely to eliminate noise.

## Suggested dashboards

### API

- request rate by route template/status;
- p50/p95/p99 request duration;
- 4xx/5xx ratio;
- resource-policy denials by code.

### Generation

- generations by lifecycle state;
- outbox pending/processing count;
- oldest outbox age;
- Kie circuit state;
- submit success/failure event deltas;
- reconcile failure deltas.

### Media

- media assets by `pending` / `ready` / `failed`;
- ingest jobs by lifecycle state;
- oldest pending/processing ingest job age;
- media worker heartbeat;
- reconcile/worker-error event deltas.

### Payments

- payments by lifecycle state;
- `creation_unknown`, `pending`, `refund_review` counts;
- reconciliation success/failure deltas.

### Workers

- `ksu_worker_up`;
- heartbeat age;
- worker loop error deltas.

## Incident playbooks

### Worker down

1. Check `/health/operational` and `ksu_worker_up`.
2. Inspect Docker/container status and structured logs for the named worker.
3. Check Redis connectivity before assuming the process itself is dead.
4. For generation incidents, inspect PostgreSQL `generation_outbox`; paid work remains durable there.
5. For media incidents, inspect `media_ingest_jobs`; successful generation accounting remains intact while media delivery recovers.
6. Restart only the affected worker after identifying the immediate cause.

### Generation outbox backlog

1. Check generation-worker heartbeat.
2. Check Kie circuit/429/5xx state.
3. Check Redis protection-store availability.
4. Inspect oldest pending/processing outbox row and lease state.
5. Do not create a duplicate paid generation as repair.

### Media ingest backlog

1. Check media-worker heartbeat.
2. Verify S3 credentials, bucket, region/custom endpoint and network path.
3. Inspect the oldest `media_ingest_jobs` rows and their `last_error` values.
4. Check whether provider result URLs are returning 403/404 or have expired.
5. Do not mark the generation failed or refund it solely because durable-media copying is delayed.
6. Fix storage/network configuration and let the durable queue retry.

### Kie circuit open

1. Inspect recent provider transport/429/5xx errors.
2. Verify whether Kie itself is degraded or a local networking problem exists.
3. Let durable outbox items remain pending during the protection window.
4. Do not disable the circuit solely to force traffic into an unhealthy provider.

### Payment reconciliation failures

1. Check payment-worker heartbeat.
2. Inspect provider credentials/connectivity/status APIs.
3. Review payments in `creation_unknown`, `pending`, `refund_review`.
4. Use the authorized admin reconcile operation if necessary.
5. Never manually mark a payment successful or refunded as a monitoring workaround.

### Metrics scrape fails

1. Confirm `METRICS_ENABLED=true`.
2. Verify bearer token and reverse-proxy ACL.
3. Check PostgreSQL; DB snapshot refresh is part of the scrape.
4. Redis failures degrade worker/circuit/event snapshot values but should not erase PostgreSQL business state.

### OTLP export fails

1. Verify collector endpoint and network.
2. Inspect collector/exporter logs.
3. Keep product API/workers running; tracing is optional telemetry.
4. Use structured logs + Prometheus while collector service is restored.

## Deployment smoke checks

```bash
BASE=https://api.example.com
curl -fsS "$BASE/health/live"
curl -fsS "$BASE/health/ready"
curl -fsS "$BASE/health/operational"
curl -fsS -H "Authorization: Bearer $METRICS_BEARER_TOKEN" "$BASE/metrics" | head
```

After workers have started, all three `ksu_worker_up` series should be `1`. A fresh environment can briefly report operational 503 until each worker publishes its first heartbeat.

## External guidance

Implementation follows the current OpenTelemetry Python SDK/OTLP exporter guidance and Prometheus instrumentation guidance. Metric labels are deliberately bounded to avoid high-cardinality resource growth, while traces/logs carry per-operation debugging identifiers.
