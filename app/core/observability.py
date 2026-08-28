from __future__ import annotations

import contextvars
import logging
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from prometheus_client import Counter, Gauge, Histogram
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.media_models import MediaAsset, MediaIngestJob
from app.db.models import Generation, Payment
from app.db.reliability_models import GenerationOutbox

logger = logging.getLogger(__name__)

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id",
    default=None,
)

HTTP_REQUESTS = Counter(
    "ksu_http_requests_total",
    "HTTP requests handled by the application",
    ("method", "route", "status"),
)
HTTP_DURATION = Histogram(
    "ksu_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ("method", "route"),
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120),
)
RESOURCE_POLICY_EVENTS = Counter(
    "ksu_resource_policy_events_total",
    "Resource-policy denials/degraded events",
    ("code",),
)
GENERATION_EVENTS = Counter(
    "ksu_generation_events_total",
    "Generation lifecycle events",
    ("event", "provider"),
)
PAYMENT_EVENTS = Counter(
    "ksu_payment_events_total",
    "Payment lifecycle events",
    ("event", "provider"),
)
PAYMENT_REVERSAL_RUB = Counter(
    "ksu_payment_reversal_rub_total",
    "Provider-confirmed payment reversals in RUB",
    ("provider",),
)
WORKER_LOOP_ERRORS = Counter(
    "ksu_worker_loop_errors_total",
    "Unhandled worker loop errors",
    ("worker",),
)
GENERATION_STATE = Gauge(
    "ksu_generations",
    "Current generation rows by lifecycle state",
    ("status",),
)
OUTBOX_STATE = Gauge(
    "ksu_generation_outbox",
    "Current generation outbox rows by lifecycle state",
    ("status",),
)
OUTBOX_OLDEST_SECONDS = Gauge(
    "ksu_generation_outbox_oldest_pending_seconds",
    "Age of the oldest pending/processing generation outbox row",
)
PAYMENT_STATE = Gauge(
    "ksu_payments",
    "Current payment rows by lifecycle state",
    ("status",),
)
MEDIA_ASSET_STATE = Gauge(
    "ksu_media_assets",
    "Current product-owned media assets by lifecycle state",
    ("status",),
)
MEDIA_INGEST_STATE = Gauge(
    "ksu_media_ingest_jobs",
    "Current durable media ingest jobs by lifecycle state",
    ("status",),
)
MEDIA_INGEST_OLDEST_SECONDS = Gauge(
    "ksu_media_ingest_oldest_pending_seconds",
    "Age of the oldest pending/processing media ingest job",
)
WORKER_UP = Gauge(
    "ksu_worker_up",
    "Whether the worker heartbeat is within the configured stale threshold",
    ("worker",),
)
WORKER_HEARTBEAT_AGE = Gauge(
    "ksu_worker_heartbeat_age_seconds",
    "Age of the most recent worker heartbeat",
    ("worker",),
)
DISTRIBUTED_EVENTS = Gauge(
    "ksu_distributed_event_count",
    "Cross-process event count stored in Redis",
    ("event",),
)
PROVIDER_CIRCUIT_OPEN = Gauge(
    "ksu_provider_circuit_open",
    "Whether a provider resource-protection circuit is open",
    ("provider",),
)

DISTRIBUTED_EVENT_NAMES = (
    "generation_submit_success",
    "generation_submit_failure",
    "generation_reconcile_failure",
    "generation_worker_loop_error",
    "payment_reconcile_success",
    "payment_reconcile_failure",
    "payment_worker_loop_error",
    "media_ingest_processed",
    "music_audio_ingest_processed",
    "music_audio_worker_loop_error",
    "media_reconcile_failure",
    "media_worker_loop_error",
)

_tracer_provider: TracerProvider | None = None
_httpx_instrumented = False


def current_trace_fields() -> dict[str, str]:
    span = trace.get_current_span()
    context = span.get_span_context()
    if not context.is_valid:
        return {"trace_id": "", "span_id": ""}
    return {
        "trace_id": format(context.trace_id, "032x"),
        "span_id": format(context.span_id, "016x"),
    }


def configure_telemetry(app: FastAPI) -> None:
    global _tracer_provider, _httpx_instrumented
    if not settings.otel_enabled or _tracer_provider is not None:
        return

    ratio = min(1.0, max(0.0, float(settings.otel_trace_sample_ratio)))
    provider = TracerProvider(
        resource=Resource.create(
            {
                "service.name": settings.otel_service_name,
                "service.version": "0.1.0",
                "deployment.environment.name": settings.app_env,
            }
        ),
        sampler=ParentBased(TraceIdRatioBased(ratio)),
    )
    endpoint = settings.otel_exporter_otlp_traces_endpoint.strip()
    if endpoint:
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    else:
        logger.warning("OTEL_ENABLED is true but OTEL_EXPORTER_OTLP_TRACES_ENDPOINT is empty")

    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(
        app,
        tracer_provider=provider,
        excluded_urls="health/live,health/ready,health/operational,metrics",
    )
    if not _httpx_instrumented:
        HTTPXClientInstrumentor().instrument(tracer_provider=provider)
        _httpx_instrumented = True
    _tracer_provider = provider


def shutdown_telemetry() -> None:
    global _tracer_provider
    if _tracer_provider is not None:
        _tracer_provider.shutdown()
        _tracer_provider = None


def heartbeat_key(worker: str) -> str:
    return f"observability:worker:{worker}:heartbeat"


