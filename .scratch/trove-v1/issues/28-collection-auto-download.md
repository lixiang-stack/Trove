# 28 — 合集持续自动下载

Status: implemented
Type: feature
Milestone: M3
Spec: [spec.md](../spec.md)
Tech: [tech-selection.md](../tech-selection.md)
Requirements: FR-72, FR-73
ADRs: [0009](../../../docs/adr/0009-native-android-client-app-managed-sync.md)

## Context

#26 的「下载全部」是一次性动作：只入队点击当时已有 artifact 的单集，且不持久化
合集选择。实际使用中，合集 75 集里 69 集已处理完成，但只有 51 集已下载；后 18 集
在点「下载全部」时还没生成 artifact，之后处理完成也不会自动入队，处理进度因此
持续大于下载进度。

## Scope

- 「下载全部」持久化该合集的自动下载意图。
- 同步到该合集、具备 artifact 且尚未下载的单集自动入队；后续新增并处理完成的
  单集也自动下载。
- artifact 未变化时，已暂停、失败、部分下载和用户移除下载保持原状态；sha 变化时按既有规则重新入队。
- 合集菜单提供「停止自动下载」；删除/解散合集会清除意图。
- 未开启意图的合集保持 selective sync。

## Acceptance Criteria

- [x] 点击「下载全部」后本地保存合集下载意图，并立即入队当前可下载单集。
- [x] 同步到该合集的新 artifact/新单集自动入队，无需再次点击。
- [x] 未开启意图的合集不会自动入队。
- [x] 暂停、失败、部分下载和已移除下载在 artifact 未变化时不会因意图被重排。
- [x] 可停止自动下载；删除/解散合集清除意图。
- [x] Room 迁移、JVM/Compose 测试与 lint 全绿。

## Testing

- `SyncEngineTest`：开启意图后新 artifact 自动入队；未开启不自动入队；未变化的
  已移除 artifact 不重排。
- `CollectionFlowTest`：点击「下载全部」后显示自动下载提示，同步新单集自动入队，
  菜单可停止自动下载。
- `TroveDatabaseMigrationTest` / `TroveDatabaseMigrationDeviceTest`：4→5 迁移。
- `scripts/android/check.sh --no-daemon`、`scripts/android/device-check.sh`、
  `python3 scripts/check-docs.py` 全绿。

## Out of Scope

- 整库自动下载。
- 合集级取消/删除全部下载。
- 改变 Library 顶部「已同步」语义。

## Implementation

- `collection_download_intents` Room 表保存合集 ID；`CollectionDownloadIntentDao`
  提供开启、停止、查询和孤儿清理。
- `LibraryViewModel.downloadCollection()` 开启意图后调用既有 `enqueueAll()`；
  `disableCollectionAutoDownload()` 停止意图；删除合集时清除意图。
- `SyncEngine.applyArtifacts()` 在意图开启时为新建或 sha 变化的 artifact 置
  `queued` 并触发下载队列；同步结束后清理没有对应 Item 的孤儿意图。
- `CollectionScreen` 显示自动下载提示，并在合集菜单提供「停止自动下载」。
