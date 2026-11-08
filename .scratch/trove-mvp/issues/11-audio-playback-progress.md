# 11 — 音频播放、Media Session 与进度

Status: ready-for-agent  
Type: task  
Milestone: M0  
Blocked by: 05, 06, 07, 08  
Spec: [spec.md](../spec.md)  
Requirements: FR-34, FR-35, FR-40, NFR-05, NFR-14  
ADRs: [0002](../../../docs/adr/0002-server-rendered-htmx-web-shell.md), [0006](../../../docs/adr/0006-native-launchd-tailscale.md)

## Context

音频是核心消费方式。需要把处理完成的音频以可拖动/可续播的方式提供给浏览器，并在 HTMX 导航时保持播放器不中断；同时保存播放位置和 Consumption State。

## Scope

- 音频 artifact 服务：`ETag`（sha256）、`Accept-Ranges: bytes`、Range 206、`Cache-Control: private`、防路径穿越。
- 持久播放器：`<audio>` 放在 `#main` 之外，HTMX 只替换主内容；播放/暂停/进度/倍速。
- B Now Playing：全屏播放/阅读；顶部返回 C 列表；返回后播放/进度保持。
- B 的 transcript 默认折叠，点击就地展开/收起；不另开 modal。
- Media Session 元数据与动作（播放/暂停/seek）；HTTPS 下验证锁屏/后台行为。
- 进度写回：每 5 秒 + 暂停/结束/pagehide；打开时恢复上次位置。
- Consumption State：未开始/进行中/完成自动更新；可手动标记完成/未完成。
- 手机宽度下的播放器布局。

## Acceptance Criteria

- [ ] Range 请求返回 206，带 ETag/Accept-Ranges；无 Range 返回完整音频。
- [ ] 播放/暂停/拖动/倍速可用；刷新或重新打开回到上次位置。
- [ ] 播放超过阈值自动进入进行中，接近结束/手动标记进入完成；状态在 Library/详情可见。
- [ ] HTMX 在 Library/Search/详情之间导航时，音频元素不被销毁、播放不中断。
- [ ] 从 C 列表进入 B、再返回 C 后，播放状态和进度保持。
- [ ] B transcript 默认折叠；点击标题就地展开，再次点击收起；展开/收起不丢播放状态。
- [ ] Media Session 元数据和动作在 HTTPS 手机浏览器可用（Q10 设备验证）。
- [ ] 路径穿越/未知 artifact 被拒绝，不返回任意文件。

## Testing

- Host seam：Range/ETag/404/路径穿越；进度 PUT 和恢复；Consumption State 转换。
- Playwright：播放/暂停/导航持久化/进度恢复；C→B→C；B transcript 展开/收起；移动视口。
- 真实手机 Q10 行为由 25 验证；本 issue 只保证实现和桌面/模拟器覆盖。

## Out of Scope

- Up Next、睡眠定时、视频播放、时间戳跳转；不做。
- 离线播放；V1 需求。
