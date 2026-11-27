# Observability

Trove exposes Prometheus metrics from the API and worker processes and emits
OpenTelemetry traces when an OTLP endpoint is configured. Both are optional:
without an exporter the trace API stays no-op and request processing is
unchanged.

## Metrics endpoints

| Process | URL | Authentication |
| --- | --- | --- |
| API and web shell | `http://127.0.0.1:8765/metrics` | Same cookie or device token as the rest of the API |
| Worker | `http://127.0.0.1:8766/metrics` | None; bind only to loopback or a trusted internal network |

The API and worker run in separate processes, so Prometheus must scrape both.
Metrics are process-local; the API endpoint does not proxy worker metrics.

`/metrics` is not a public path. Authenticate with a device token (bearer) or a
signed-in cookie. To issue a read-only scrape token:

```bash
curl -sS -X POST http://127.0.0.1:8765/api/auth/device-token \
  -H 'Content-Type: application/json' \
  -d '{"password":"<host-password>","name":"prometheus"}'
```

Prometheus configuration:

```yaml
scrape_configs:
  - job_name: trove-api
    metrics_path: /metrics
    authorization:
      credentials: "<token from the response>"
    static_configs:
      - targets: ["127.0.0.1:8765"]

  - job_name: trove-worker
    metrics_path: /metrics
    static_configs:
      - targets: ["127.0.0.1:8766"]
```

In Docker Compose, scrape `api:8765` with a token and `worker:8766` over the
internal network. Do not publish the worker metrics port. On a Host exposed
through Tailscale or Caddy, keep the API endpoint behind auth or expose only the
scrape path to the collector.

The worker listener follows `[server] host` and uses
`[metrics] worker_port` (default `8766`). Disable it with:

```toml
[metrics]
enabled = false
```

## Metric families

| Metric | Type | Labels | Meaning |
| --- | --- | --- | --- |
| `trove_stage_duration_seconds` | histogram | `stage`, `outcome` | Stage wall-clock time; `outcome` is `success`, `failure`, `cancelled`, or `skipped` |
| `trove_stage_failures_total` | counter | `stage`, `code` | Failed attempts by stable error code |
| `trove_stage_retries_total` | counter | `stage` | Attempts requeued by policy or lease expiry |
| `trove_stage_dead_total` | counter | `stage` | Attempts that exhausted their budget |
| `trove_queue_depth` | gauge | `stage` | Ready queued tasks |
| `trove_worker_lease_age_seconds` | gauge | — | Age of the oldest running task |
| `trove_asr_realtime_factor` | histogram | — | ASR seconds per audio second |
| `trove_llm_tokens_total` | counter | `kind` | Actual input/output tokens from organization calls |
| `trove_llm_cost_usd_total` | counter | — | Estimated organization cost |
| `trove_search_duration_seconds` | histogram | — | Search request duration |
| `trove_search_results` | histogram | — | Items returned per search |
| `trove_http_request_duration_seconds` | histogram | `method`, `route`, `status` | HTTP latency by route template |
| `trove_external_cache_hits_total` | counter | `cache` | External calls avoided by package cache |
| `trove_external_cache_misses_total` | counter | `cache` | Cache misses that called ASR/LLM |
| `trove_external_cache_saved_asr_seconds_total` | counter | — | Audio seconds not transcribed |
| `trove_external_cache_saved_tokens_total` | counter | `kind` | LLM tokens not spent |
| `trove_external_cache_saved_cost_usd_total` | counter | — | Estimated LLM cost avoided |

### Label rules

- Allowed metric labels are bounded: stage names, outcomes, stable error codes,
  HTTP methods, route templates, status codes, token kinds, and cache names.
- Never use `run_id`, `item_id`, `request_id`, a search query, a raw URL, a file
  path, or Item text as a metric label.
- `route` is always the framework route template, such as
  `/api/items/{item_id}`, never the concrete path.
- Identifiers belong on trace span attributes (`trove.run_id`,
  `trove.item_id`), where cardinality does not break Prometheus.

## Traces

Tracing is enabled only when an OTLP HTTP endpoint is configured:

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4318
# Optional; the exporter appends /v1/traces when it is missing.
# export OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://127.0.0.1:4318/v1/traces
export OTEL_SERVICE_NAME=trove
```

Set the same variables for the API and worker (including the Docker Compose
services). If no endpoint is set, spans are no-op and no network connection is
attempted. Exporter failures are handled by the SDK and do not fail requests or
stage tasks.

Span structure:

```text
HTTP GET
└── queue.enqueue
    └── stage transcribing
        └── trove.asr.transcribe
```

- Incoming W3C `traceparent` headers are honored.
- `queue.enqueue` stores the current `traceparent` on the stage task. A worker
  in another process extracts it, so the stage span joins the original HTTP
  trace.
- The stage span carries `trove.run_id`, `trove.item_id`, and `trove.stage`.
- Adapter spans cover `trove.asr.transcribe`, `trove.llm.organize`, and
  `trove.search`.

## Grafana

Import [trove-dashboard.json](observability/trove-dashboard.json) into Grafana
and select the Prometheus data source. The dashboard covers the four golden
signals plus stage latency, queue depth, retries/dead letters, ASR RTF, LLM
tokens/cost, and search latency.

## Operator checks

1. `curl -H "Authorization: Bearer <token>" http://127.0.0.1:8765/metrics`
   returns Prometheus text.
2. `curl http://127.0.0.1:8766/metrics` works only from the Host or its internal
   Docker network.
3. Run one Item end to end and confirm `trove_stage_duration_seconds_count`
   increases for every stage.
4. Queue an Item without starting a worker and confirm
   `trove_queue_depth{stage="downloading"} 1`.
5. With OTLP configured, search the collector for one trace containing the HTTP
   request, `queue.enqueue`, a stage span, and its adapter span.
