# 26 — 合集手动批量下载与下载状态

Status: implemented
Type: feature
Milestone: M3
Spec: [spec.md](../spec.md)
Tech: [tech-selection.md](../tech-selection.md)
Requirements: FR-72, FR-73
ADRs: [0009](../../../docs/adr/0009-native-android-client-app-managed-sync.md)

## Context

合集内单集是独立 Item，下载也按 Item 管理。实际使用中 Library 显示「已同步」，
合集卡片仍显示「全部完成」，但合集内只有部分单集下载到手机，用户无法判断哪些
已离线、也无法一次下载整个合集。

「已同步」只表示 Content/State 流同步成功，不是「所有文件已下载」。下载完整度
应在合集卡片和合集详情单独表达，不改变 selective sync 语义。

## Scope

- 合集详情增加手动「下载全部」：一次性把当前可下载单集入队。
- 不持久化合集选择；之后新增单集不自动下载。
- 合集卡片显示「已下载 x/y」和下载进度；处理完成但未全部下载时不再显示「全部完成」。
- 合集详情显示已下载 x/y 与下载进度，以及单集下载状态：
  `未下载 / 等待下载 / 下载中 / 已下载`，保留失败、暂停、部分下载文案。
- Library 顶部「已同步」继续只表示元数据同步。

## Acceptance Criteria

- [x] 合集详情有「下载全部」；一次入队所有带 artifact 的单集，已完成项不重复下载。
- [x] 批量入队只触发一个下载任务，不因逐集入队反复取消 worker。
- [x] 单集行明确显示下载状态，未下载单集不再没有提示。
- [x] 合集卡片和详情显示下载完整度；未全部下载时不显示「全部完成」。
- [x] 既有播放、重试失败、删除合集、下载恢复行为不变。
- [x] JVM/Compose 测试与 lint 全绿。

## Testing

- `ArtifactDownloaderTest`：`enqueueAll` 只触发一次队列请求，并跳过已完成项。
- `LibraryQueryTest`：合集卡片的已下载数、等待数、下载进度。
- `CollectionFlowTest`：合集详情显示「未下载」→ 点击「下载全部」→ 两个单集变为
  「等待下载」，按钮显示等待计数。
- `scripts/android/check.sh --no-daemon`、`python3 scripts/check-docs.py` 全绿。

## Out of Scope

- 自动追更/新增单集自动下载；合集选择不持久化。
- 合集级取消下载、删除全部下载。
- 改变 Library 顶部「已同步」语义；它仍不代表离线完整。
- 整库自动下载。

## Implementation

- `DownloadManager.enqueueAll(itemIds)`：批量标记非 completed artifact 为 `queued`，
  只调用一次全局下载队列；单集继续复用现有 `enqueue` 语义。
- `LibraryViewModel.downloadCollection(collectionId)`：取当前合集中带 artifact 的
  单集，交给 `enqueueAll`。
- `CollectionScreen`：新增「下载全部」按钮和下载完整度/进度；单集用
  `collectionDownloadLabel` 显示完整下载状态；单集列表加稳定 test tag。
- `LibraryEntry.CollectionCard`：新增 `downloadedCount`、`pendingDownloadCount`、
  `downloadingCount`、`allDownloaded`、`downloadProgress`；Library 卡片状态文案与
  进度条改为下载视角。
- 原型差异：`.scratch/collections-ebooks/prototype/android.html` 原设计明确不做
  合集级「下载全部」、只用下载图标；本票按用户 2026-11-19 的要求改为显式按钮和
  四态文案，原型未重绘。
