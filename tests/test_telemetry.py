from __future__ import annotations

from opentelemetry import trace
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from trove import telemetry

INCOMING_TRACE_ID = "0af7651916cd43dd8448eb211c80319c"
INCOMING_SPAN_ID = "b7ad6b7169203331"
INCOMING_TRACEPARENT = f"00-{INCOMING_TRACE_ID}-{INCOMING_SPAN_ID}-01"


def test_tracing_is_noop_without_an_endpoint(monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", raising=False)

    assert telemetry.configure_tracing() is False
    with telemetry.span("noop") as span:
        assert telemetry.current_traceparent() is None
        assert span.get_span_context().is_valid is False


def test_http_queue_stage_and_adapter_spans_share_one_trace():
    exporter = InMemorySpanExporter()
    assert telemetry.configure_tracing(span_exporter=exporter) is True
    assert telemetry.configure_tracing(span_exporter=exporter) is False

    with telemetry.http_server_span(
        "GET", {"traceparent": INCOMING_TRACEPARENT}
    ) as server_span:
        queued_traceparent = telemetry.current_traceparent()
        assert queued_traceparent is not None
        with (
            telemetry.span(
                "stage transcribing",
                parent_traceparent=queued_traceparent,
                attributes={"trove.stage": "transcribing"},
            ),
            telemetry.span("trove.asr.transcribe"),
        ):
            pass

    provider = trace.get_tracer_provider()
    assert provider.force_flush()  # type: ignore[attr-defined]
    spans = {span.name: span for span in exporter.get_finished_spans()}
    server = spans["HTTP GET"]
    stage = spans["stage transcribing"]
    adapter = spans["trove.asr.transcribe"]

    assert {span.context.trace_id for span in spans.values()} == {
        int(INCOMING_TRACE_ID, 16)
    }
    assert server_span.get_span_context().trace_id == int(INCOMING_TRACE_ID, 16)
    assert stage.parent is not None
    assert stage.parent.span_id == server.context.span_id
    assert adapter.parent is not None
    assert adapter.parent.span_id == stage.context.span_id
    assert stage.attributes["trove.stage"] == "transcribing"
