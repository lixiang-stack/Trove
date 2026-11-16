# 19 — Android 同步硬化：冲突、Epoch 与重装恢复

Status: implemented
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

- [x] 离线改 Tag/进度/状态，重连后按字段 LWW 收敛，无静默覆盖。
- [x] 相同 Idempotency-Key 重放无重复副作用。
- [x] epoch/cursor 无效触发全量重同步；已下载文件按 sha256 复用。
- [x] tombstone 删除、复活、文件清单变化处理正确。
- [ ] 重装后登录恢复进度/选择；本地下载可重下。Library/进度已覆盖；“下载选择”无 Host 字段，记录为例外并开 [24](24-reinstall-download-selection.md)。
- [x] Host 不可达时 App 继续播放/阅读已下载内容，不丢改动。

## Testing

- App seam：离线队列、冲突、epoch/cursor、tombstone/复活、重装、Host 不可达。
- Host seam 已由 06/07 覆盖；这里用 fake API 编排边界。
- 真实设备：飞行模式改状态 → 重连 → Web/另一设备看 canonical。

## Out of Scope

- 新功能/新页面；只做同步正确性和恢复。
- 多用户/多租户同步。

## Implementation

- `SyncEngine` 保持“先推 PendingMutation，再拉 manifest，最后拉 state”；单条 mutation 失败不再阻断 manifest/tombstone 拉取，state 在有 pending 时跳过。写响应只应用本次 mutation 携带的字段，且不覆盖同字段更新的 pending 本地值；Tag/State 拉取也跳过有 pending 的字段。
- 全量 manifest 只有在所有页成功后才推进 cursor，避免部分失败后把下一次同步误判为增量而漏掉删除对账；epoch/cursor 无效仍重置两条游标并保留 pending mutation。
- 文件清单变化按下载选择保留：sha 变化时 `queued/downloading/paused/failed/completed` 都重新入队，已选 Item 新增 artifact 也自动入队；sha 不变的已下载文件继续复用。重下完成时清理同路径的延迟删除记录，暂停/播放中不再误删新文件。
- 后台恢复：`AppContainer` 启动即恢复 session，`SyncWorker` 在同步前再次 `restore()`；登录/恢复、网络恢复和周期任务都会触发同步。时钟偏移 warning 和 `applied:false` 都进入可见提示；Settings 诊断新增待同步数量/最后错误。
- App seam 新增 `SyncHardeningFlowTest`：离线编辑收敛、Idempotency-Key 重试、epoch/tombstone/revive、重装恢复 Library/进度、离线本地播放 + 进度排队、打开中的 Item 被 tombstone。`SyncEngineTest` 增加部分全量失败、state cursor、sha 复用、pending 跨 epoch、下载选择、clock skew、字段级 canonical 等测试。
- 例外：下载选择仍是纯本地状态，重装后不能恢复；按 [24](24-reinstall-download-selection.md) 处理。真机重装已恢复 6 个 Item 和 40% 进度；60 分钟/蓝牙/Caddy 验收在 [23](23-v1-release-device-acceptance.md)。
