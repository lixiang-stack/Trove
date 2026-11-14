# 07 — Host LWW 进度/Tag 与幂等

Status: ready-for-agent
Type: task
Milestone: M0
Blocked by: 02, 03, 04
Spec: [spec.md](../spec.md)
Tech: [tech-selection.md](../tech-selection.md)
Requirements: FR-73
ADRs: [0009](../../../docs/adr/0009-native-android-client-app-managed-sync.md)

## Context

手机和桌面可能离线修改播放/阅读进度、Consumption State 和 Tag。Host 必须按字段 last-write-wins 合并，返回 canonical 值，并让重试幂等；不能让一次 book 进度覆盖更新的 audio 进度。

## Scope

- 扩展现有 `PUT /api/items/{id}/progress`：body 增加 `client_updated_at`，header `Idempotency-Key`。
- 新增 `PUT /api/items/{id}/tags`：整组替换、Host 归一化、按 `tags` 字段 LWW。
- `sync_field_clocks` 按字段比较：`client_updated_at` 大者胜，相等按 `device_id` 稳定决胜。
- 超过 Host 当前时间 5 分钟的客户端时间用服务端时间并返回 `sync.clock_skew`。
- 返回 `applied: true/false` + canonical Item/state + 字段时钟；`applied:false` 是正常 LWW 结果。
- `sync_mutations` 保存首次响应；相同 Idempotency-Key 返回第一次结果。
- Web Host Console 写操作也走字段时钟，`device_id = host-web`。
- 进度写入不递增 `version`/`content_seq`，只递增 `state_seq`。

## Acceptance Criteria

- [ ] 旧 `client_updated_at` 被忽略，新的生效；相同时间按 device_id 稳定决胜。
- [ ] 一次 book 进度不覆盖更新的 audio 进度；字段独立比较。
- [ ] Tag 写入归一化并返回 canonical Tag；旧 Tag 写被忽略。
- [ ] 相同 Idempotency-Key 重放无重复副作用；返回第一次结果。
- [ ] Web 写操作参与 LWW；进度写不导致 manifest 抖动。
- [ ] 错误/时钟偏移响应稳定，不泄露内部路径。

## Testing

- Host seam：旧写/新写/平局/部分字段/重放/时钟偏移/Web 写。
- 断言 canonical 值、`applied`、字段时钟和 state_seq。
- 现有 progress/tag API 测试回归。

## Out of Scope

- Android 本地乐观更新/离线队列；由 16/19 实现。
- 跨用户/多租户冲突策略；V1 单用户。
