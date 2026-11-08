# 10 — 重试、续跑、取消与重启恢复

Status: ready-for-agent  
Type: task  
Milestone: M0  
Blocked by: 06, 07, 08, 09  
Spec: [spec.md](../spec.md)  
Requirements: FR-09, FR-10, FR-11, FR-83, NFR-04, NFR-13  
ADRs: [0001](../../../docs/adr/0001-python-monolith-sqlite-worker.md)

## Context

处理会因网络、模型、Host 休眠/重启而中断。需要保证失败可重试、已完成阶段不重做、排队/运行中可取消、重启后不丢 Processing Run 也不重复处理。

## Scope

- 重试失败/取消的 Run：只重置失败/取消阶段及其后续阶段，已完成阶段跳过。
- 取消排队：直接置为 `cancelled`；取消运行中：写 `cancel_requested_at`，阶段边界检查并终止子进程组，清理当前阶段半成品。
- Worker 启动回收：所有 `running` Run 回收为 `queued`，清理当前阶段临时文件；单 worker 前提下安全。
- 幂等：重复 cancel/retry 不产生多个并发 Run；已存在的产物不重复生成。
- API/HTML 操作入口与状态反馈；失败不删除用户原始文件。

## Acceptance Criteria

- [ ] 在下载/抽音频/转写任一阶段注入失败，retry 从该阶段继续，之前完成阶段不重跑。
- [ ] 取消排队中的 Run 后 worker 不领取；取消运行中的 Run 在阶段边界停止并清理半成品。
- [ ] 处理中 kill worker，重启后 Run 回到队列并从安全阶段继续；不重复生成已完成 artifact。
- [ ] 重复点击 retry/cancel 不会创建多个 Run 或并发执行。
- [ ] 已完成的音频/文本在后续阶段失败或取消后仍可播放/阅读。
- [ ] 失败/取消原因在 UI/API 可见。

## Testing

- Host seam：fake 阶段注入失败、取消、重启；断言阶段 attempt、artifact、Run 终态。
- 子进程取消测试：mock 长运行子进程，确认被终止并清理。
- 幂等测试：重复操作。
- 不依赖固定 sleep；使用轮询 helper 和可控 fake 阶段。

## Out of Scope

- 新增阶段或真实适配器；由 07–09、13、16、17 实现。
- 运行中取消的“立即”保证；只承诺 best-effort。
