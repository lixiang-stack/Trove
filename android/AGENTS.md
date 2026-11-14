# Android App 开发规范（Trove）

本文件只约束 `android/` 子树；根 [AGENTS.md](../AGENTS.md) 的通用规范仍然适用。进入 Android 开发前，按顺序阅读：

1. 根 [AGENTS.md](../AGENTS.md)
2. [产品 spec](../.scratch/trove-v1/spec.md)
3. [技术选型](../.scratch/trove-v1/tech-selection.md)
4. [ADR-0009](../docs/adr/0009-native-android-client-app-managed-sync.md)
5. 本文件

如果本文件与 spec/tech selection 冲突，以 spec/tech selection 为准，并先修正文档再改代码。

## 1. 范围

- 只做 native Android 客户端：登录、Library、播放、下载/离线、transcript、EPUB、搜索、Continue、Add、设置、同步。
- 不做 iOS、PWA 主客户端、云端、多用户、PDF/TTS/标注/语义检索/视频播放/Up Next/睡眠定时。
- 手机是主要听设备；后台/锁屏播放、媒体通知、离线播放是 P0，不能用“浏览器能播”替代。

## 2. 构建基线

- Kotlin、AGP、Gradle、JDK、compileSdk/targetSdk、minSdk 以 [技术选型](../.scratch/trove-v1/tech-selection.md) 和 `gradle/libs.versions.toml` 为准；这里的版本只是当前兼容链快照。
- 禁止动态版本（`+`、`latest.release`、range）；升级版本前先做 toolchain smoke，并更新技术选型/ADR。
- 当前基线：Kotlin 2.4.21、AGP 9.5.1、Gradle 9.7.0、JDK 21、compileSdk/targetSdk 37、minSdk 26。
- 不要为了“更新”而单独升级 Gradle/Kotlin/Compose/Readium；它们是兼容链，必须整体验证。

## 3. Module 与依赖方向

- Gradle module：`:app`、`:core`、`:playback`、`:reader`。
- 依赖只能从外向内：`:app` → `:playback`/`:reader` → `:core`；`:core` 不依赖 `:playback`/`:reader`/`:app`。
- spec 中的 `feature:*` 是 `:app` 内的 package 边界，不要为每个页面新建空 module。
- 新依赖必须说明收益；优先复用现有库。没有真实收益不引入 Hilt、Koin、Paging 3、MockK、代码生成客户端。

## 4. 架构约束

- UI：Kotlin + Jetpack Compose + **Google Material Design 3（Material 3）**；使用 `androidx.compose.material3`。
- DI：手工 `AppContainer` + ViewModel factory；不引入 Hilt/Koin。
- 导航：Navigation 3；不要默认回退 Navigation 2，除非有记录在案的兼容性问题。
- 播放：Media3 ExoPlayer + `MediaSessionService`；不在 UI 里直接持有 ExoPlayer。
- 阅读：Readium classic `EpubNavigatorFragment`；不使用 alpha Compose navigator。
- 本地 DB：Room + `androidx.sqlite:sqlite-bundled`；本地搜索用 FTS5，不用 Room FTS4/平台 SQLite。
- 网络：Retrofit + OkHttp + Kotlinx Serialization；Bearer 走 interceptor，不把 token 放 URL。
- Content Package 是事实源；Room/文件是选中 Item 的镜像；不要另建一套内容模型。

## 5. Material 3 与交互

- **遵循 Google Material Design 3（Material 3）**：使用 Material 3 的 color roles、typography、shape、elevation、motion。
- 优先使用 Material 3 组件：`Scaffold`、`TopAppBar`、`NavigationBar`、`Card`、`ListItem`、`BottomSheet`、`Dialog`、`Snackbar` 等。
- 自定义组件必须复用主题 token（颜色/字号/间距/圆角），不要散落硬编码颜色和魔法值。
- 支持浅色/深色主题；不引入 iOS/Cupertino 风格或与 Material 3 冲突的第三方设计系统。
- 无障碍：主要触控目标 ≥48dp、contentDescription、对比度、字体缩放、TalkBack 可读。
- 手机优先布局；不做平板/折叠屏专门布局，不引入多套设计语言。

## 6. 构建与测试命令

在 `android/` 下：

```bash
./gradlew :app:assembleDebug
./gradlew :app:testDebugUnitTest
./gradlew :app:lintDebug
./gradlew :app:connectedDebugAndroidTest   # 需要模拟器/真机
./gradlew :app:assembleRelease             # R8/release smoke
```

在仓库根目录：

```bash
python3 scripts/check-docs.py
./scripts/check.sh --fast                  # Host 侧回归
```

提交前至少：Android unit test/lint 绿；涉及 Host 改动时 Host 测试绿；文档检查绿。pre-push 只跑与改动路径相关的检查；`./scripts/check.sh --full` 留给 release/验收，不要求每次 push。

## 7. 测试缝

- **Host HTTP seam**：真实 Host + 临时 `TROVE_HOME` + 真实 SQLite/FTS5/文件；外部适配器 fake。
- **Android App seam**：通过公开 ViewModel/Compose UI 测试；fake `TroveApi` + 真实 Room/临时文件/Robolectric；共享 contract fixture。
- 只测外部行为（HTTP/JSON/文件/可见 UI/Room 公开查询），不测私有方法、内部调用顺序或 SQL 细节。
- 不用 MockK；用 fake API、fake repository、`TestAppContainer`。
- P0 功能（后台播放、下载续传、离线阅读、媒体通知）必须真机手动验收；模拟器通过不算。
- 新增/修改契约时，先更新 Host fixture，再让 Android DTO/测试消费同一组 fixture。

## 8. 安全红线

- 正式 release 只允许 HTTPS；明文 HTTP 只允许独立 `lan` flavor（持续警告、不随正式包发布）或 debug localhost。
- Token 存 Android Keystore 保护的加密存储；不打印 token/Authorization/Cookie；`allowBackup=false`。
- 不提供开放 URL 下载代理；Android 只从 Host 的 Content Package 文件端点下载。
- EPUB 内容按不可信处理：阻断远程资源/外部导航/内容脚本；用恶意 EPUB fixture 验证。
- Host URL/token 不进日志、崩溃报告、诊断导出；诊断信息要脱敏。
- 不在 release 中绕过证书校验或信任所有证书。

## 9. 同步与数据规则

- Content stream / State stream 两条流；播放进度不 bump content version。
- 写操作带 `client_updated_at` + `Idempotency-Key`；Host 按字段 LWW，客户端用 canonical 覆盖乐观值。
- SyncEngine 顺序：先推 PendingMutation，再拉 manifest，最后拉 state；有未推送本地写时跳过 state 拉取。
- `sync_epoch` 变化/cursor 无效时全量重同步；已下载文件按 sha256 复用。
- tombstone 删除本地；复活 Item 重新出现；删除/移除下载要区分。
- 下载默认包含 audio、transcript、book、book_json、ai、cover；`ai.json` 用于完整镜像，不跳过。

## 10. 变更纪律

- 只碰必须碰的；不做未要求的“可配置性/抽象/重构”；无关死代码只指出，不顺手删。
- 改架构、版本、API 契约或安全边界前，先更新 spec/tech selection/ADR，再改代码。
- 不静默偏离 spec；发现前提不成立，先记录并确认。
- 代码用英文；面向用户的文案用中文；领域术语用 GLOSSARY 的 Item/Source/Library/Content Package/Processing Run/State/Consumption State/Host。
- 完成定义：功能可验证、测试/lint/docs 绿、P0 真机验收、无未声明的 P2/P3 功能。
