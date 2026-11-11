# 26 — ASR、搜索与存储性能基准

Status: ready-for-human  
Type: task  
Milestone: M3  
Blocked by: 13, 14, 16, 17  
Spec: [spec.md](../spec.md)  
Requirements: NFR-05, NFR-06

## Context

MVP 的硬指标是：1 小时视频端到端 <30 分钟、千条级搜索 <1 秒、100 小时音频 + 100 本书 <5GB。需要在真实 Mac（M1 Pro）和真实数据上记录，而不是凭估算宣称达标。

## Scope

- ASR 组件：1 小时真实中文音频，`trove bench asr` 记录耗时/实时倍率/模型/语言。
- 端到端：1 小时视频完整管线（下载→抽音频→转写→整理→索引）计时。
- 搜索：1k 条数据（真实 + 可重复 seed）`trove bench search`，记录 p50/p95、索引大小。
- 存储：导入 20 条真实内容后 `du`，外推 100h + 100 本书；记录音频/EPUB/transcript/DB 分布。
- 失败动作：换 ASR/降码率/调索引/分段；不达标不得宣称满足 NFR。

## Acceptance Criteria

- [ ] 记录 ASR 组件耗时；目标 ≤20 分钟/1 小时。
- [ ] 记录端到端 1 小时视频耗时；目标 <30 分钟。
- [ ] 记录 1k 条搜索 p95；目标 <1 秒（争取 <100ms）。
- [ ] 记录真实库存储分布并外推；目标 <5GB。
- [ ] 每个指标附命令、数据来源、机器/模型版本、日期；不达标附行动项。
- [ ] 结果可供 29 验收引用。

## Testing

- 基准脚本/命令可重复执行；网络下载只在需要时跑。
- 手动记录到本 issue 的 `## Comments` 或 `.scratch/trove-mvp/` 记录文件。
- 不用合成假数据代替真实 1 小时音频/真实书库。

## Out of Scope

- 性能优化本身；如果不达标，另开 issue 或回退方案。
- 大众市场容量/成本模型；不做。

## Comments

2026-11-10 — Added repeatable commands `trove bench asr <audio>`,
`trove bench seed --count N` (use a disposable `TROVE_HOME`),
`trove bench search --queries <file> --repeat N`, and
`trove bench pipeline <video-url>`, plus the recording template at
`.scratch/trove-mvp/benchmarks.md`. Real 1-hour audio, 1k-Item search, end-to-end
timing, and storage measurements still require the physical Mac and user data.
