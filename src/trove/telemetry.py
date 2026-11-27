"""OpenTelemetry tracing with a no-op default.

Spans are only exported when an OTLP endpoint is configured through the
standard OpenTelemetry environment variables. The queue stores the W3C
``traceparent`` on each stage task so a worker can continue the HTTP trace in a
different process.
"""

from __future__ import annotations

import os
from collections.abc import Iterator, Mapping
from contextlib import contextmanager

from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.propagate import extract, inject
from opentelemetry.trace import Span, SpanKind, Status, StatusCode
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

_PROPAGATOR = TraceContextTextMapPropagator()
_CONFIGURED = False

DEFAULT_SERVICE_NAME = "trove"


def configure_tracing(*, span_exporter=None) -> bool:
    """Install the SDK exporter once; without an endpoint tracing stays no-op."""
    global _CONFIGURED
    if _CONFIGURED:
        return False
    endpoint = (
        os.environ.get("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")
        or os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
        or ""
    ).strip()
    if not endpoint and span_exporter is None:
        return False

    if span_exporter is None:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )

        url = endpoint.rstrip("/")
        if not url.endswith("/v1/traces"):
            url += "/v1/traces"
        span_exporter = OTLPSpanExporter(endpoint=url)

    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    service_name = os.environ.get("OTEL_SERVICE_NAME", DEFAULT_SERVICE_NAME)
    provider = TracerProvider(
        resource=Resource.create({"service.name": service_name})
    )
    provider.add_span_processor(BatchSpanProcessor(span_exporter))
    trace.set_tracer_provider(provider)
    _CONFIGURED = True
    return True


def tracer() -> trace.Tracer:
    return trace.get_tracer("trove")


def current_traceparent() -> str | None:
    carrier: dict[str, str] = {}
    inject(carrier)
    return carrier.get("traceparent")


def _parent_context(traceparent: str | None) -> Context | None:
    if not traceparent:
        return None
    return extract({"traceparent": traceparent})


@contextmanager
def span(
    name: str,
    *,
    attributes: Mapping[str, str | int | float | bool] | None = None,
    parent_traceparent: str | None = None,
    kind: SpanKind = SpanKind.INTERNAL,
) -> Iterator[Span]:
    with tracer().start_as_current_span(
        name,
        context=_parent_context(parent_traceparent),
        kind=kind,
        attributes=dict(attributes or {}),
    ) as current:
        try:
            yield current
        except Exception as exc:
            current.record_exception(exc)
            current.set_status(Status(StatusCode.ERROR, str(exc)))
            raise


@contextmanager
def http_server_span(
    method: str, headers: Mapping[str, str]
) -> Iterator[Span]:
    carrier = {key.lower(): value for key, value in headers.items()}
    with tracer().start_as_current_span(
        f"HTTP {method}",
        context=extract(carrier),
        kind=SpanKind.SERVER,
        attributes={"http.request.method": method},
    ) as current:
        yield current


def mark_error(span: Span, error: str) -> None:
    span.set_status(Status(StatusCode.ERROR, error))
