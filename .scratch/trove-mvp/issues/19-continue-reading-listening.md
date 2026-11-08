# 19 — Continue：最近在听/在读一键继续

Status: ready-for-agent  
Type: task  
Milestone: M2  
Blocked by: 11, 12, 16  
Spec: [spec.md](../spec.md)  
Requirements: FR-36, FR-39, FR-40

## Context

用户经常隔几天回来继续听/读。MVP 需要一个 Continue 入口：最近在听/在读的 Item，一键回到上次位置；不做 Up Next 队列。

## Scope

- Continue 列表：最近有进度的 Item，按最近消费排序；区分听/读。
- 一键继续：音频恢复播放位置；书恢复章节/位置。
- 空状态：没有进行中内容时引导到 Library/Add。
- Continue 入口在 P1 加入导航；与 Library 排序共用消费数据。
- 完成/手动标记完成后从 Continue 移除或标记。

## Acceptance Criteria

- [ ] 播放/阅读产生进度后，Item 出现在 Continue；点击恢复到正确位置。
- [ ] 最近消费优先；完成的 Item 不出现在“继续”主列表（或明确标记）。
- [ ] 空状态、无进度、未知 Item 有清晰处理。
- [ ] Continue 入口在桌面/手机导航可见（P1）。
- [ ] 不实现 Up Next/队列。

## Testing

- Host seam：进度/状态 → Continue 列表 → 恢复。
- Playwright：音频/书一键继续、空状态、手机布局。
- 与 11/16 的进度测试共用 fixture。

## Out of Scope

- Up Next、睡眠定时、播放列表；不做。
- 跨设备同步；V1。
