# 11 — Android Media3 播放与后台服务

Status: ready-for-agent
Type: task
Milestone: M1
Blocked by: 05, 10
Spec: [spec.md](../spec.md)
Tech: [tech-selection.md](../tech-selection.md)
Requirements: FR-70, FR-72
ADRs: [0009](../../../docs/adr/0009-native-android-client-app-managed-sync.md)

## Context

音频是手机主消费方式。需要 Media3 `MediaSessionService` 提供后台/锁屏播放、媒体通知、音频焦点、倍速和进度保存；这是 V1 的 P0，不接受“浏览器能播就行”。

## Scope

- Media3 ExoPlayer + `MediaSessionService`；`MediaController` 封装。
- 媒体通知/锁屏/蓝牙/车机控制；`MediaMetadata` 标题/作者/封面。
- 音频焦点、耳机拔出、来电暂停/恢复；`setAudioAttributes(..., handleAudioFocus = true)`。
- 播放/暂停、seek、1×/1.25×/1.5×/2×；一次只播放一个 Item。
- 播放位置每 5 秒 + 暂停/停止/切换保存；先写 Room，再排队同步。
- 已下载优先本地文件；未下载走 Host `/api/items/{id}/files/audio` Range 流；`OkHttpDataSource` 加 Bearer。
- 播放错误映射可读提示并允许重试；播放结束标记完成。
- 不实现队列/Up Next/睡眠定时。

## Acceptance Criteria

- [ ] 后台/锁屏连续播放 ≥60 分钟；媒体通知/锁屏控制可用。
- [ ] 播放/暂停/seek/倍速/恢复位置正确；切换页面不中断。
- [ ] 音频焦点/耳机拔出/来电行为合理；不会两个声音同时播放。
- [ ] 本地/流式播放都能工作；Bearer 流式请求不带 token 到 URL。
- [ ] 播放结束自动标记完成；手动状态由 16 接入。
- [ ] 无队列/睡眠定时；不实现 transcript 跳转。

## Testing

- App seam：播放状态机、位置保存、错误映射；fake player/controller。
- Instrumented：Media3 service/通知/锁屏 metadata；不在默认 CI 跑。
- 真实 Xiaomi 13：1 小时后台播放、蓝牙、媒体通知、续听。

## Out of Scope

- 下载/离线存储；由 12 实现。
- transcript 阅读/搜索；由 13 实现。
- Up Next、睡眠定时、视频播放。
