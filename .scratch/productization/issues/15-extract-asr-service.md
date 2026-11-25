# 15 — 抽取 ASR 服务（gated）

Status: needs-triage
Type: task
Milestone: P4
Blocked by: 08, 09, 10, 14
Spec: [spec.md](../spec.md)

## Context

ASR 是资源隔离收益最大的阶段：CPU/内存密集、模型 1.25GB、单次可跑数小时。L1 先通过独立 asr pool 解决阻塞；只有在队列持续积压、需要 GPU/多机、或 ASR 运行时迁移后，才值得抽成独立服务。服务实现继续用 Python，不做 Go 重写。

## Scope

- 定义契约（HTTP 或本地队列，二选一并在 issue 中记录理由）：
  - 输入：音频路径/对象 key、语言提示、模型标识、幂等键。
  - 输出：`TranscriptResult`（segments/language/model）或稳定错误码。
  - 健康、指标、版本、取消语义。
- Python 服务：FastAPI 或独立 worker；warm model pool；并发/内存上限；优雅停机。
- 调用侧：新增 `RemoteTranscriber` 适配器，实现 `Transcriber` 端口；feature flag 切换；保留 in-process fallback。
- 部署：Compose service / launchd agent；共享 `trove-data` 卷或对象存储；模型卷。
- 迁移：历史 transcript 不重跑；新任务走 remote；失败可回退。

## Acceptance Criteria

- [ ] 契约文档和 contract fixtures 存在；错误码与现有 `asr.*` 对齐。
- [ ] `RemoteTranscriber` 通过现有 `Transcriber` 合同测试；与 in-process 输出 schema 一致。
- [ ] 一个长 ASR 不再占用 API/download/LLM 进程；ASR 服务可独立重启。
- [ ] feature flag 可一键切回 in-process；切换不丢任务。
- [ ] 服务暴露健康、指标、版本；warm pool 减少冷启动。
- [ ] 现有 host seam 在 remote 模式下通过。
- [ ] 部署文档更新。

## Testing

- 契约测试：同一音频，in-process vs remote 输出结构一致。
- 故障：ASR 服务重启/超时/429，任务能重试或回退。
- 并发：warm pool 下多任务；内存不超限。
- 端到端：video → download → asr service → organize → index。

## Out of Scope

- Go/C++ 重写；如果 14 建议换运行时，另开 issue。
- 多租户/按用户计费。
- GPU 自动扩缩容、Kubernetes。
- 把下载/整理也拆成服务（16/17）。

## Notes

- 先做“同机独立进程 + HTTP/队列”，不要直接上多机。
- 传文件路径时注意容器卷一致性；如果未来上对象存储，契约用 object key。
- 服务化不是目的；必须先有指标证明 asr pool 是瓶颈。
