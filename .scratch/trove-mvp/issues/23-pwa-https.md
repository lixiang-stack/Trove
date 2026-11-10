# 23 — PWA 安装壳与 HTTPS 前置

Status: ready-for-agent  
Type: task  
Milestone: M3  
Blocked by: 11, 12, 15  
Spec: [spec.md](../spec.md)  
Requirements: FR-86, NFR-14

## Context

PWA 是可选 P1，依赖 HTTPS；它可以让手机浏览器更像应用，但 MVP 不承诺离线内容。需要 manifest、图标和最小 service worker，只缓存 app shell，避免缓存 API/媒体造成陈旧内容。

## Scope

- Web app manifest：名称、图标、主题色、`display: standalone`、start URL。
- 最小 service worker：只缓存 app shell/静态资源；网络优先或更新提示；不缓存 API/媒体/内容。
- HTTPS 前置说明：Tailscale Serve（24）或 Caddy 内部 CA；localhost 例外。
- 安装提示/更新策略；失败时普通浏览器仍可用。
- 可选项：不阻塞 Q10 和 MVP 验收。

## Acceptance Criteria

- [ ] manifest 可被浏览器识别；图标/名称/standalone 正确。
- [ ] service worker 只缓存 app shell；断网时 API/媒体请求失败而不是返回旧内容。
- [ ] 更新后不会长期提供旧 HTML/CSS；有版本/更新机制。
- [ ] HTTPS 下可安装；HTTP/不支持环境可正常使用。
- [ ] 不影响持久播放器/搜索/阅读。

## Testing

- Playwright：manifest/SW 注册、离线时 API 不被缓存、更新后内容刷新。
- 手机手动安装冒烟（HTTPS）。
- 不测试离线播放/阅读；不做。

## Out of Scope

- 离线内容缓存、后台同步、push、V1 Android；不做。
- 强制安装；PWA 是可选。

## Comments

2026-11-10 — Added a web app manifest, 180/192/512 icons, a root-scoped service
worker that caches only `/static/` assets network-first, and non-blocking
registration. HTML/API/media are never cached; `/sw.js` is `no-store` with
`Service-Worker-Allowed: /`. HTTPS setup is documented in
`docs/deployment.md`. Playwright coverage verifies registration, shell-only cache
contents, and offline API failure.
