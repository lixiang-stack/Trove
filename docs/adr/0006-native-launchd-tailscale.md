# 原生 macOS 部署 + launchd + Tailscale Serve

MVP 的 Host 是用户自己的 Mac，处理依赖 MLX/Metal，且手机端 Media Session/PWA 需要 HTTPS。因此不使用 Docker 或桌面 App：用 `uv` 运行 API 与 worker 两个原生进程，由 launchd 常驻；默认只绑定 127.0.0.1，手机通过 Tailscale Serve 获得有效 TLS 证书；单用户认证用 Argon2id + 签名 Cookie，Caddy 内部 CA 作为无 Tailscale 时的备选。

**Status**: Accepted · 2026-11-08

## Considered Options

- Docker：macOS 容器无法使用 MLX/Metal，本地视频路径和 launchd 也更麻烦。
- 直接 LAN HTTP：没有 secure context，Media Session/PWA 不承诺；仅作为受信任局域网的管理入口。
- 公网反向代理/云主机：MVP 不做云端/公网暴露；Tailscale 是 VPN 路径。
- 桌面 App（Tauri/Electron）：需求明确不做桌面 App。

## Consequences

- 方案绑定 macOS/Apple Silicon；launchd 负责重启/开机启动，队列在 SQLite 中恢复。
- Tailscale 是可选依赖；不装时用 Caddy 内部 CA 或桌面本机访问。
- HTTPS 是 Q10 手机播放验收的前提；单用户认证始终开启。
- 见 [技术选型](../ideas/trove-tech-selection.md) 第 3.5、3.6 节；需求 FR-80/83/84/86、NFR-12/13/14。
