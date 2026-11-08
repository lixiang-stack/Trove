# 09 — 播客 RSS 单集入库

Status: ready-for-agent  
Type: task  
Milestone: M0  
Blocked by: 05, 06, 07  
Spec: [spec.md](../spec.md)  
Requirements: FR-04, FR-06, FR-07, FR-85

## Context

播客是核心内容来源之一，但 MVP 只做“粘贴 feed、预览最近单集、选一集入库”，不订阅、不轮询。feed 和 enclosure 是用户提供的任意公网 URL，必须走 SSRF 防护。

## Scope

- Safe HTTP 客户端：只允许 http/https、逐次重定向校验、拒绝私网/回环/元数据/CGNAT、超时和大小限制。
- feed 获取与 feedparser 解析；展示标题、作者、最近 50 集、发布日期、时长、enclosure。
- 选择一集后下载 enclosure，校验类型/大小，FFmpeg 转 64kbps 单声道 AAC，创建 Item + Run。
- `source_key = feed_url#episode_guid`（GUID 缺失时用 enclosure URL）；重复选集返回已存在。
- 不订阅、不轮询、不后台刷新；错误分类（feed 解析/网络/类型/大小）。

## Acceptance Criteria

- [ ] 用 RSS fixture 预览最近单集，字段完整；用户可选择任意一集。
- [ ] 选择后生成 Item、内容包音频和 `queued` Run；来源保留 feed URL、单集 GUID、原始 enclosure URL。
- [ ] 私网/元数据/非 http(s) URL 被拒绝；重定向到私网也被拒绝。
- [ ] 重复选择同一集返回已存在，不重复下载。
- [ ] 超过大小/类型限制的 enclosure 被拒绝并清理临时文件。
- [ ] 没有订阅/轮询副作用；重新打开 feed 不会自动入库。

## Testing

- Host seam + fake FeedClient/SafeHttpClient：预览、选集、重复、拒绝。
- SSRF 单元测试：回环、私网、链路本地、元数据、CGNAT、重定向。
- 真实 feed 手动测试（可选）；不默认访问网络。
- 移动端预览/选集冒烟。

## Out of Scope

- 播客订阅、自动更新、播放列表；MVP 不做。
- 转写/整理/索引；由 13/17/14 接入。
