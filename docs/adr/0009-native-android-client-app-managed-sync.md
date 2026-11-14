# V1 采用 native Android 客户端与 app-managed sync

V1 的主要消费端从桌面/移动 Web 转移到 Android 手机：Q10 手机 Web 未被接受，浏览器无法稳定提供后台/锁屏播放、离线音频/阅读/搜索、可续传下载和本地索引。因此 V1 采用 Kotlin + Jetpack Compose 的 native Android 客户端；Host 仍是 Mac 上的 Python/FastAPI/SQLite，Content Package 仍是事实源；同步由客户端管理，使用 manifest + cursor、tombstone、可续传下载和按字段 last-write-wins。Consumer Web Shell 保留为桌面/管理壳，不再作为 V1 的移动消费验收路径。

**Status**: Accepted · 2026-11-14

## Considered Options

- 强化移动 Web/PWA：能复用服务端渲染的 Web Shell，但 Q10 未接受当前手机 Web 壳，真机 PWA 已暴露播放/状态/布局问题；后台播放、离线缓存、大文件续传和离线搜索仍要另建本地数据层，且受浏览器/OEM 后台限制。不作为主要消费端。
- Hybrid（Capacitor/React Native/Flutter）：可复用部分 Web/JS 资产，但后台播放、下载、本地索引仍要原生模块；WebView 阅读器和插件质量增加不确定性，对 V1 的 P0/P1 并不更简单。不采用。
- iOS 优先或跨平台优先：需求明确 iOS 为 P3，用户只有 Android；V1 不需要为 iOS 支付抽象成本。不采用。
- 桌面 App（Tauri/Electron）：需求明确不做桌面 App；桌面继续用 Host Console/Consumer Web Shell。不采用。
- Native Android（选中）：Media3 覆盖后台播放/媒体通知，WorkManager 覆盖可续传/约束下载，Room 覆盖本地库/索引，Readium 覆盖 EPUB；与 FR-70/71/72/73、NFR-11 的验收直接对齐。代价是新增 Kotlin/Gradle 代码库和 Android 发布链路。

## Consequences

- 新增 native Android 代码库和 Android CI（JVM/Compose 测试、lint；instrumented 测试在本地/专用 runner 跑）；V1 以 sideload/个人分发为主，不承诺 Play Store 上架。
- Host 需要增量改动：设备 token/bearer 认证、Content/State 两条同步流、soft delete/tombstone、通用 Content Package 文件下载、`sync_epoch`、按字段时钟与 `Idempotency-Key`。现有 JSON API 保持向后兼容，OpenAPI 继续作为契约。
- Content Package 仍是事实源；Android 本地数据库/文件是选中 Item 的镜像，本地搜索索引可重建。Android 不复制 Host 的处理管线。
- 内容流与状态流分离：播放/阅读进度不递增 Item 内容版本，避免每 5 秒写进度导致 manifest 抖动；tombstone 和 `sync_epoch` 处理删除与 Host 备份恢复。
- Q10 手机 Web 不再是 V1 验收；Consumer Web Shell 的存在不影响 native 客户端。PWA 安装保留为可选，不作为核心播放器默认答案。
- EPUB 阅读采用 Readium，`book_locator` 升级为 `schema: 2`（保留 Web legacy 字段，增加 EPUB href/progression）；跨客户端位置映射需要测试。
- 主要运行风险：小米/OEM 后台限制、Caddy 内部 CA 的 Android 信任配置、手机存储配额、Readium locator 兼容性。V1 用真机手动验收和电池优化引导兜底，不承诺所有 OEM 行为一致。
- 测试采用两个 seam：现有 Host HTTP seam（真实 Host + fake 外部适配器）和新的 Android App seam（fake `TroveApi` + 真实 Room/Compose UI）；共享契约 fixture 防止两端漂移。
- 未来云端 Host 复用同一套 API/base URL 和资源形状；客户端不需要重做数据模型。iOS 仍不在 V1 承诺范围。
- 见 [V1 spec](../../.scratch/trove-v1/spec.md)、[trove-requirements.md](../ideas/trove-requirements.md) §5.8/§8.2、[trove-tech-selection.md](../ideas/trove-tech-selection.md)、[ADR-0002](0002-server-rendered-htmx-web-shell.md)、[ADR-0008](0008-content-package-as-source-of-truth.md)、[MVP acceptance](../../.scratch/trove-mvp/acceptance.md)。
