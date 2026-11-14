# 04 — Host 同步 Manifest/State 与 epoch

Status: ready-for-agent
Type: task
Milestone: M0
Blocked by: 02, 03
Spec: [spec.md](../spec.md)
Tech: [tech-selection.md](../tech-selection.md)
Requirements: FR-73, NFR-08
ADRs: [0008](../../../docs/adr/0008-content-package-as-source-of-truth.md), [0009](../../../docs/adr/0009-native-android-client-app-managed-sync.md)

## Context

Android 需要增量同步 Item/Tag/文件/tombstone 和消费状态。Content 与 State 必须分两条流，避免每 5 秒播放进度导致 manifest 抖动。cursor 和 epoch 要能处理分页、Host 备份恢复和全量重同步。

## Scope

- 实现 `sync_sequence` 的 `next_seq()`（`UPDATE ... RETURNING`）和 content/state 变更 helper。
- Content 变化递增 `version` + `content_seq`；State 变化只递增 `state_seq`。
- `GET /api/sync/manifest?cursor=&limit=`：compact Item（元数据、Tag、Processing State、错误码、文件清单）、tombstone、`next_cursor`、`has_more`、`epoch`。
- `GET /api/sync/state?cursor=&limit=`：Item ID、位置、Consumption State、`last_consumed_at`、`next_cursor`、`has_more`、`epoch`。
- cursor 无效/大于当前最大 seq、epoch 变化时返回 `sync.cursor_invalid` 或新 epoch 语义。
- `trove sync reset-epoch` CLI（Host 从备份恢复后强制全量同步）。
- manifest 不返回 Run steps/log tail/搜索 evidence。

## Acceptance Criteria

- [ ] 首次全量、分页、增量 manifest 正确，无重复/遗漏；`has_more`/`next_cursor` 正确。
- [ ] State 同步推进 `state_seq`，但 content manifest 不因播放进度抖动。
- [ ] tombstone 出现在 manifest；已删除 Item 不出现在普通 Library/Search/Continue。
- [ ] epoch 变化或 cursor 超界时客户端可识别并触发全量重同步。
- [ ] compact payload 不包含 Run steps/log tail；文件清单含 kind/sha256/size/mime/version/url。

## Testing

- Host seam：首同步/分页/增量/epoch/cursor 无效/进度不 bump content_seq。
- 1,000 Item seed 的分页和顺序测试。
- 现有 Library/Search/Continue 测试回归。

## Out of Scope

- LWW 写接口/幂等；由 07 实现。
- 文件下载端点；由 05 实现。
- soft delete/tombstone 的删除行为；由 06 实现。
