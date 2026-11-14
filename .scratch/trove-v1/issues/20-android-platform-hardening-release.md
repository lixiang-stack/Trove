# 20 — Android 平台硬化与 Release 构建

Status: ready-for-agent
Type: task
Milestone: M3
Blocked by: 01, 11, 12, 18
Spec: [spec.md](../spec.md)
Tech: [tech-selection.md](../tech-selection.md)
Requirements: FR-70, FR-72, NFR-11
ADRs: [0009](../../../docs/adr/0009-native-android-client-app-managed-sync.md)

## Context

功能完成后需要把 Android 平台行为收口：通知权限、前台服务类型、HTTPS/用户 CA、独立 LAN flavor、备份/日志脱敏、R8 和可安装的 release APK。V1 是个人侧载分发，不做 Play Store。

## Scope

- 权限/FGS：`POST_NOTIFICATIONS`、`FOREGROUND_SERVICE_MEDIA_PLAYBACK`、`FOREGROUND_SERVICE_DATA_SYNC`、`WAKE_LOCK`、网络权限。
- `MediaSessionService`/WorkManager 前台服务声明；Android 13+ 通知权限引导。
- 网络：release HTTPS-only；`lan` flavor 允许受信任局域网 cleartext 并持续警告；Caddy 用户 CA 信任；`debug` 可 localhost cleartext。
- `allowBackup=false`；日志/诊断脱敏；不打印 token/Authorization。
- R8/minify/resource shrinking；release APK 签名/版本号；sideload 安装验证。
- CI：Android JVM/Compose 测试 + lint；instrumented 本地/专用 runner。
- 小米电池优化设置入口；OEM 后台限制说明。
- APK 体积/权限/隐私检查。

## Acceptance Criteria

- [ ] Release APK 可安装/启动；R8 不破坏 Retrofit/Room/Readium/Media3。
- [ ] 通知权限/FGS 类型正确；后台播放/下载在真机可用。
- [ ] Release 拒绝明文 HTTP；`lan` flavor 可用且持续警告；Caddy 用户 CA 可按文档配置。
- [ ] `allowBackup=false`；日志/诊断无 token/password/Cookie/完整路径。
- [ ] CI 绿；release 包体积/权限无意外增长。
- [ ] 不包含 Play Store 上架/签名托管。

## Testing

- Release build + 真机安装/播放/下载/阅读冒烟。
- 权限/网络配置/备份/日志脱敏检查；R8 后 smoke。
- 不把模拟器通过当真实设备通过。

## Out of Scope

- Play Store 上架、商店合规、应用内购买。
- iOS/平板/TV/Wear。
