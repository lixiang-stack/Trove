# 10 — Android Library 与首次/增量同步

Status: ready-for-agent
Type: task
Milestone: M1
Blocked by: 04, 06, 08, 09
Spec: [spec.md](../spec.md)
Tech: [tech-selection.md](../tech-selection.md)
Requirements: FR-71, FR-73
ADRs: [0009](../../../docs/adr/0009-native-android-client-app-managed-sync.md)

## Context

登录后 App 需要先看到整个 Library 的元数据，再增量同步；删除要按 tombstone 清理本地，离线时仍能显示已同步的库。这个 issue 建立 Library 的读模型和 manifest/state 应用逻辑。

## Scope

- 首次 manifest 全量同步 + 分页；只同步元数据/Tag/文件清单，不自动下载文件。
- 增量 cursor 同步、`sync_epoch`/`cursor_invalid` 全量重同步；保留已下载文件按 sha256 复用。
- State stream 应用；同步状态（Idle/Syncing/Offline/Error、上次成功时间）。
- Library UI：最近添加/最近消费排序、类型/Consumption State/Tag/Source 过滤、Processing State 徽标、Inbox、离线徽标。
- tombstone：删除本地 Item/索引/文件引用；复活 Item 重新显示。
- 初始同步的 loading/empty/error/offline 状态。

## Acceptance Criteria

- [ ] 首次登录后显示全部 Item 元数据；分页正确，无重复/遗漏。
- [ ] 增量同步只应用变更；epoch/cursor 无效时全量重同步。
- [ ] tombstone 清理本地 Item；复活 Item 重新出现。
- [ ] 排序/过滤/Inbox/离线状态可用；无网络时显示已同步库。
- [ ] 同步不阻塞 UI；错误可见且可重试。
- [ ] 不下载媒体文件，不做播放/阅读。

## Testing

- App seam：fake manifest/state 分页/增量/tombstone/epoch；Library 过滤/排序/Inbox/离线。
- 1,000 Item fixture 的列表性能冒烟。
- 不测真实网络；用 fake API + 真 Room。

## Out of Scope

- 下载、播放、阅读、搜索、Tag 编辑；由 12–17 实现。
- 全量文件同步；V1 只做选择性下载。
