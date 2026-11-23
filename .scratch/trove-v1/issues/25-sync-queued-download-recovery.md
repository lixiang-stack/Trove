# 25 — 已同步但下载长期停等待的恢复

Status: implemented
Type: bug
Milestone: M3
Spec: [spec.md](../spec.md)
Tech: [tech-selection.md](../tech-selection.md)
Requirements: FR-73, FR-72
ADRs: [0009](../../../docs/adr/0009-native-android-client-app-managed-sync.md)

## Context

真机用 USB + `adb reverse` 连真实 Host 时，Library 显示「已同步」，但打开合集
单集仍显示「等待下载」，拔掉 USB 后也没有变化。

排查到的现场：sync cursor 已成功推进，但 4 个 Item 的 artifact 停在 `queued`、
`downloaded_bytes = 0`；WorkManager 的下载任务从入队起 `run_attempt_count = 0`。
JobScheduler 报告 `Restricted due to: frozen`，App 不在电池优化白名单内。也就是
说同步（前台 HTTP）成功，但下载 worker 被系统冻结，从未执行。

代码层面的缺口：

- `SyncStrip` 的「已同步」只反映 `lastSuccessAt`，不包含待下载文件。
- `PlayerViewModel.autoSync()` 只在 `none/partial/failed` 时入队；`queued` 被跳过。
- `LibraryScreen` 回前台只触发 sync；`SyncEngine` 只在 artifact 新增/sha 变化时
  入队，已存在的 `queued` 永远不会补排。
- 唯一下载任务一旦被 OEM 冻结，App 回前台、手动刷新、重新打开 Item 都不会重建
  任务，只能永久显示「等待下载」。

## Scope

- App 回前台（Library refresh）时补排已 `queued` 的下载。
- 打开 `queued` Item 时补排，而不是重新标记选择。
- Library 同步条显示待下载数量，避免把「元数据已同步」误解为「内容已离线」。
- 不改变下载约束、选择语义或 Host 契约。

## Acceptance Criteria

- [x] 有 `queued` artifact 时，Library 回前台会重新入队下载任务。
- [x] 打开 `queued` Item 会补排下载；不会覆盖 `paused` 选择。
- [x] Library 状态条显示「已同步 · N 项等待下载」。
- [x] 下载进行中不会因补排再次启动 worker。
- [x] 既有下载/同步测试保持绿。

## Testing

- `ArtifactDownloaderTest`：`queued` 补排；`downloading` 时 no-op；`none` 时 no-op。
- `PlayerViewModelTest`：打开 `queued` Item 调用补排，不走新的入队选择。
- `LibraryFlowTest`：带 `queued` artifact 的 Library 显示待下载数量并重新入队。
- `scripts/android/check.sh --no-daemon` 全绿。

## Out of Scope

- 绕过 MIUI/OEM 对后台任务的冻结；App 仍建议把电池策略设为「无限制」。
- 整库/合集自动下载；仍按 item 选择性下载。
- 下载选择跨重装恢复（[24](24-reinstall-download-selection.md)）。

## Implementation

- `DownloadManager.resumePending()`：有 `downloading` artifact 时 no-op；否则从
  `itemsWithPendingDownloads()` 取一个 `queued` item 重新 `enqueue` 唯一下载任务。
- `LibraryViewModel.refresh()` 在 sync 后调用 `resumePending()`；`queuedDownloads`
  从 downloads 流计算并显示在同步条。
- `PlayerViewModel.autoSync()` 对 `queued` 走 `resumePending()`，`paused` 仍不触碰。
- 真机复核（2026-11-19，USB + 真实 Host）：安装新 APK 并启动后，原先 4 个
  `queued` Item 的 13 个 artifact 全部变为 `completed`，`DownloadWorker` 返回
  SUCCESS，前台下载通知正常结束。该次恢复由 App 进程重启触发 WorkManager 重跑
  旧任务；不重启进程的补拉路径由 `ArtifactDownloaderTest` / `PlayerViewModelTest`
  / `LibraryFlowTest` 覆盖。
- 真机残留风险：若 OEM 连前台任务也冻结，补排仍可能失败；此时状态条至少暴露
  「N 项等待下载」，且用户可按 [docs/android.md](../../../docs/android.md) 的电池
  优化说明处理。
