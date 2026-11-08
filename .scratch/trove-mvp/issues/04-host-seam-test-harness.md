# 04 — Host Seam 测试骨架与 Golden Fixtures

Status: ready-for-agent  
Type: task  
Milestone: M0  
Blocked by: 01, 02  
Spec: [spec.md](../spec.md)  
Requirements: NFR-04, NFR-05  
ADRs: [0001](../../../docs/adr/0001-python-monolith-sqlite-worker.md)

## Context

Spec 已确认唯一的测试主缝是 Host HTTP/HTML 边界：启动真实 API + worker、临时数据目录、真实 SQLite/文件/FFmpeg/EPUB，外部网络和重工具用 fake。先把这个骨架和 fixture 建好，后续 issue 才能按统一 seam 写测试。

## Scope

- pytest + httpx 测试基座：临时 `TROVE_HOME`、迁移、真实 SQLite、启动 API 与 worker。
- Fake 端口：`Downloader`、`FeedClient`、`Transcriber`、`Organizer`；真实 FFmpeg、EPUB 解析、FTS5。
- 轮询 helper：等待 Run 到终态，带超时；禁止固定 sleep。
- Golden fixtures：EPUB2、EPUB3、1–2 秒公开领域音频、播客 RSS XML、transcript JSON。
- Playwright（Python）脚手架：启动同一个 Host，跑一个登录/首页冒烟；不建立第二产品缝。
- 网络测试标记与默认排除。

## Acceptance Criteria

- [ ] 一个新测试可以启动 Host、走 HTTP 完成登录并断言页面/JSON。
- [ ] Fake 端口可注入，测试不访问 YouTube/B 站/播客/DeepSeek。
- [ ] 真实 FFmpeg 能从短音频 fixture 产出 `audio.m4a`；真实 EPUB 解析 fixture 可读。
- [ ] worker 轮询 helper 在超时后失败并给出清晰诊断；不使用固定 sleep。
- [ ] `pytest` 默认不跑网络测试；`pytest -m network` 才跑标记测试。
- [ ] Playwright 冒烟测试可运行。

## Testing

- 本 issue 的测试即基座本身：一个 Host 冒烟、一个 fake 端口测试、一个真实 FFmpeg/EPUB fixture 测试、一个 Playwright 冒烟。
- 确认测试目录/临时数据在结束后清理。

## Out of Scope

- 业务功能测试；由后续 issue 补充。
- CI 服务配置；先保证本地 `pytest` 可运行。
