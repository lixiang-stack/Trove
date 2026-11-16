# 16 — Android Continue、Consumption State 与 Tag

Status: resolved
Type: task
Milestone: M2
Blocked by: 07, 10, 11, 12
Spec: [spec.md](../spec.md)
Tech: [tech-selection.md](../tech-selection.md)
Requirements: FR-71, FR-73
ADRs: [0009](../../../docs/adr/0009-native-android-client-app-managed-sync.md)

## Context

手机主要用来“继续听/继续读”。需要 Continue 入口、自动/手动 Consumption State、Tag 编辑和离线队列；这些写操作必须按字段 LWW 与 Host/Web 合并，不能静默覆盖。

## Scope

- Continue：最近在听/在读的 Item，一键打开 Player/Reader。
- Consumption State 自动规则（播放/阅读进度、结束）与手动完成/未完成。
- Tag 编辑：增删 Tag、Host 归一化、canonical 回写。
- 离线改动入 `PendingMutation`；重连按字段推送；`applied:false` 显示非阻塞冲突提示。
- 进度/Tag 写入不阻塞播放/阅读；失败可重试。
- 与 Host `PUT progress`/`PUT tags`、`sync_field_clocks` 集成。

## Acceptance Criteria

- [x] Continue 显示进行中的音频/书，一键恢复正确位置。
- [x] 播放/阅读结束自动完成；手动完成/未完成立即生效。
- [x] Tag 增删离线可用，重连后同步；冲突时显示 canonical 并提示。
- [x] 一次 book 进度不覆盖更新的 audio 进度。
- [x] 写入不阻塞 UI；失败可重试且不丢本地改动。
- [x] 不做标题/作者编辑；不做标注。

## Testing

- App seam：Continue、自动/手动状态、Tag 编辑、离线队列、LWW 冲突提示。
- Host seam 已由 07 覆盖；这里用 fake API 编排 applied/canonical。
- 真实设备：离线改 Tag/进度 → 重连 → Web 看到 canonical。

## Out of Scope

- 标题/作者编辑；Host Console 负责。
- 跨用户/多租户冲突。

## Implementation

- Library now computes a Continue strip from in-progress Items ordered by `last_consumed_at`; tapping resumes audio or opens the downloaded book.
- Manual finished/unstarted is available from Player/Reader. Reading progress auto-finishes at 95% and queues a schema-2 `book_progress` mutation; audio auto-completion continues through `PlaybackProgressRecorder`.
- Tag editing is optimistic and offline-first: tags are normalized locally, written to Room, and queued as a `tags` mutation with `client_updated_at`/`Idempotency-Key`. Sync pushes Tags via `PUT /items/{id}/tags`, applies canonical Tags, and emits a non-blocking conflict notice when `applied:false`.
- Automated coverage: `ItemMutationRepositoryTest`, `TagNormalizerTest`, `SyncEngineTest` tag conflict/canonical test, Continue UI test, Player tag/consumption wiring.
- Pending device acceptance: offline Tag/progress edit → reconnect → Web canonical, and cross-device LWW conflict display on Xiaomi 13.

### Xiaomi 13 real-device acceptance (2026-11-16 / Android 16, API 36)

- Continue showed the two in-progress videos and the in-progress book; tapping the video resumed from 73% and MediaSession reported `PLAYING`, tapping the book opened the Reader at its saved locator.
- Manual `标记完成` from Now Playing wrote locally and synced to the Host (`consumption_state=finished`); reopening the menu showed `标记未完成`.
- Tags: added `acceptance` online and `offline-tag` while offline; after reconnect the Host received canonical tags. A Host-side `PUT /tags` with a newer `client_updated_at` won field LWW; the app applied `host-wins` and showed the non-blocking “已在其他设备更新” notice.
- The manual-state-only progress request initially failed with `progress.missing` on the real Host; the API now accepts consumption-only progress, with a Host regression test. Unit tests cover book-vs-audio field independence and the 95% reading auto-finish.
