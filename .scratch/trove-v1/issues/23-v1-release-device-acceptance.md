# 23 — V1 release 真机验收补齐

Status: ready-for-agent
Type: task
Milestone: M3
Blocked by: 20
Spec: [spec.md](../spec.md)
Tech: [tech-selection.md](../tech-selection.md)
Requirements: FR-70, FR-72, NFR-11
ADRs: [0009](../../../docs/adr/0009-native-android-client-app-managed-sync.md)

## Context

M3 自动化、release 构建和契约收口已完成，但 60 分钟后台播放仍未验证。
2026-11-17 首轮连续播放到 32:06 时因使用手机被中断；用户明确跳过干净重跑。
release 安装/启动、明文拒绝、重装 Library/进度、EPUB 离线/图片/脚注和离线进度回写
已在真机 PASS。此 issue 只补验收证据，不引入新功能。

## Scope

- 安装签名 `prodRelease` APK（先卸载 debug），冷启动、登录、流式播放、下载、离线播放、EPUB。
- 60 分钟连续后台/锁屏播放；媒体通知、蓝牙控制、耳机拔出、来电/音频焦点。
- Caddy 用户 CA 或 Tailscale HTTPS 连接；release 拒绝明文 HTTP；`lan` flavor 警告和私有地址连接。
- 下载中断/续传、sha 校验失败重下、存储配额不足；token 撤销/密码修改。
- 重装后 Library/进度恢复；下载选择需按 issue 24 处理。
- 记录证据到 `.scratch/trove-v1/acceptance.md` 并更新结论。

## Acceptance Criteria

- [ ] 签名 release APK 可安装/启动，R8 后播放/下载/阅读/搜索无崩溃。
- [ ] 60 分钟后台/锁屏播放 PASS；蓝牙/耳机/音频焦点 PASS 或有明确例外。
- [ ] Caddy/Tailscale HTTPS 与用户 CA 配置 PASS。
- [ ] 下载续传/sha/配额与 token 撤销在真机 PASS。
- [ ] 重装恢复 Library/进度，下载选择例外按 issue 24 记录。

## Testing

- 真机 Android；不使用模拟器替代后台播放/媒体通知。
- 使用 `scripts/android/acceptance-host.sh` 和真实 Host HTTPS 各跑一次。

## Out of Scope

- 新功能；发现缺口另开 issue。
