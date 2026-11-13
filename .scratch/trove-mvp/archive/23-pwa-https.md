# 23 — PWA 安装壳与 HTTPS 前置

Status: resolved
Disposition: closed 2026-11-13 — optional PWA; acceptance SKIPPED; known issues retained in acceptance.md.
Acceptance: SKIPPED — all PWA acceptance is skipped by user decision (2026-11-13).
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

## Manual Acceptance (真实设备)

PWA 是可选 P1，但 HTTPS 安装和真机行为只能在手机上确认。以下项目已由
`tests/test_pwa.py` 和 `tests/test_browser.py` 覆盖，不列入人工表：

- manifest 内容、图标尺寸、主题色和 `standalone`
- service worker 注册、根 scope、`no-store`
- 只缓存 `/static/`，不缓存 HTML/API/media
- 断网时 API 请求失败而不是返回旧内容
- headless 下的持久播放器、搜索、阅读

### 准备

```bash
BASE=https://<host>.<tailnet>.ts.net
```

使用 Tailscale Serve 或 Caddy 内部 CA 的 HTTPS 地址；手机必须信任对应证书。

### 人工验收表

| # | 测试项 | 测试方法（最简单） | 期望结果 | 实际结果 |
| -: | ------ | ------------------ | -------- | -------- |
| 1 | HTTPS 安装与应用信息 | 手机浏览器打开 `$BASE`，使用浏览器菜单选择“安装应用/添加到主屏幕” | 可安装；桌面图标、名称 `拾藏 Trove`、主题色正确；打开后无浏览器地址栏（standalone），入口进入 `/library` 或登录页 | SKIPPED |
| 2 | 安装态基本使用 | 从主屏幕打开已安装应用，登录后播放一条音频、切换 Library/Search、打开 transcript 和 EPUB 章节 | 播放器保持；搜索和阅读可用；导航时音频不中断 | SKIPPED（已知问题见下表） |
| 3 | 升级后不长期使用旧 HTML/CSS | 部署一个新版本并重启服务，关闭再打开已安装应用，检查页面资源版本是否更新 | 打开的是新 HTML/CSS；没有长期停留在旧界面 | SKIPPED |
| 4 | HTTP/不支持环境降级 | 用 HTTP 地址（受信任局域网）或不支持安装的浏览器打开同一 Host，登录并播放/搜索 | 普通浏览器功能正常；不出现安装提示或安装失败也不影响使用 | SKIPPED |

第 2 项与 Q10 手机播放验收可共用记录。第 3 项只在有实际部署时执行；没有新版本时记录“未执行”并说明原因。

### 已知问题（PWA 验收已跳过，2026-11-13）

| ID | 现象 | 补充信息 | 当前状态 |
| -- | ---- | -------- | -------- |
| PWA-1 | p=1 播放音频会自动卡住 | 手机经 Tailscale 访问；音频文件本身可被 ffprobe 读取 | 已提交播放器修复 `3ae489b`；已记录，不阻塞 |
| PWA-2 | 列表行播放按钮显示未播放，展开卡片显示播放中 | 行按钮与 inline 卡片状态不同步 | 已提交播放器修复 `3ae489b`；已记录，不阻塞 |
| PWA-3 | p=2 音频无法播放 | 同一 B 站 BV 的第二 P；音频 artifact 存在且 AAC-LC/faststart 正常 | 已提交播放器修复 `3ae489b`；已记录，不阻塞 |
| PWA-4 | 整体体验很卡 | Tailscale 状态显示手机经 `relay "hkg"`，需确认是否直连；页面转写/列表也会放大延迟 | 播放器 DOM 更新已节流；Tailscale 验收已跳过 |
| PWA-5 | 偶发 autoplay blocked / cannot play this audio | 切换音频源时旧 `play()` Promise 被中断 | 已提交播放器修复 `3ae489b`；已记录，不阻塞 |
| PWA-6 | Library/Search 的 Type、Status、Tag、Source 标签值视觉混乱 | 四组 chip 全部展开，字号/换行/层级缺少区分，手机宽度下尤其拥挤 | 已知问题，不阻塞 |
| PWA-7 | Search 页面滚动时搜索框固定在上端，不随页面滚动 | 移动端 CSS `.search-form { position: sticky; top: 62px; }` | 已知问题，不阻塞 |

PWA-4 的网络因素需要单独确认：`tailscale status` 若长期显示 `relay` 而不是 `direct`，音频流会明显变慢；这与播放器代码问题分开记录。

## Acceptance Record

| 字段 | 值 |
| ---- | -- |
| 执行日期 | 2026-11-13 |
| Host 版本 | `待填`（测试时未记录） |
| 手机 / 系统 / 浏览器 | Xiaomi 13 / Android / 待填 |
| HTTPS 方式 | Tailscale Serve |
| 自动化证据 | `./scripts/check.sh` PASS；CI: [run 43413162565](https://github.com/lixiang-stack/Trove/actions/runs/43413162565) |
| 人工表结果 | **SKIPPED**（已知问题 PWA-1..PWA-7，不阻塞） |
| 结论 | **SKIPPED** |
| 失败项与 follow-up issue | PWA-1..PWA-5 已提交 `3ae489b`；PWA-6、PWA-7 作为已知问题保留；不作为放行门控 |

PWA 为可选项，不阻塞 Q10 和 MVP 验收；但 HTTPS 安装失败或普通浏览器降级不可用时，必须记录并开 follow-up issue。

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

2026-11-13 — 真机 PWA 人工验收未通过：播放稳定性、播放器状态同步、Library/Search 过滤标签布局和 Search sticky 搜索框均有问题。详细失败项见 `Manual Acceptance` 的“失败项（2026-11-13）”表。播放器相关修复已提交 `3ae489b`，需真机复测；PWA-6/PWA-7 仍需修复。

2026-11-13 — 用户决定：后续所有 PWA 验收跳过，不作为 MVP 放行门控。播放器修复和界面已知问题保留记录。

2026-11-13 — 关闭为可选 PWA，不再做 MVP 工作。PWA-1..PWA-5 的播放器修复已提交 `3ae489b`；PWA-6/PWA-7 作为移动 Web 已知问题记录在 `../acceptance.md`。PWA 与 Tailscale 验收均不作为放行门控。
