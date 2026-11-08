# 07 — B 站/YouTube 单视频 URL 入库

Status: ready-for-agent  
Type: task  
Milestone: M0  
Blocked by: 05, 06  
Spec: [spec.md](../spec.md)  
Requirements: FR-01, FR-06, FR-07, FR-13, FR-18, FR-85

## Context

最常见的收藏动作是粘贴一条 B 站/YouTube 视频链接。需要把 URL 变成 Item + Source，拒绝播放列表/多 P，调用 yt-dlp 下载音频，交给 FFmpeg 抽音频，并创建 Processing Run。

## Scope

- URL 规范化：去跟踪参数，YouTube `youtu.be`/watch 归一，B 站 BV/av 归一；保留 raw URL。
- 平台白名单：B 站/YouTube 单视频；明确拒绝 playlist、`list=`、多 P、直播/不支持类型。
- 重复添加：按规范化 URL 返回已存在 Item，不重复下载。
- yt-dlp 子进程下载最佳音轨；失败分类（网络/登录/地区/不支持/解析）；可选 cookies 配置。
- FFmpeg 抽取 64kbps 单声道 AAC；视频不落盘；写入 source 元数据并创建 Run。
- HTML/API 添加表单与错误提示；移动端可提交。

## Acceptance Criteria

- [ ] 用 fake yt-dlp 可添加 B 站、YouTube 各一条，生成 Item、Source、`audio.m4a` 和 `queued` Run。
- [ ] playlist/多 P/`list=` URL 被拒绝，提示明确，不创建 Item。
- [ ] 同一规范化 URL 第二次添加返回已存在，不重复下载。
- [ ] 下载失败时 Run 进入 `failed`，错误码可读；原有 Library 不受影响。
- [ ] 原始 URL、平台、标题、作者、发布日期、抓取时间在 Item 详情可见。
- [ ] 库内没有视频文件；只有音频和来源信息。
- [ ] 真实网络测试标记为 `network`，默认不跑；至少手动验证 B 站/YouTube 各一条。

## Testing

- Host seam + fake Downloader：成功、重复、拒绝、失败分类。
- 真实 FFmpeg fixture：从短音轨产出音频。
- 真实 yt-dlp 手动/网络测试：各平台单条视频。
- 移动视口表单提交冒烟。

## Out of Scope

- 本地文件、EPUB、播客 feed；由 08/09 实现。
- 转写、整理、索引；由 13/17/14 接入。
