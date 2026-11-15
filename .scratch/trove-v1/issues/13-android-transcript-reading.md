# 13 — Android Transcript 阅读与文内搜索

Status: resolved
Type: task
Milestone: M1
Blocked by: 10, 12
Spec: [spec.md](../spec.md)
Tech: [tech-selection.md](../tech-selection.md)
Requirements: FR-71, FR-72
ADRs: [0009](../../../docs/adr/0009-native-android-client-app-managed-sync.md)

## Context

Transcript 是阅读和搜索定位的主要文本。Android 需要从 `transcript.json` 建立本地分段，在播放页/阅读页展示时间戳和文本，并支持文内搜索/高亮；离线时仍可读已下载 transcript。

## Scope

- 下载/解析 `transcript.json`，写入 Room `TranscriptSegment`。
- Transcript 阅读页/播放页折叠区：`seq`、`start_ms`、`end_ms`、`text`。
- 文内搜索：过滤/高亮匹配分段；不做音频跳转/同步滚动。
- 播放页与 transcript 页共享当前 Item；不因导航销毁播放器。
- 离线读取已下载 transcript；未下载时显示需要网络/下载。
- 解析失败/空 transcript 显示明确状态。

## Acceptance Criteria

- [x] 真实 long transcript 可分段显示，时间戳格式正确。
- [x] 文内搜索命中/高亮正确；清空搜索恢复全部。
- [x] 离线可读已下载 transcript；未下载有明确提示。
- [x] 导航/展开收起不丢播放状态。
- [x] 不实现点击 transcript 跳音频/同步滚动。
- [x] 大 transcript 列表滚动流畅。

## Testing

- App seam：transcript fixture 解析、搜索/高亮、离线/错误状态；真 Room。
- 1,000+ 段列表性能冒烟。
- 不测播放器内部；由 11 覆盖。

## Out of Scope

- 本地全文搜索；由 15 实现。
- transcript 编辑/替换；MVP Web 已有，Android V1 不做。
- 点击跳转/同步滚动。

## Implementation

- `TranscriptParser` reads `transcript.json` (`seq`/`start_ms`/`end_ms`/`text`), validates duplicate/negative seq and timestamp ranges, and writes `TranscriptSegmentEntity` through `TranscriptRepository`; malformed and empty files produce explicit states.
- Player shows a transcript preview and a full transcript page; the full page filters in-page and highlights all matches with an `AnnotatedString`. Timestamps use the same `m:ss` / `h:mm:ss` format as the Web shell.
- Transcript screen reads only the local download; missing/not-downloaded states are explicit. Playback lives in the Media3 service, so navigating between player/transcript does not interrupt it. No click-to-seek or synchronized scrolling.
- Tests: `TranscriptRepositoryTest` including the golden fixture, search/highlight/timestamp cases and a 1,000-segment parse smoke; `TranscriptFlowTest` covers offline display, search filtering, and the not-downloaded prompt.

### Xiaomi 13 real-device acceptance (2026-11-15 / Android 16, API 36)

- Open/downloaded transcript rendered all 3 golden segments with `m:ss` timestamps; the player preview and full transcript page both worked.
- Searched `context`: list filtered to the one matching segment, highlight was visible in the rendered UI, and `1 个匹配` was shown. Clearing the query restored all 3 segments.
- With Host, Wi-Fi/data, and `adb reverse` unavailable, the downloaded transcript still rendered in full.
- Navigating Player → Transcript → Player kept the Media3 session alive and did not change a paused playback state. Empty/malformed/not-downloaded states and a 1,000-segment parse/query smoke test are covered by JVM/Robolectric tests.
