# 01 — Android toolchain smoke 与工程骨架

Status: ready-for-agent
Type: task
Milestone: M0
Blocked by: none
Spec: [spec.md](../spec.md)
Tech: [tech-selection.md](../tech-selection.md)
Requirements: NFR-08, NFR-11
ADRs: [0009](../../../docs/adr/0009-native-android-client-app-managed-sync.md)

## Context

Readium 3.4.0 把 V1 的构建基线推到 compileSdk 37 / Gradle 9.7 / Kotlin 2.4.x，AGP 9 又启用 built-in Kotlin；Compose + KSP + Readium + Media3 的组合必须先验证。这个 issue 不实现产品功能，只建立可编译、可安装、可测试的 Android 工程和 CI。

## Scope

- 新建 Android Gradle 工程（Kotlin DSL + version catalog），4 个 module：`:app`、`:core`、`:playback`、`:reader`。
- 固定 tech selection 的基线：Kotlin 2.4.21、AGP 9.5.1、Gradle 9.7.0、JDK 21、compileSdk/targetSdk 37、minSdk 26。
- 接入依赖：Compose BOM/Material3、Navigation3、Media3、Room + KSP、WorkManager、Retrofit/OkHttp、Kotlinx Serialization、DataStore、Coil、Readium。
- Compose 空壳 + 底部导航占位；Application/AppContainer 骨架；遵循 Google Material Design 3（Material 3）。
- 创建/维护 `android/AGENTS.md`（Android 开发规范，含 Material 3、构建/测试/安全约束）。
- Android CI：JDK 21、SDK 37、Gradle cache，跑 `assembleDebug`、unit test、lint。
- 在 Xiaomi 13 上安装并启动空壳。
- 记录任何版本降级/opt-out；若 smoke 失败，按 tech selection 整体回退到 Readium 3.2 / compileSdk 36 档，并更新 tech selection。

## Acceptance Criteria

- [ ] `assembleDebug` 成功，Readium/Media3/Room/KSP 依赖全部解析。
- [ ] 空壳在 Xiaomi 13 安装并启动，无 crash。
- [ ] `:app` 的 unit test/lint 在 CI 通过。
- [ ] 4 个 module 的依赖方向正确：feature 不反向依赖 app；`core` 不依赖 playback/reader。
- [ ] `android/AGENTS.md` 存在并包含 Material 3、构建基线、测试/安全约束。
- [ ] 未实现登录、Library、播放、阅读等产品功能。
- [ ] 版本/兼容性问题有记录和结论。

## Testing

- Gradle build + CI；Robolectric smoke；真机启动手动记录。
- 不测试业务行为。

## Out of Scope

- 登录、Library、播放、下载、阅读、搜索；由后续 issue 实现。
- release APK/签名/Play Store；由 20 处理。