async def record_worker_heartbeat(redis: Redis, worker: str) -> None:
    now = time.time()
    await redis.set(
        heartbeat_key(worker),
        str(now),
        ex=max(settings.worker_heartbeat_ttl_seconds, settings.worker_stale_after_seconds + 1),
    )


async def worker_health(redis: Redis, worker: str) -> dict[str, Any]:
    raw = await redis.get(heartbeat_key(worker))
    if raw is None:
        WORKER_UP.labels(worker=worker).set(0)
        WORKER_HEARTBEAT_AGE.labels(worker=worker).set(float("inf"))
        return {"worker": worker, "up": False, "age_seconds": None}
    try:
        recorded = float(raw)
    except (TypeError, ValueError):
        WORKER_UP.labels(worker=worker).set(0)
        return {"worker": worker, "up": False, "age_seconds": None}
    age = max(0.0, time.time() - recorded)
    up = age <= settings.worker_stale_after_seconds
    WORKER_UP.labels(worker=worker).set(1 if up else 0)
    WORKER_HEARTBEAT_AGE.labels(worker=worker).set(age)
    return {"worker": worker, "up": up, "age_seconds": round(age, 3)}


async def record_distributed_event(redis: Redis, event: str) -> int:
    if event not in DISTRIBUTED_EVENT_NAMES:
        raise ValueError(f"Unknown distributed observability event: {event}")
    key = f"observability:event:{event}"
    value = int(await redis.incr(key))
    DISTRIBUTED_EVENTS.labels(event=event).set(value)
    return value


async def refresh_snapshot_metrics(session: AsyncSession, redis: Redis) -> None:
    generation_rows = list(
        (
            await session.execute(
                select(Generation.status, func.count()).group_by(Generation.status)
            )
        ).all()
    )
    for status_name in (
        "queued",
        "retry",
        "submitting",
        "generating",
        "succeeded",
        "failed",
    ):
        GENERATION_STATE.labels(status=status_name).set(0)
    for status_name, count in generation_rows:
        GENERATION_STATE.labels(status=str(status_name)).set(int(count))

    outbox_rows = list(
        (
            await session.execute(
                select(GenerationOutbox.status, func.count()).group_by(GenerationOutbox.status)
            )
        ).all()
    )
    for status_name in ("pending", "processing", "completed", "failed"):
        OUTBOX_STATE.labels(status=status_name).set(0)
    for status_name, count in outbox_rows:
        OUTBOX_STATE.labels(status=str(status_name)).set(int(count))

    oldest = await session.scalar(
        select(func.min(GenerationOutbox.created_at)).where(
            GenerationOutbox.status.in_(("pending", "processing"))
        )
    )
    if oldest is None:
        OUTBOX_OLDEST_SECONDS.set(0)
    else:
        if oldest.tzinfo is None:
            oldest = oldest.replace(tzinfo=timezone.utc)
        OUTBOX_OLDEST_SECONDS.set(
            max(0.0, (datetime.now(timezone.utc) - oldest).total_seconds())
        )

    payment_rows = list(
        (
            await session.execute(
                select(Payment.status, func.count()).group_by(Payment.status)
            )
        ).all()
    )
    for status_name in (
        "creating",
        "creation_unknown",
        "pending",
        "succeeded",
        "partially_refunded",
        "refunded",
        "refund_review",
        "canceled",
        "expired",
        "failed",
    ):
        PAYMENT_STATE.labels(status=status_name).set(0)
    for status_name, count in payment_rows:
        PAYMENT_STATE.labels(status=str(status_name)).set(int(count))

    media_asset_rows = list(
        (
            await session.execute(
                select(MediaAsset.status, func.count()).group_by(MediaAsset.status)
            )
        ).all()
    )
    for status_name in ("pending", "ready", "failed"):
        MEDIA_ASSET_STATE.labels(status=status_name).set(0)
    for status_name, count in media_asset_rows:
        MEDIA_ASSET_STATE.labels(status=str(status_name)).set(int(count))

    media_job_rows = list(
        (
            await session.execute(
                select(MediaIngestJob.status, func.count()).group_by(MediaIngestJob.status)
            )
        ).all()
    )
    for status_name in ("pending", "processing", "completed", "failed"):
        MEDIA_INGEST_STATE.labels(status=status_name).set(0)
    for status_name, count in media_job_rows:
        MEDIA_INGEST_STATE.labels(status=str(status_name)).set(int(count))

    media_oldest = await session.scalar(
        select(func.min(MediaIngestJob.created_at)).where(
            MediaIngestJob.status.in_(("pending", "processing"))
        )
    )
    if media_oldest is None:
        MEDIA_INGEST_OLDEST_SECONDS.set(0)
    else:
        if media_oldest.tzinfo is None:
            media_oldest = media_oldest.replace(tzinfo=timezone.utc)
        MEDIA_INGEST_OLDEST_SECONDS.set(
            max(0.0, (datetime.now(timezone.utc) - media_oldest).total_seconds())
        )

    for worker in ("generation-worker", "payment-worker", "media-worker", "prompt-tool-worker"):
        await worker_health(redis, worker)

    for event in DISTRIBUTED_EVENT_NAMES:
        value = int(await redis.get(f"observability:event:{event}") or 0)
        DISTRIBUTED_EVENTS.labels(event=event).set(value)

    circuit_ttl = await redis.ttl("abuse:circuit:kie:open")
    PROVIDER_CIRCUIT_OPEN.labels(provider="kie").set(1 if circuit_ttl and circuit_ttl > 0 else 0)
