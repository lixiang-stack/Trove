# 06 — Host Soft Delete、Tombstone 与复活

Status: ready-for-agent
Type: task
Milestone: M0
Blocked by: 02, 04
Spec: [spec.md](../spec.md)
Tech: [tech-selection.md](../tech-selection.md)
Requirements: FR-73
ADRs: [0008](../../../docs/adr/0008-content-package-as-source-of-truth.md), [0009](../../../docs/adr/0009-native-android-client-app-managed-sync.md)

## Context

Android 需要知道 Host 删除了哪些 Item，才能清理本地文件和索引；同时不能在重新添加同一 Source 时留下永久墓碑。删除语义从硬删除改为 soft delete + tombstone + 同 ID 复活。

## Scope

- `DELETE /api/items/{id}` 改为 soft delete：设置 `deleted_at`、递增 `version`/`content_seq`。
- 删除 Content Package 派生文件、FTS 行；保留 Item 行和 tombstone 元数据。
- Library/Search/Continue/Export/index rebuild 默认过滤 `deleted_at IS NOT NULL`。
- 重新添加同一 `source_key` 时复活同一 Item ID：清空 `deleted_at`、递增 version/content_seq、创建新 Processing Run。
- manifest 返回 tombstone；复活后返回新版本 Item。
- 迁移/删除相关的现有测试更新。

## Acceptance Criteria

- [ ] 删除后普通 Library/Search/Continue 不再返回 Item；Content Package 文件/FTS 被清理。
- [ ] 下一次 manifest 返回 tombstone（含 id/version/deleted_at）。
- [ ] 重新添加同一 URL/文件复活同一 ID，旧客户端先收到 tombstone 再收到复活 Item。
- [ ] Export 不包含 tombstone；删除不触碰用户原始文件。
- [ ] 现有删除/导出/搜索测试不回归。

## Testing

- Host seam：删除 → 普通查询不可见 → manifest tombstone → 复活 → 新 Run。
- 文件/索引清理断言；用户原始路径不存在于删除范围。
- Export/Continue/Search 过滤 tombstone。

## Out of Scope

- Android 本地删除/清理；由 10/19 实现。
- tombstone 清理策略；V1 保留 tombstone，单用户规模可接受。
