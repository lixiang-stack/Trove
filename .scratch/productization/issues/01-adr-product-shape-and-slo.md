# 01 — ADR 0014：单租户自托管产品形态与 SLO

Status: resolved
Type: task
Milestone: P0
Blocked by: none
Spec: [spec.md](../spec.md)
ADRs: [0001](../../../docs/adr/0001-python-monolith-sqlite-worker.md), [0008](../../../docs/adr/0008-content-package-as-source-of-truth.md)

## Context

产品化讨论已经确定：Trove 是单租户自托管 Host，不做多租户 SaaS；核心保持 Python，不做 Go 重写；服务化按处理阶段和资源类型推进。需要把这些决定固化成 ADR，并定义可验证的 SLO，避免后续反复讨论或无意中引入多租户/微服务复杂度。

## Scope

- 新增 `docs/adr/0014-single-tenant-self-hosted-python.md`，状态 `Accepted`，日期 `2026-11-25`。
- 记录 spec 中的 D1–D10：单租户、Python、阶段分池、抽取顺序、不做 Go、内容包事实源、SQLite、API v1、Docker 一等交付、契约后替换实现。
- 定义初始 SLO 表：测量方法、目标值、参考硬件、校准时机。
- 明确非目标：多租户、Go 重写、K8s/Kafka/Redis/Celery、立即替换 FTS5、改内容包布局。
- 记录语言决策的触发条件：只有满足 spec“语言决策”中的条件，才评估单个独立服务的实现语言，不重写核心。
- 在 `docs/agents/code-map.md` 的 Layers/HTTP surface 附近加一行指向 spec 和 ADR，方便后续 agent 找到路线。

## Acceptance Criteria

- [x] ADR 文件存在，包含 Status、Date、Context、Decision、Consequences、Alternatives。
- [x] ADR 明确写出“单租户自托管”和“Python 核心，不做 Go 重写”，并解释原因。
- [x] SLO 表包含指标、目标、测量方式；所有目标都能从日志/指标/基准测试得到。
- [x] 非目标清单完整，和 spec 一致。
- [x] 语言重评触发条件明确，且限定为“单个服务试点”，不是全量重写。
- [x] `python3 scripts/check-docs.py` 通过；所有相对链接有效。
- [x] ADR 已提交，等待用户 review。

## Testing

- 文档检查：`python3 scripts/check-docs.py`。
- 人工检查：ADR 与 spec 的 D1–D10、Non-Goals、语言决策逐条对应，无矛盾。
- 检查链接：ADR 引用 ADR-0001/0008、spec、deployment 文档均存在。

## Out of Scope

- 实现任何架构改动。
- 修改现有 ADR-0001/0008 的正文；新 ADR 只做补充和收敛。
- 多租户/计费/配额设计。

## Notes

- ADR 编号接在 0013 之后；如果仓库已有 0014，使用下一个可用编号并在 spec 中同步。
- SLO 是初始目标，Phase 3 验收时用真实数据校准；不在本 issue 调整代码。

## Implementation

- 新增 `docs/adr/0014-single-tenant-self-hosted-python.md`，记录 D1–D10、SLO、非目标和语言重评触发条件。
- `docs/agents/code-map.md` 增加 Productization roadmap 段，链接 spec、ADR 和 API contract。
- 未改动运行时代码；`python3 scripts/check-docs.py` 通过。
