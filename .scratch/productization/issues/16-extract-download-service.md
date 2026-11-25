# 16 — 抽取下载服务（gated）

Status: needs-triage
Type: task
Milestone: P4
Blocked by: 08, 09
Spec: [spec.md](../spec.md)

## Context

下载阶段依赖 yt-dlp、FFmpeg、cookies 和网络出口；平台限流、代理、地区限制和登录态会让它成为独立故障域。L1 的 download pool 已能隔离并发；只有在需要独立代理/出口 IP、cookies 池、平台限流隔离或多机下载时，才抽成独立服务。服务实现继续用 Python。

## Scope

- 定义契约（HTTP 或本地队列）：
  - 输入：canonical URL、source type、cookies/代理配置引用、幂等键。
  - 输出：媒体文件路径/对象 key + 元数据（title/author/duration/language）或稳定错误码。
  - 健康、指标、版本、取消语义。
- Python 服务：包装 yt-dlp/HTTP 下载；每任务独立临时目录；大小/超时限制；代理/cookies 配置；失败分类。
- 调用侧：新增 `RemoteDownloader` 适配器，实现 `Downloader` 端口；feature flag；保留 in-process fallback。
- 部署：Compose service / launchd agent；共享卷或对象存储；出口网络配置。
- 合规：文档明确 cookies/代理能力不等于内容授权；保留现有错误码和用户责任边界。

## Acceptance Criteria

- [ ] 契约文档和 contract fixtures 存在；错误码与现有 `download.*` 对齐。
- [ ] `RemoteDownloader` 通过 `Downloader` 合同测试；输出元数据与 in-process 一致。
- [ ] 下载服务可独立重启/限流，不影响 API 和 ASR。
- [ ] 代理/cookies 配置可用，且不写入日志/镜像。
- [ ] feature flag 可一键切回 in-process；切换不丢任务。
- [ ] 现有 video/podcast/EPUB 下载测试在 remote 模式下通过。
- [ ] 部署文档和合规说明更新。

## Testing

- 契约：同一 URL（或 fake server），in-process vs remote 输出结构和错误码一致。
- 故障：超时、403、地区限制、磁盘满、服务重启。
- 网络：代理/cookies 场景（可用 fake/本地 server，避免真实平台）。
- 端到端：download service → audio → ASR → organize → index。

## Out of Scope

- Go 重写；yt-dlp 是 Python，Go 只能包 CLI。
- 绕过平台授权/DRM；不做内容抓取策略变更。
- 多租户/按用户配额。
- 把 ASR/整理也拆成服务（15/17）。

## Notes

- 下载服务是最需要“网络出口”隔离的；如果单机不需要代理，保持 pool 即可，不要提前拆。
- 文件传递优先共享卷；跨机时再用对象存储 + 预签名 URL。
- yt-dlp 版本升级要有 canary；服务化后仍要锁定版本。
