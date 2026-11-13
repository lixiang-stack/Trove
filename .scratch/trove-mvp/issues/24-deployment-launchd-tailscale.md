# 24 — macOS 部署、launchd 与 Tailscale Serve

Status: ready-for-agent  
Acceptance exception: Tailscale Serve verification is SKIPPED by user decision (2026-11-13); Caddy/localhost remains in scope.
Type: task  
Milestone: M3  
Blocked by: 01, 06, 13  
Spec: [spec.md](../spec.md)  
Requirements: FR-80, FR-83, FR-86, NFR-12, NFR-13, NFR-14  
ADRs: [0006](../../../docs/adr/0006-native-launchd-tailscale.md)

## Context

MVP 的 Host 是用户自己的 Mac，需要开机/登录后自动运行、崩溃自动重启、手机通过 HTTPS 访问。MLX/Metal 不能在 macOS Docker 里用，因此部署走原生进程。

## Scope

- 两个 launchd LaunchAgent：API/HTML 与 worker；`RunAtLoad`、`KeepAlive`、日志路径、工作目录、`TROVE_HOME`。
- 安装/卸载脚本：渲染 plist、加载/卸载、首次迁移、权限 0700/0600。
- `trove setup`/`trove doctor`：检查 FFmpeg/ffprobe/yt-dlp、下载 ASR 模型、检查 FTS5/数据目录/端口。
- Tailscale Serve 配置文档：绑定 127.0.0.1，`tailscale serve` HTTPS；Caddy 内部 CA 备选。
- 升级流程：`uv sync` → `trove db upgrade` → 重启；日志轮转；SQLite/导出备份说明。
- 可选 `caffeinate -i -w <pid>` 防止处理时空闲睡眠。

## Acceptance Criteria

- [ ] 在干净 Mac 上按文档安装后，API/worker 自动启动；kill 任一进程后 launchd 重新拉起。
- [ ] 重启 Mac 后队列/运行中 Run 恢复，服务可访问。
- [ ] `trove doctor` 能发现缺失 FFmpeg/yt-dlp/模型/FTS5 并给出命令。
- [ ] ~~Tailscale Serve 下手机可用 HTTPS 访问；Media Session/PWA 前置满足~~ **SKIPPED**（2026-11-13）；Caddy 备选仍有文档。
- [ ] 升级不丢数据；日志/备份路径明确；不使用 Docker/云服务。
- [ ] 安装/卸载不删除用户原始文件/内容包。

## Testing

- 手动部署检查清单：安装、自动启动、kill/restart、重启 Mac、Caddy HTTPS、升级、卸载；Tailscale 验收跳过。
- 部署后 Host seam 冒烟：health、登录、播放、搜索。
- 文档链接/命令可复制执行；`python3 scripts/check-docs.py` 通过。

## Out of Scope

- Docker、云主机、公网反向代理、多用户；不做。
- Q10 一周播放验证；由 25 执行。

## Comments

2026-11-10 — Added `trove service install/uninstall`, launchd plist rendering with
`RunAtLoad`/`KeepAlive`, separate logs, `TROVE_HOME`, and full `PATH`; wrapper
scripts perform the first migration. `trove doctor` now checks the listen port;
`trove setup` checks FTS5, `yt-dlp`, and the port as well. Documented Tailscale
Serve, Caddy, upgrade, backup, caffeinate, uninstall, and a deployment checklist
in `docs/deployment.md`. Real clean-Mac kill/reboot/HTTPS checks remain manual.

2026-11-13 — 用户决定：Tailscale Serve 验收跳过；launchd、doctor、Caddy/localhost 仍按本票验收。
