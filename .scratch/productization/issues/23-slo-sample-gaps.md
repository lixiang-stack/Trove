# 23 — 补齐 SLO 取样：30 分钟 p95、ASR RTF、worker 恢复

Status: ready-for-agent
Type: task
Milestone: P3
Blocked by: none
Spec: [spec.md](../spec.md)
Related: [19](19-productization-acceptance.md), [20](20-asr-warm-worker-pool.md)

## Context

19 的验收没有按 SLO 的原始定义取样：

- `30 分钟音频入库到可搜索 p95 ≤ 15 分钟`：只测了 1 条 15 分钟视频和 1 条 3.75 分钟播客，n=2，且不是 30 分钟样本，无法计算 p95。
- `ASR RTF ≤ 0.15`：900 s 视频为 0.1237，但 225 s 播客为 0.216。短音频 RTF 受每次 FunASR 模型加载的固定开销影响，不能直接判断 SLO 是否达标；需要按音频时长分桶或暖进程数据。
- `worker 崩溃恢复 ≤ 30 秒`：lease 回收为 28.5 s，但任务要等 32.6 s 退避后才开始 attempt 2（kill→恢复约 61.1 s）。需要明确 SLO 计的是“检测/回收”还是“任务恢复”。

这不是 10k 列表问题（见 [22](22-paginate-item-list.md)），而是 SLO 测量口径缺口。不能把 n=2 的结果当作 p95 通过。

## Scope

- 准备至少 5 条 30 分钟左右的真实中文音频（可用现有 15 分钟视频拼接/多集，但需记录来源和时长分布）。
- 在分池模式（download/asr/llm/index）下逐条跑完整管线，记录创建到 completed 的 stage 时间戳。
- 输出 end-to-end p50/p95、ASR RTF 按 `<5 min`、`5–15 min`、`15–30 min`、`≥30 min` 分桶，并给出样本数和置信说明。
- 对比 `ASR RTF ≤ 0.15`：明确短音频是否豁免、是否需要 [20](20-asr-warm-worker-pool.md) 的 warm pool，或调整 SLO 定义。
- 明确 worker 崩溃恢复的计时口径（lease 回收 / 任务恢复），并按该口径复测。
- 结果追加到 [acceptance.md](../acceptance.md) 的 SLO 快照，不新开验收文档。

## Acceptance Criteria

- [ ] 至少 5 条 30 分钟样本完成端到端，记录 p50/p95 和每条 stage 时间。
- [ ] ASR RTF 按上述时长分桶，每桶至少 2 个样本（短音频桶可用现有样本）。
- [ ] 对 30 分钟 p95 是否 ≤ 15 分钟给出明确结论；未达标写明原因和后续 issue。
- [ ] 对短音频 RTF 0.216 给出结论：SLO 豁免、warm pool 优化，或标记为已知限制。
- [ ] 明确 worker 恢复口径，并给出 lease 回收与任务恢复两个时间；按约定口径判定是否达标。
- [ ] 数据使用独立 `TROVE_HOME`，结束后清理；记录模型、CPU、并发配置。

## Testing

- `trove bench asr` 先测单条 ASR，再用 API 跑完整管线计时。
- 用 `run_steps` 时间戳计算 stage 耗时，不用人工秒表。
- 搜索延迟单独记录，不混入 end-to-end p95。

## Out of Scope

- 修改 `domain/retry.py`、StageTask 或队列语义。
- 优化 ASR 运行时（由 20 决定）。
- 10k Item 列表分页（由 22 负责）。

## Notes

- 19 的记录已把这三项标为“部分验证”，本 issue 负责补齐或正式调整 SLO 口径。
