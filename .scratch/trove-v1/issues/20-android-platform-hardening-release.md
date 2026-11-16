# 20 — Android 平台硬化与 Release 构建

Status: implemented
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

- [ ] Release APK 可安装/启动；R8 不破坏 Retrofit/Room/Readium/Media3。签名 APK 已安装/启动，release 拒绝明文 HTTP；完整 HTTPS 登录/播放/下载/阅读 R8 冒烟待 [23](23-v1-release-device-acceptance.md)。
- [x] 通知权限/FGS 类型正确；后台播放/下载在真机可用（FGS 声明与既有真机 `types=0x2/0x1` 证据；release 真机冒烟待 23）。
- [x] Release 拒绝明文 HTTP；`lan` flavor 可用且持续警告；Caddy 用户 CA 可按文档配置。
- [x] `allowBackup=false`；日志/诊断无 token/password/Cookie/完整路径。
- [x] CI 绿；release 包体积/权限无意外增长。
- [x] 不包含 Play Store 上架/签名托管。

## Testing

- Release build + 真机安装/播放/下载/阅读冒烟。
- 权限/网络配置/备份/日志脱敏检查；R8 后 smoke。
- 不把模拟器通过当真实设备通过。

## Out of Scope

- Play Store 上架、商店合规、应用内购买。
- iOS/平板/TV/Wear。

## Implementation

- 平台声明沿用并验证：`POST_NOTIFICATIONS`、`FOREGROUND_SERVICE_MEDIA_PLAYBACK`、`FOREGROUND_SERVICE_DATA_SYNC`、`WAKE_LOCK`、网络权限；新增 `PlatformManifestTest` 检查权限和两个前台服务类型。
- 新增 `prod`/`lan` 两个 flavor，`lan` 使用独立 application id、允许受信任私有地址明文 HTTP，并在所有页面顶部持续显示警告；`lanRelease` 被禁用，避免 LAN 包进入正式分发。
- 主 network security config 默认禁止明文并信任 system + user CA（Caddy）；debug 只放行 localhost/emulator，`lanDebug` 放行私有 LAN。`HostUrl` 增加 LAN 地址校验（RFC1918/回环/链路本地/ULA/`.local`），release 仍拒绝一切明文。
- Release 启用 R8 + resource shrinking；签名从 `TROVE_RELEASE_*` 环境变量或 Gradle properties 读取，keystore 不入库。`scripts/android/release-check.sh` 检查签名、debuggable、权限 allowlist 和 35 MiB 目标；签名 APK 实测 9 MiB。
- CI/lefthook 更新为 prod debug 构建/单测/lint，并新增 `assembleProdRelease` + `assembleLanDebug`；设备脚本安装 `prodDebug` 并跑 core + app instrumented tests。
- 日志只输出异常类名；Settings 增加 App 版本和小米/红米自启动/省电策略说明；新增 `docs/android.md`，补充 Caddy 用户 CA、release 签名、LAN、OEM、APK 检查步骤。
- 真机：签名 release APK 安装/启动和明文拒绝 PASS；Caddy/Tailscale HTTPS、完整 R8 登录/播放/下载/阅读冒烟、60 分钟后台播放待 [23](23-v1-release-device-acceptance.md)。
