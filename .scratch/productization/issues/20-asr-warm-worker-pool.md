# 20 — ASR 冷启动测量与 warm worker 池

Status: needs-triage
Type: task
Milestone: P2
Blocked by: 08
Spec: [spec.md](../spec.md)

## Context

当前每个 ASR 任务都会启动一次 `python -m trove.adapters.asr_worker`，子进程里重新 import FunASR、加载 1.25GB 模型，然后只处理一条音频。单条长音频时冷启动占比不高；批量入库时，每次 10–30 秒的模型加载会累加。先测量，再决定是否值得引入常驻模型进程；不要凭感觉增加复杂度。

## Scope

- 测量（先做）：
  - 参考机上记录单次 ASR 的“进程启动 + 模型加载”与“纯推理”耗时。
  - 用短（<2 min）、中（10–20 min）、长（>60 min）三类音频，计算冷启动占比。
  - 记录峰值 RSS、并发 1/2 时的内存和 RTF。
- 判定阈值：如果冷启动在 100 条批量中占总 ASR 时间 > 5%，或单条短音频 > 30 秒，进入实现；否则关闭本 issue，保留数据。
- 实现（仅当触发）：
  - 常驻 ASR 子进程：父进程通过 JSON lines/队列发送任务，子进程加载一次模型、循环处理。
  - 健康检查、崩溃重启、超时取消、内存上限；失败时回退到一次性子进程。
  - 指标：冷启动耗时、模型加载次数、warm 命中率、单任务推理耗时。
- 不改变 `Transcriber` 端口和 `TranscriptResult` 契约；只替换 `ParaformerTranscriber` 的内部执行方式。

## Acceptance Criteria

- [ ] 测量报告记录测试音频、模型版本、冷启动/推理耗时、RSS、结论。
- [ ] 明确写出是否触发实现；未触发则关闭并说明数据。
- [ ] 如果实现：批量 ASR 的总耗时下降达到报告中的目标，且转写输出与一次性子进程一致。
- [ ] 子进程崩溃/超时/内存超限时任务失败可重试，不拖垮 worker。
- [ ] 现有 `test_asr.py`、host seam 保持绿。
- [ ] 不引入新的常驻服务/端口；仍是 worker 内部进程。

## Testing

- 基准：三类音频各跑 3 次，记录均值/峰值。
- 功能：warm 模式与一次性模式的 transcript segments 逐条对比。
- 故障：kill 子进程、发送超时任务、并发 2 时的内存。
- 回归：`./scripts/check.sh --fast`；ASR 相关测试。

## Out of Scope

- 抽取独立 ASR 服务（15）。
- 换 FunASR/ONNX/sherpa-onnx 运行时（14）。
- GPU 调度、多机。
- 修改音频预处理或 ASR 质量。

## Notes

- 先测量再实现；如果冷启动不是瓶颈，直接关闭，避免为“可能有用”增加常驻进程。
- 常驻进程要考虑模型更新/配置变更后的重启；不要在父进程里缓存模型。
- 与 08 的 asr pool 并发配合：warm pool 大小和 pool 并发要一致，避免多个进程各加载一份模型。
