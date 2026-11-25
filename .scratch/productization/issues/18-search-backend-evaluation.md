# 18 — 搜索后端评估门禁（gated）

Status: needs-triage
Type: research
Milestone: P4
Blocked by: 06, 12
Spec: [spec.md](../spec.md)
ADRs: [0003](../../../docs/adr/0003-sqlite-fts5-cjk-search.md)

## Context

当前搜索是 SQLite FTS5 + CJK 归一化 + bm25/启发式加权，已有 `evaluation.py` 和 `scripts/evaluate-search.py`。产品化后可能遇到召回不足、语义搜索需求或 10k Item 规模延迟问题，但不能凭“别人都用向量库”就迁移。需要先量化，再决定是否替换。

## Scope

- 建立/扩充 golden query 集：至少覆盖标题、摘要、tag、transcript、book 五类；每条有期望 Item。
- 用现有 `scripts/evaluate-search.py` 跑基线：recall@10、first relevant rank、p95 延迟、索引大小、重建时间。
- 定义触发条件（任一）：
  - recall@10 低于约定阈值（例如 0.8）且不是数据缺失导致；
  - 10k Item 规模 p95 > 500ms；
  - 用户明确需要跨语言/语义搜索，FTS5 无法满足。
- 只有触发后才评估候选：Typesense、Meilisearch、OpenSearch、pgvector/嵌入模型；对比召回、延迟、运维、许可、备份。
- 输出报告 `.scratch/productization/search-backend-evaluation.md`，给出“保持 FTS5 / 换某后端 / 需要更多标注数据”的结论。
- 不触发则关闭本 issue，保留基线数据供后续回归。

## Acceptance Criteria

- [ ] golden query 集和基线报告存在；命令可复现。
- [ ] 报告包含 recall@10、first rank、p95、索引大小、重建时间。
- [ ] 明确写出触发条件和是否触发；未触发时记录“保持 FTS5”。
- [ ] 如果触发，候选对比包含召回、延迟、运维、许可、备份/恢复。
- [ ] 不修改生产搜索实现；迁移另开 issue。
- [ ] 基线纳入回归：后续搜索改动不能显著降低 recall。

## Testing

- 运行 `uv run trove search` / `scripts/evaluate-search.py`，确认报告数据可复现。
- 人工抽查 10 条结果，确认 golden 期望合理。
- 记录测试数据版本/Item 数量，避免不同库对比失真。

## Out of Scope

- 立即引入向量数据库或嵌入模型。
- 重做搜索 UI/排序策略。
- 多租户/跨库搜索。
- 把搜索拆成独立服务（只有触发后才考虑）。

## Notes

- 先用数据回答“FTS5 是否够用”；语义搜索是产品需求，不是工程默认。
- 如果只是索引缺失，先修 `trove index rebuild`/索引覆盖，不要换后端。
- 迁移成本包括双写、回滚、备份、Android 本地搜索一致性；报告必须列出。
