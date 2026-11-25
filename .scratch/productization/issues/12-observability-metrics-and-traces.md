# 12 — 指标与追踪：Prometheus + OpenTelemetry

Status: ready-for-agent
Type: task
Milestone: P3
Blocked by: 08
Spec: [spec.md](../spec.md)

## Context

已有 JSON 日志（带 `run_id`/`item_id`/`duration_ms`）和 `/api/health`，但没有聚合指标和 trace。产品化后需要回答：队列多深、哪个 stage 慢、失败码分布、ASR 实时率、LLM 花了多少 token/钱、搜索 p95 多少。没有这些数据，Phase 3 验收和容量规划只能靠感觉。

## Scope

- 指标（Prometheus 文本格式 `/metrics`，默认只绑定 loopback/内部网络）：
  - `trove_stage_duration_seconds{stage,outcome}` histogram。
  - `trove_stage_failures_total{stage,code}` counter。
  - `trove_stage_retries_total{stage}`、`trove_stage_dead_total{stage}`。
  - `trove_queue_depth{stage}` gauge。
  - `trove_worker_lease_age_seconds` gauge（最老 running task）。
  - `trove_asr_realtime_factor` histogram。
  - `trove_llm_tokens_total{kind}`、`trove_llm_cost_usd_total`。
  - `trove_search_duration_seconds`、`trove_search_results` histogram。
  - `trove_http_request_duration_seconds{method,route,status}`（route 用模板，不用原始 URL）。
- 指标标签禁止高基数：不放 `item_id`/`run_id`/`query`/`path` 原值。
- Trace（OpenTelemetry）：
  - HTTP 请求 span；stage 执行 span；LLM/ASR/搜索 adapter span。
  - 属性放 `run_id`/`item_id`/`stage`（span attribute，不是 metric label）。
  - 传播 `traceparent`；默认导出到 OTLP endpoint，未配置时 no-op。
- 在 stage executor、队列、adapter 边界统一埋点，避免每个业务函数重复加。
- 提供 Grafana dashboard JSON（`docs/observability/trove-dashboard.json`）和最少说明：四个黄金信号、阶段耗时、队列、ASR/LLM 成本。
- 文档：`docs/observability.md`，写清端点、鉴权、采集配置、标签规范。

## Acceptance Criteria

- [ ] `/metrics` 可访问，包含上述指标；无高基数标签。
- [ ] 一条完整 Item 处理后，能看到各 stage 的耗时、成功/失败、队列深度变化。
- [ ] 一个 trace 能串起 HTTP → 队列 → stage → adapter；未配置 OTLP 时不影响运行。
- [ ] Grafana dashboard 可导入，至少展示四个黄金信号。
- [ ] ASR RTF、LLM tokens/cost、搜索延迟可从指标读出。
- [ ] 指标命名/标签有测试或快照，防止后续随意改名。
- [ ] 指标端点不泄露密码、token、URL 查询参数或 Item 文本。
- [ ] `ruff`、`mypy`、现有测试通过。

## Testing

- 单测：指标注册/标签；route 模板化；no-op tracer。
- 集成：host seam 跑一条 Item，断言关键指标出现。
- 安全：`/metrics` 默认不公开；检查日志/指标无敏感值。
- 手动：导入 Grafana dashboard，确认面板有数据。

## Out of Scope

- 托管监控、告警路由、日志聚合（Loki/ELK）。
- 每个 adapter 的深度自定义指标；先覆盖 stage 和关键外部调用。
- 用指标做自动扩缩容。

## Notes

- 先加 `prometheus-client` 和 `opentelemetry-sdk` 两个依赖；不要引入整套 agent。
- 指标初始化要幂等，测试里重复创建 app 不能重复注册。
- `/metrics` 在 Docker 内网可访问；如果绑定公网，必须加认证或只暴露给采集器。
