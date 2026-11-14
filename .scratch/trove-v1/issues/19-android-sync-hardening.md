# 19 — Android 同步硬化：冲突、Epoch 与重装恢复

Status: ready-for-agent
Type: task
Milestone: M3
Blocked by: 07, 08, 10, 16
Spec: [spec.md](../spec.md)
Tech: [tech-selection.md](../tech-selection.md)
Requirements: FR-73
ADRs: [0009](../../../docs/adr/0009-native-android-client-app-managed-sync.md)

## Context

基础同步完成后，需要把离线队列、LWW 冲突、tombstone/复活、epoch 变化、重装恢复和失败重试收口。目标是“Host 不可达不丢本地改动；重连后状态收敛；不静默覆盖”。

## Scope

- SyncEngine 顺序：先推 `PendingMutation`，再拉 Content manifest，最后拉 State；有未推送本地写时跳过 State 拉取。
- 离线队列：Tag/进度/Consumption State 合并、重试、失败可见；`Idempotency-Key` 重放。
- `applied:false`/canonical 冲突提示；Host 旧写/新写/时钟偏移。
- `sync_epoch` 变化、`cursor_invalid`、Host 备份恢复后的全量重同步。
- tombstone/复活、文件清单变化、已下载文件 sha256 复用。
- 重装 App 登录后恢复 Library/进度/下载选择（文件可重下）。
- Host 不可达/网络切换/后台被杀后的恢复；不丢本地改动。

## Acceptance Criteria

- [ ] 离线改 Tag/进度/状态，重连后按字段 LWW 收敛，无静默覆盖。
- [ ] 相同 Idempotency-Key 重放无重复副作用。
- [ ] epoch/cursor 无效触发全量重同步；已下载文件按 sha256 复用。
- [ ] tombstone 删除、复活、文件清单变化处理正确。
- [ ] 重装后登录恢复进度/选择；本地下载可重下。
- [ ] Host 不可达时 App 继续播放/阅读已下载内容，不丢改动。

## Testing

- App seam：离线队列、冲突、epoch/cursor、tombstone/复活、重装、Host 不可达。
- Host seam 已由 06/07 覆盖；这里用 fake API 编排边界。
- 真实设备：飞行模式改状态 → 重连 → Web/另一设备看 canonical。

## Out of Scope

- 新功能/新页面；只做同步正确性和恢复。
- 多用户/多租户同步。
