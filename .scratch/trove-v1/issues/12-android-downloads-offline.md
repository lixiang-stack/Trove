# 12 — Android 下载管理与离线存储

Status: implemented
Type: task
Milestone: M1
Blocked by: 05, 10, 11
Spec: [spec.md](../spec.md)
Tech: [tech-selection.md](../tech-selection.md)
Requirements: FR-72, NFR-11
ADRs: [0008](../../../docs/adr/0008-content-package-as-source-of-truth.md), [0009](../../../docs/adr/0009-native-android-client-app-managed-sync.md)

## Context

离线播放/阅读/搜索需要把选中的 Content Package 文件下载到手机。下载必须可续传、校验 sha256、遵守 Wi-Fi/充电约束和存储配额；下载完成后播放器/阅读器/搜索都使用本地文件。

## Scope

- WorkManager `CoroutineWorker` + 前台通知；全局唯一 work chain 串行下载，默认 1 个。
- 请求 `/api/items/{id}/files/{kind}`；Range + `If-Range: <ETag>` 续传；ETag 变化丢弃 `.part` 全量重下。
- 选中 Item 默认下载全部可用 artifact：audio、transcript、book、book_json、ai、cover；`ai.json` 保留完整镜像。
- 完成后校验 sha256，原子 rename；失败可重试/暂停/取消。
- 约束：默认 Wi-Fi；可选仅充电；临时允许移动网络；默认 5GB 配额（可配置）。
- 下载状态/进度/大小写 Room；下载中心 UI；移除下载只删本地，不调用 Host DELETE。
- 文件清单变化时删除旧 artifact；正在播放的文件延迟清理。
- 配额/空间不足阻止下载并提示，不静默删除已有文件。

## Acceptance Criteria

- [x] 选中 Item 下载全部可用 artifact；音频/书/transcript 可离线使用。
- [x] 中断后续传成功；ETag 变化全量重下；sha256 不匹配可重试。
- [x] 下载遵守 Wi-Fi/充电约束和配额；移动网络需用户确认。
- [x] 移除下载保留 Host Item；删除 Item 才走 Host soft delete。
- [x] 下载不阻塞播放/阅读/搜索；状态和错误可见。
- [ ] 前台通知符合 Android 14+ `dataSync` 类型。

## Testing

- App seam：下载状态机、配额、移除、manifest 文件变化；MockWebServer Range/If-Range/sha。
- WorkManager `work-testing`；instrumented 前台通知冒烟。
- 真实设备：断网续传、飞行模式播放、存储不足。

## Out of Scope

- 本地搜索索引；由 15 实现。
- 整库自动下载；V1 只做选择性同步。
- Android 15/16 超长下载的特殊优化；先按 WorkManager 重试兜底。

## Implementation

- `ArtifactDownloader` downloads every artifact for an item to `.part`, resumes with `Range` + `If-Range: <ETag>`, restarts on ETag change, verifies size/sha256, then atomically renames. Partial files are retained on pause/network failure and removed on download removal.
- Quota (default 5 GB) and free-space checks run before network; errors are persisted on artifacts and shown in the UI. Mobile-network and charging-only constraints come from `DownloadSettingsStore`.
- `DownloadWorker` is a WorkManager `CoroutineWorker` using one global unique queue (`KEEP`) and a `dataSync` foreground notification on Android 14+. `DefaultDownloadManager` implements enqueue/pause/retry/remove; removal never calls Host DELETE.
- Sync deletes stale artifact files and defers deletion while the item is playing. Tests: `ArtifactDownloaderTest` (MockWebServer Range/If-Range/sha/quota/remove), sync artifact-change tests.
- **Device acceptance pending**: no Android device is attached; airplane-mode resume, storage-full, and real foreground-notification smoke still need a Android run.

### Android real-device acceptance (2026-11-15 / Android 16, API 36)

- Verified a selected Item downloads `audio`, `transcript`, and `cover` into `filesDir`, with per-artifact `completed`, byte count, ETag, and local path in Room. No media file is downloaded for non-selected Items.
- Verified WorkManager foreground download: `SystemForegroundService` was `isForeground=true` with `types=0x1` (dataSync) and channel `trove_downloads`.
- Verified interruption/resume by force-stopping the app after ~52 MB of a 400 MB download. The `.part` file and ETag survived; WorkManager resumed after relaunch, and the final file matched the Host sha256 (`6ed5e853…`) with `completed` state.
- Verified removing a download deletes all local files and transcript segments but keeps the Host Item; deleting the Item instead produced Host 404 + tombstone and removed local files.
- ETag-change full restart and sha256-mismatch handling are covered by MockWebServer tests; not separately forced on device. Storage-full and metered-network confirmation were not exercised on device.
