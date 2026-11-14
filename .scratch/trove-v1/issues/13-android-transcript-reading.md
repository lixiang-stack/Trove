# 13 — Android Transcript 阅读与文内搜索

Status: ready-for-agent
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

- [ ] 真实 long transcript 可分段显示，时间戳格式正确。
- [ ] 文内搜索命中/高亮正确；清空搜索恢复全部。
- [ ] 离线可读已下载 transcript；未下载有明确提示。
- [ ] 导航/展开收起不丢播放状态。
- [ ] 不实现点击 transcript 跳音频/同步滚动。
- [ ] 大 transcript 列表滚动流畅。

## Testing

- App seam：transcript fixture 解析、搜索/高亮、离线/错误状态；真 Room。
- 1,000+ 段列表性能冒烟。
- 不测播放器内部；由 11 覆盖。

## Out of Scope

- 本地全文搜索；由 15 实现。
- transcript 编辑/替换；MVP Web 已有，Android V1 不做。
- 点击跳转/同步滚动。
