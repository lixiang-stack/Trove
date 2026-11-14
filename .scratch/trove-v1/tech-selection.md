# 拾藏 / Trove — V1 技术选型

> 状态：v0.2（细化已确认；进入实现前先做 toolchain smoke）
> 日期：2026-11-14
> 依据：[V1 spec](spec.md)、[trove-requirements.md §5.8/§8.2](../../docs/ideas/trove-requirements.md)、[ADR-0009](../../docs/adr/0009-native-android-client-app-managed-sync.md)、[GLOSSARY.md](../../GLOSSARY.md)
> 范围：native Android 客户端 + Host 的设备认证、同步、文件下载与 tombstone 变更；不含云端、多用户、iOS。

## 0. 结论

V1 采用 **Kotlin/Compose 的 native Android 客户端 + 现有 Python/FastAPI/SQLite Host**：

- Android 端：Kotlin + Jetpack Compose + Media3 + Room + WorkManager + Readium；本地镜像选中的 Content Package，离线播放/阅读/搜索。
- Host 端：继续现有 Python 3.12 + FastAPI + SQLAlchemy + Alembic + SQLite；只做增量 API/表结构，不引入 Redis、Celery、Postgres、外部搜索服务。
- 同步：Content stream + State stream 两条流；manifest + cursor、tombstone、可续传下载、按字段 LWW、`sync_epoch`、`Idempotency-Key`。
- 搜索：Android 本地使用 **bundled SQLite 的 FTS5**，与 Host 一样做 CJK bigram 归一化 + `porter unicode61`，避免两套搜索规则漂移。
- 构建基线：Kotlin 2.4.21、AGP 9.5.1、Gradle 9.7.0、JDK 21、compileSdk/targetSdk 37、minSdk 26；Readium 3.4.0 是这组版本的主要驱动。

### 0.1 决策表

| 层 | 选择 | 关键理由 |
|---|---|---|
| Android 语言/UI | Kotlin 2.4.21 + Jetpack Compose + Material 3 | native 体验；Compose 适合列表/播放器/阅读器壳 |
| 构建 | AGP 9.5.1 + Gradle 9.7.0 + JDK 21 + version catalog | Readium 3.4 要求 compileSdk 37/Gradle 9.7；AGP 9 支持 API 37 |
| 模块 | `:app`、`:core`、`:playback`、`:reader` | 4 个 Gradle module 足够；spec 的 feature 拆分为包边界，避免构建过度复杂 |
| DI | 手工 `AppContainer` + ViewModel factory | V1 规模不需要 Hilt/Koin；减少 KSP/构建时间 |
| 导航 | Navigation 3 1.2.1 | stable、Compose-first；Navigation 2 已进入 maintenance mode |
| 网络 | Retrofit 3.0.0 + OkHttp 5.5.1 + Kotlinx Serialization 1.13.0 | 成熟、可拦截器加 bearer、与 Coil/Media3 共用 OkHttp |
| 本地 DB | Room 2.8.5 + `androidx.sqlite:sqlite-bundled` 2.7.1 | Room 2.8 稳定；bundled SQLite 提供 FTS5 |
| 本地搜索 | FTS5 + `porter unicode61` + CJK bigram；bm25 | 与 Host 搜索规则一致，支持英文词干和中文两字词 |
| 播放 | Media3 1.11.1（ExoPlayer + MediaSessionService + OkHttp datasource） | 后台/锁屏/媒体通知/倍速/音频焦点是 P0 |
| 下载/同步 | WorkManager 2.12.0 + OkHttp Range/If-Range | 约束下载、前台通知、断点续传、校验 sha256 |
| EPUB | Readium Kotlin 3.4.0（classic EPUB navigator） | 重排文本、图片、脚注、书内搜索；避开 alpha Compose navigator |
| 认证 | Host 密码换长期设备 token；Bearer + SHA-256 hash 存储；release HTTPS-only | Web Cookie 保留；Android 用可撤销设备 token；LAN 调试走独立 flavor |
| Host 同步 | SQLite 序列表 + `content_seq`/`state_seq` + 字段时钟 | 单用户、千条级；不需要外部队列/搜索 |
| Host 文件 | Starlette `FileResponse` + 自定义 ETag/sha256 | Starlette 1.10 已支持 Range/If-Range；无需新增依赖 |
| 测试 | Host HTTP seam + Android App seam | 已与用户确认；共享 contract fixture 防漂移 |

## 1. 约束与决策驱动

| 约束 | 来源 | 对选型的影响 |
|---|---|---|
| 手机是主要听设备 | V1 spec / 用户确认 | 后台播放、媒体通知、离线音频是 P0；不能只做移动 Web |
| V1 必须有离线播放/阅读/搜索 | FR-72、NFR-11 | 必须本地存储 + 本地索引；纯流式不够 |
| app-managed sync | FR-73、ADR-0009 | manifest/cursor、tombstone、可续传下载、LWW、设备 token |
| 单用户、千条级 Library | 需求 §2.3、NFR-05 | 不需要多租户/分布式；SQLite/Room 足够 |
| Mac Host 本地优先 | NFR-01、ADR-0001/0006 | Host 继续 Python/SQLite；不引入云服务 |
| 小米/Android 后台限制 | 真机 Q10 记录 | 必须用前台服务 + 媒体通知；需要电池优化引导 |
| 本地搜索与 Host 一致 | FR-51、搜索评估 | 共享 CJK bigram/英文 stem 规则；FTS5 优先于 FTS4 |
| 依赖许可 | NFR-10 | 只用 MIT/BSD/Apache；不引入 Readium LCP/GPL/AGPL |
| 个人分发 | V1 spec | 侧载 APK；不做 Play Store 合规 |

## 2. 总体架构

```text
Android App
├─ Compose UI（Library / Player / Reader / Search / Add / Settings）
├─ ViewModel + StateFlow
├─ Repository（只暴露领域模型）
├─ SyncEngine ── WorkManager ── Retrofit/OkHttp ── HTTPS ──┐
├─ Room + bundled SQLite FTS5                             │
├─ Media3 MediaSessionService（ExoPlayer）                 │
└─ Readium EPUB navigator                                 │
                                                          ▼
Host（Mac）
├─ FastAPI JSON API + Host Console/Web Shell
├─ 设备 token / sync manifest/state / 文件下载 / tombstone
├─ SQLAlchemy + SQLite（WAL）
└─ Content Package 文件库（source/audio/transcript/book/ai/cover）
```

- **事实源**：Host 的 Content Package；Android Room 是选中 Item 的镜像，本地索引可重建。
- **两条同步流**：Content stream 负责元数据/Tag/文件/tombstone；State stream 负责播放/阅读位置和 Consumption State。
- **无额外服务**：Host 不引入 Redis/消息队列/外部搜索；Android 不引入 FCM/WebSocket/云端。

## 3. Android 技术选型

### 3.1 构建、语言与 SDK

**选择**

- Kotlin **2.4.21**（当前稳定版；Readium 3.4.0 以 Kotlin 2.4.20 构建）。
- AGP **9.5.1**，Gradle **9.7.0**，JDK **21**（JVM target 17）。
- `compileSdk = 37`，`targetSdk = 37`，`minSdk = 26`，Build Tools 36.0.0。
- Kotlin DSL + `libs.versions.toml`；所有版本固定，不用动态版本。
- AGP 9 默认启用 built-in Kotlin：不应用 `org.jetbrains.kotlin.android`；通过顶层 buildscript 固定 KGP 2.4.21 和 KSP 2.3.12。
- Compose Compiler Gradle plugin 2.4.21；Room 使用 KSP；其余无需注解处理器。
- Release 启用 R8/minify + resource shrinking；Debug 不混淆。
- 构建变体：正式 `release` 只允许 HTTPS；独立 `lan` flavor 允许受信任局域网 cleartext 并持续警告；`debug` 可对 `10.0.2.2`/localhost 开 cleartext。`lan` 不随正式包发布。

**理由**

- Readium 3.4.0 的兼容矩阵列出 Android compileSdk 37、Gradle 9.7.0、Kotlin 2.4.20（submodule 集成时强制；Maven Central 集成也按此基线验证）；AGP 9.5 支持 API 37，且 min Gradle 9.6.0。
- Compose 1.12.x 也要求 compileSdk 37 / AGP 9；三者只能一起升级。
- JDK 21 是 Robolectric 4.17 跑 SDK 37 测试所需；AGP 9.5 最低 JDK 17，21 兼容。

**风险与 gate**

- AGP 9 built-in Kotlin + KSP + Compose compiler + Readium 的组合必须先做 **toolchain smoke**：空 Compose 工程 + Readium/Media3/Room 依赖，能 `assembleDebug` 并在 Xiaomi 13 启动。若 built-in Kotlin 与 KSP/Readium 冲突，优先调整 KGP/KSP 版本或临时 opt-out；不降级到 AGP 8（会失去 compileSdk 37 支持）。

### 3.2 模块、DI 与导航

**Gradle module**

- `:app`：Application、MainActivity、导航、`AppContainer`、Settings、所有 feature 页面。
- `:core`：model、network、database、sync、search、repository；内部用 package 边界拆 `model/network/db/sync/search`。
- `:playback`：Media3 service、`MediaController` 封装、播放状态模型。
- `:reader`：Readium 集成、EPUB Fragment 壳、locator 映射。

Spec 中的 `feature:*` 在 V1 作为 `:app` 内的 package 边界，不单独建 Gradle module；等构建时间真正成为问题时再拆。

**DI**

- 手工 `AppContainer`：懒加载 `OkHttpClient`、`Retrofit`、`TroveApi`、`AppDatabase`、`TokenStore`、`SyncEngine`、`DownloadScheduler`、`PlayerController`、`ReaderFactory`。
- ViewModel 用 `viewModelFactory { initializer { ... } }` 注入依赖；测试用 `FakeAppContainer`。
- 不引入 Hilt/Koin：V1 只有约 6 个页面，手动注入更轻；也避免额外 KSP/构建时间。

**UI / 导航**

- Compose BOM **2026.09.00**（Compose 1.12.1、Material3 1.4.0）、Activity Compose **1.13.0**、Lifecycle **2.11.0**、Core KTX **1.18.0**、Core Splashscreen **1.2.0**。
- Navigation **3 1.2.1**（`navigation3-runtime`、`navigation3-ui`、`lifecycle-viewmodel-navigation3`）：stable、Compose-first；Navigation 2 已进入 maintenance mode，新项目不选。
- 底部导航：Library / Search / Add；Continue/Library 分组；Item 详情进入 Player 或 Reader。
- 不使用 Paging 3：1,000 Item 级用 Room `Flow` + `LazyColumn` 足够；需要时再引入。
- 使用 Coil 3.6.3（`coil-compose` + `coil-network-okhttp`）加载封面；在线封面走带 bearer 的 OkHttpClient，已下载封面走本地文件。
- Material 3 自定义主题；edge-to-edge；predictive back；中文 UI。

### 3.3 网络、序列化与认证

**选择**

- Retrofit **3.0.0** + OkHttp **5.5.1** + Kotlinx Serialization **1.13.0** + `converter-kotlinx-serialization`。
- OkHttp `Authorization: Bearer <token>` interceptor；仅登录/健康检查不带 token。
- DTO 与领域模型分离；`ApiError` 解析 Host 的 `{code,message,details?}`。
- 超时：连接 10s、API 读 30s、下载读 60s；GET/5xx 允许有限退避重试，写请求靠 `Idempotency-Key` 去重。
- 不做 HTTP cache；Room 是唯一本地缓存。

**设备 token**

- 登录：`POST /api/auth/device-token`，body 为 Host 密码 + 设备名；Host 返回 `device_id` + token（只显示一次）。
- Token 存 Android Keystore AES-GCM 加密后的密文，密文/IV 放 DataStore **1.3.0**；不使用已弃用的 `EncryptedSharedPreferences`。
- Host 只存 token 的 SHA-256 hash；token 校验走 `Authorization: Bearer`，失败返回 401/`auth.device_revoked`。
- Android 收到 401/`auth.device_revoked` 清除 token、停止同步并回到登录；本地已下载内容保留。
- 密码修改/session epoch 变化/显式撤销使 token 失效；Host 提供设备列表/撤销 API + `trove device` CLI。
- Token 不放在 URL、日志、崩溃报告或 Android backup；`allowBackup=false`。

**Host URL 与 TLS**

- 用户手动输入 Host base URL；正式 release 必须是 HTTPS，去掉尾部 `/`；不要求路径前缀。`lan` flavor 允许受信任局域网 HTTP，并持续显示警告。
- Release 默认 `usesCleartextTraffic=false`；`debug` 可对 `10.0.2.2`/localhost 开 cleartext；独立 `lan` flavor 可对受信任局域网开 cleartext 并持续警告。正式 release 不提供运行时明文开关。
- Caddy 内部 CA：network security config 信任 system + user CA；Tailscale 使用公开证书，作为推荐路径。
- 不做证书 pinning：Host 证书会随 Tailscale/Caddy 变化，pin 会制造维护问题；用标准 TLS + 用户 CA 信任。
- Host URL 可配置，未来改云端 Host 只换 base URL，不改客户端模型。

### 3.4 本地数据库与搜索

**选择**

- Room **2.8.5** + KSP **2.3.12** + `androidx.sqlite:sqlite-bundled` **2.7.1**，使用 `BundledSQLiteDriver`。
- Room 管理 Item/Artifact/TranscriptSegment/BookChapter/BookParagraph/Tag/SyncCursor/PendingMutation 等普通表；FTS5 虚表由 migration + `SearchIndex` adapter 用 raw SQL 管理，不依赖 Room 的 FTS 注解。
- 本地搜索使用 **SQLite FTS5**：`norm_text` 索引列，`text`/`item_id`/`doc_kind`/`ref` 作为 UNINDEXED 列；`tokenize='porter unicode61'`。
- 文档/查询先做与 Host 完全相同的 CJK bigram 归一化（`人工智能 -> 人工 工智 智能`）；英文交给 porter。
- 查询用 FTS5 `MATCH` 取候选，`bm25()` 做基础排序；再在 Kotlin 按 `doc_kind` 权重重排（title/summary/tag 高于 transcript/book），结果按 Item 聚合，最多 3 条 evidence。
- Evidence snippet 在 Kotlin 中从原始 `text` 提取（找到最早命中的 query token/bigram，取 80–120 字窗口）；不依赖 FTS5 snippet 对 bigram 的展示。
- 单字查询退化为 `LIKE`；查询长度上限 200；不直接拼 FTS5 语法。
- 启动时做 FTS5 自检（临时虚表 + `sqlite_compileoption_used('ENABLE_FTS5')`）；失败时禁用离线搜索并显示明确错误，但播放/阅读仍可用。
- 本地索引从已下载的 `transcript.json`、`book.json` 和 Item 元数据构建；可重建；删除/更新/升级时增量或重建。

**为什么不用 Room FTS4 / 平台 SQLite**

- 平台 SQLite 在 minSdk 26 不保证 FTS5；Room 2.8 只提供 FTS4 注解。
- FTS4 没有 Host 同款 porter/unicode61 组合，英文词干和中文 bigram 的规则会分叉；需要额外 stemmer/排序实现。
- bundled SQLite 提供 FTS5，换来少量 APK 体积和一层 raw SQL，但搜索行为与 Host 一致，长期维护成本更低。

**文件与备份**

- 下载文件放 App 私有 `filesDir`；按 `itemId/kind` 组织；`.part` 临时文件完成后校验 sha256 再原子 rename。
- `allowBackup=false`；本地下载不参与 Android 云备份；重装后从 Host 重新同步。
- 不申请外部存储权限；不扫描用户文件系统。

### 3.5 播放

**选择**

- Media3 **1.11.1**：`media3-exoplayer`、`media3-session`、`media3-datasource-okhttp`；不使用 `media3-ui`，播放器 UI 用 Compose 自绘。
- `MediaSessionService` + `ExoPlayer`；`MediaSession` 提供锁屏/通知/蓝牙/车机控制；媒体通知用 Media3 默认 provider 定制。
- `DefaultDataSource.Factory` 组合 `FileDataSource` 与 `OkHttpDataSource`；`OkHttpDataSource` 通过 `RequestTransformer` 加 `Authorization: Bearer`，流式播放不需要签名 URL。
- `setAudioAttributes(..., handleAudioFocus = true)`；处理音频焦点、耳机拔出、来电暂停/恢复。
- `Player.Listener` + 5 秒定时器保存位置；暂停/停止/切换 Item 立即保存；先写 Room，再节流入 PendingMutation。
- 播放结束自动标记 Consumption State 完成；手动完成/未完成写本地并排队同步。
- 一次只播放一个 Item；不做队列/Up Next/睡眠定时。

**平台**

- Manifest：`FOREGROUND_SERVICE`、`FOREGROUND_SERVICE_MEDIA_PLAYBACK`、`POST_NOTIFICATIONS`、`WAKE_LOCK`、`INTERNET`、`ACCESS_NETWORK_STATE`。
- `MediaSessionService` 声明 `foregroundServiceType="mediaPlayback"`；按 Media3 文档导出 service + intent filter。
- Android 13+ 首次播放/下载时请求通知权限；拒绝通知不阻塞播放，但提示锁屏控制可能受限。
- OEM（小米）后台限制：用前台服务 + 媒体通知；设置页提供电池优化设置入口（用系统设置页，不强制 `REQUEST_IGNORE_BATTERY_OPTIMIZATIONS`）。

### 3.6 下载与同步

**下载**

- WorkManager **2.12.0** `CoroutineWorker`；`setForeground` + `ForegroundInfo`，Android 14+ 使用 `dataSync` 类型。
- 全局唯一 work chain（`beginUniqueWork` + append）串行下载，默认同时 1 个；用户可暂停/取消。
- 约束：默认 `UNMETERED`；可选“仅充电”；用户可临时允许移动网络；遵守用户存储配额（默认 5 GB，可配置）。
- 请求：`GET /api/items/{id}/files/{kind}`；`Range` + `If-Range: <ETag>` 续传；ETag 变化丢弃 `.part` 全量重下；完成校验 sha256。
- 下载状态（排队/下载中/暂停/失败/完成）写 Room；WorkManager progress 更新 UI；失败可重试。
- 选中下载的 Item 默认下载全部可用 artifact：audio、transcript、book、book_json、ai、cover；`ai.json` 通常只有几 KB，保留完整镜像和离线 provenance。
- 下载/播放只针对已有对应 Artifact 的 Item；Processing State 可以是 failed（音频/书已保留），但没有 artifact 时不显示播放/下载。
- Android 15/16 对 `dataSync` 前台服务有时间限制；单 Item 音频通常 30MB 级，不受影响；若遇到限制，WorkManager 会重试，必要时后续改用 user-initiated data transfer job。

**同步**

- `SyncEngine` 顺序：**先推 PendingMutation，再拉 Content manifest，最后拉 State**。若有未能推送的本地进度/Tag，跳过 State 拉取，避免覆盖本地较新的编辑。
- Content stream：`GET /api/sync/manifest?cursor=&limit=`；按页应用 Item/Tag/文件/tombstone；每页事务提交后推进 cursor；`has_more` 继续。
- State stream：`GET /api/sync/state?cursor=&limit=`；应用播放/阅读位置/Consumption State。
- `sync_epoch` 变化或 `sync.cursor_invalid`：清空两条 cursor，做全量重同步；保留 PendingMutation 和已下载文件，按 sha256 复用。
- 文件清单变化：删除本地不再存在的 artifact；sha256 变化则删除旧文件并按下载选择重新入队。
- 触发：App 启动/回前台、手动下拉、添加成功、网络恢复、WorkManager 周期任务（默认 15 分钟，可关闭）。不使用 FCM/WebSocket。
- 同步状态写 Room/DataStore：Idle/Syncing/Offline/Error、上次成功时间、错误码；UI 顶部状态条 + 可重试。
- 同步与下载通过 `Mutex`/唯一 work 避免并发写 Room 冲突；同步/下载不阻塞播放/阅读。

**冲突**

- 写请求带 `client_updated_at`（设备 UTC ms）+ `Idempotency-Key`；Host 按字段比较，大者胜，相等按 `device_id` 决胜。
- Host 返回 `applied: true/false` + canonical Item/state；客户端用 canonical 覆盖本地乐观值；`applied:false` 显示“已在其他设备更新”的非阻塞提示。
- Progress 字段独立：`audio_progress`、`book_progress`、`consumption_state`；Tag 作为整组字段；一次 book 进度不覆盖更新的 audio 进度。
- Host 时间超过当前 5 分钟视为无效，使用服务端时间并返回 `sync.clock_skew`；客户端不因时钟偏差卡死。
- `Idempotency-Key` 在 Host 保留至少 24h；重复请求返回第一次结果。

### 3.7 阅读

**选择**

- Readium Kotlin **3.4.0**：`readium-shared`、`readium-streamer`、`readium-navigator`；不引入 `readium-lcp`（V1 只支持 DRM-free）。
- 使用 **classic EPUB navigator**（`EpubNavigatorFragment`）而不是 alpha 的 Compose navigator；通过 `FragmentContainerView`/`AndroidView` 嵌入 Compose 页面。
- `book.epub` 由 Readium 渲染；`book.json` 用于搜索文本、章节索引和与 Web 的 locator 映射。
- Readium 需启用 core library desugaring；编译/运行时按 3.4.0 兼容矩阵。
- EPUB 内容安全：把 EPUB 内容视为不可信；用 WebViewClient 阻断非本地请求和外部导航，并向 Readium WebView 注入禁止内容脚本/远程资源的 CSP；Readium 自身的本地注入脚本保留。用恶意 EPUB fixture 验证不会执行远程脚本或发出网络请求；若无法在不破坏 Readium 的前提下满足，则 V1 降级为 `book.json` 净化 HTML 阅读器并记录为已知限制。
- 书内搜索用 Readium 的搜索 API；结果 locator 映射到 `ref`（chapter/paragraph），打开并高亮。
- 阅读偏好用 Readium `EpubPreferences`：字号、行高、浅色/深色/护眼主题；不做分页模式切换。
- 阅读位置写 `book_locator` schema 2：
  - `schema: 2`
  - `chapter_index` / `paragraph_index` / `scroll_ratio`（Web legacy）
  - `epub_href` / `epub_progression` / `epub_total_progression`（Readium）
- chapter_index 使用 Host `book.json` 的 spine 顺序；Android 打开时优先用 EPUB locator，缺失时回退到 chapter/paragraph/scroll。映射失败时打开章节起始并提示。
- Transcript 用 Compose `LazyColumn` 显示 `seq/start_ms/end_ms/text`；支持文内搜索/高亮；不做点击跳音频/同步滚动。

### 3.8 入库与处理状态

- `ACTION_SEND` `text/plain` 分享 intent：提取第一个 URL，预填 Add；也支持手动粘贴。
- Add 调用 Host `POST /api/items`（视频 URL/播客单集）或 `POST /api/feeds/preview`（播客 feed 预览）；所有 URL 校验/平台白名单/SSRF/上传限制由 Host 执行。
- 重复添加返回已有 Item；Android 直接打开详情。
- Add 页持续显示 DeepSeek 数据流提示；不做 per-item LLM 开关。
- 处理中前台轮询 Item/Run 状态（有上限/退避）；后台靠周期同步；不引入 WebSocket。
- 失败原因映射 Host 稳定错误码到中文；支持从手机重试失败 Run。
- V1 不做手机上传本地音频/EPUB；本地文件入库继续走 Host Console 浏览器上传。

### 3.9 Android 测试

- JUnit 4 + Robolectric **4.17** + Compose UI Test + AndroidX Test；Turbine **1.2.1** 测 Flow；MockWebServer **5.5.1**（`mockwebserver3`）测 HTTP/Range。
- 不使用 MockK/Hilt：用 fake `TroveApi`、fake repository、`TestAppContainer`；真实 Room + 临时文件 + Robolectric。
- JVM/Robolectric 覆盖：DTO 契约、cursor/分页、tombstone、LWW、PendingMutation、下载续传状态机、CJK 归一化/locator 映射、UI 主流程。
- Instrumented 覆盖：Media3 `MediaSessionService`/通知、WorkManager 前台下载、Readium 打开 golden EPUB；不在默认 CI 跑。
- 共享 contract fixture：Host 测试生成/校验 manifest/state/error JSON；Android DTO/App 测试消费同一组 fixture。
- 真实 Xiaomi 13 手动验收：1 小时后台/锁屏播放、媒体通知、蓝牙、飞行模式离线、断点续传、EPUB、离线搜索、Tag/进度同步、删除/重装、token 撤销。

## 4. Host 技术选型

### 4.1 运行时与依赖

- 继续 Python **3.12.14** + FastAPI **0.162.2** + Pydantic **2.14.3** + SQLAlchemy **2.1.8** + Alembic **1.20.1** + Uvicorn **0.54.0**。
- SQLite **3.54.1**（WAL、FTS5、`RETURNING` 可用）；Starlette **1.10.0**。
- **不新增 Python 依赖**：token 生成/哈希、UUID、base64 用标准库；文件响应复用 Starlette `FileResponse`；数据库用现有 SQLAlchemy/Alembic。
- 不引入 Redis/Celery/Postgres/Meilisearch；单用户千条级不需要。

### 4.2 认证与设备

- 新增 `device_tokens`：`device_id`（UUID）、`name`、`token_hash`（SHA-256，唯一索引）、`created_at`、`last_used_at`、`revoked_at`、`session_epoch`。
- `POST /api/auth/device-token`：密码 + 设备名；沿用现有 IP 登录限速；返回一次性 token + `device_id`。
- token 随机 `secrets.token_urlsafe(32)`；Host 只存 hash；校验 `Authorization: Bearer` 时 hash 后查表。
- 中间件同时接受 Cookie 和 Bearer；Bearer 请求跳过 CSRF；Cookie 请求保留 Origin/Sec-Fetch-Site 校验。
- 校验 `session_epoch == config.session_epoch`；密码修改/撤销立即失效。
- `last_used_at` 最多每 5 分钟更新一次，避免每请求写 SQLite。
- `GET /api/devices` / `DELETE /api/devices/{device_id}`；`trove device list/revoke` CLI 可管理。

### 4.3 同步序列与游标

- 新增 `sync_sequence` 单行表：`value`（整数）、`epoch`（随机 UUID）。`next_seq` 用 `UPDATE ... SET value = value + 1 RETURNING value`，在写事务内执行；SQLite 单写者保证并发安全。
- `items` 增加 `version`、`deleted_at`、`content_seq`、`state_seq`；`content_seq`/`state_seq` 建索引。
- Content 变化（元数据/Tag/Processing State/Artifact/删除/复活）递增 `version` + `content_seq`；State 变化（播放/阅读位置/Consumption State）只递增 `state_seq`，不碰 `version`/`content_seq`。
- cursor 是 opaque 的 seq 字符串；manifest/state 响应同时返回 `epoch`。客户端 epoch 变化或 cursor 大于 Host 当前最大 seq 时全量重同步。
- `GET /api/sync/manifest` 按 `content_seq > cursor ORDER BY content_seq LIMIT`；返回 compact Item、Tag、`files[]`、tombstone、`next_cursor`、`has_more`、`epoch`。
- `GET /api/sync/state` 按 `state_seq > cursor ORDER BY state_seq LIMIT`；返回 Item ID、位置、Consumption State、`last_consumed_at`、`next_cursor`、`has_more`、`epoch`。
- compact Item 不返回 Run steps/log tail/搜索 evidence；完整详情仍走 `GET /api/items/{id}`。
- 首次同步只同步元数据；文件下载由客户端按 Item/Tag/大小选择。

### 4.4 Tombstone、LWW 与幂等

- `DELETE /api/items/{id}` 改为 soft delete：设置 `deleted_at`、递增 version/content_seq、删除 Content Package 派生文件、删除 FTS 行、保留 Item 行；普通 Library/Search/Continue 过滤 `deleted_at IS NOT NULL`。
- 重新添加同一 `source_key` 的 tombstone Item：复活同一 ID，清空 `deleted_at`、递增 version/content_seq、创建新 Processing Run；客户端先收到 tombstone 再收到复活 Item。
- 新增 `sync_field_clocks`：`(item_id, field)` 主键，`field` 为 `audio_progress`/`book_progress`/`consumption_state`/`tags`，记录 `client_updated_at` + `device_id`。
- `PUT /api/items/{id}/progress` 扩展现有接口：body 增加 `client_updated_at`，header `Idempotency-Key`；按字段比较、只更新获胜字段；返回 `applied` + canonical Item/state。
- `PUT /api/items/{id}/tags`：整组替换，Host 归一化 Tag；按 `tags` 字段时钟 LWW；返回 canonical Tag。
- `sync_mutations`：`(device_id, mutation_id)` 唯一，保存响应 JSON + 时间；重复请求返回第一次结果；写入时惰性清理 24h 前记录。
- Web Host Console 的写操作也走同一字段时钟，`device_id = host-web`，使用服务端时间；不能绕过 LWW。
- `sync_epoch` 在 Host 从备份恢复后通过 `trove sync reset-epoch` 更换，强制客户端全量同步。

### 4.5 文件服务

- 新增 `GET /api/items/{item_id}/files/{kind}`；`kind` 限定 `audio`/`transcript`/`book`/`book_json`/`ai`/`cover`。
- 只查数据库 Artifact + Content Package 已记录路径；不接受任意路径；路径穿越防护沿用现有媒体服务。
- 响应带 `ETag: "<sha256>"`、`Accept-Ranges: bytes`、`Cache-Control: private`、`X-Content-Type-Options: nosniff`；使用 Starlette 1.10 `FileResponse` 的 Range/If-Range 支持。
- `Transcript`/`book_json`/`ai` 返回 `application/json`；`book` 返回 `application/epub+zip`；`cover` 用存储 MIME。
- 现有 `/api/items/{id}/audio`、`/transcript`、`/book/chapters/{n}` 保留给 Web；Android 统一走 `/files/{kind}`。
- 文件下载 URL 是相对 API 路径；客户端加 Bearer，不把 token 放 URL。

### 4.6 Host 数据模型与迁移

- 新增表：`device_tokens`、`sync_sequence`、`sync_field_clocks`、`sync_mutations`。
- `items` 增加 `version`、`deleted_at`、`content_seq`、`state_seq`；`version` 默认 1；迁移回填现有 Item 的 seq。
- 保留 `source_key` 唯一约束；tombstone 通过复活同 ID 处理，不需要 partial unique index。
- Content Package 布局不变；`source.json` 不新增同步字段；同步状态只在 SQLite 和 Android 本地库。
- 新增一个 Alembic migration（在 0003 之后）；SQLite batch mode；回填顺序：创建 `sync_sequence` → 分配 `content_seq`/`state_seq` → 建索引 → 新增表。
- `LibraryService.delete` 改 soft delete；`list_items`/search/continue/export 过滤 tombstone；`index rebuild` 跳过 tombstone。
- `ItemSchema` 增加 `version`；`ArtifactSchema` 已有 sha256/size/mime/url；文件版本使用 Item version。

### 4.7 Host 实现落点

按现有 code map：

- `web/api/devices.py`：设备 token/列表/撤销。
- `web/api/sync.py`：manifest/state。
- `web/api/files.py`：Content Package 文件下载。
- `services/devices.py`：token 生成/校验/撤销。
- `services/sync.py`：序列、cursor、manifest/state、LWW、幂等、tombstone。
- `domain/sync.py`：cursor 编码、字段枚举、LWW 比较、时钟偏移规则（纯函数）。
- `web/security.py`：Bearer + Cookie 双认证、Bearer 跳过 CSRF。
- `services/library.py`：soft delete、revive、version/content_seq 递增、过滤 tombstone。
- `web/schemas.py`：manifest/state/device/progress 扩展。
- `cli.py`：`trove device list/revoke`、`trove sync reset-epoch`。

### 4.8 Host 测试

- 扩展现有 `Host` fixture：`device_token()`、`bearer_client`、`sync_client`；真实 SQLite/Alembic/文件系统/FTS5；外部适配器继续 fake。
- 新增 Host seam 测试：
  - 设备 token 换取/撤销/密码修改/错误 token。
  - manifest 首同步/分页/增量/epoch 变化。
  - state sync 与「进度写不 bump content_seq」。
  - tombstone/soft delete/复活。
  - 文件 Range/ETag/If-Range/sha256/路径穿越。
  - LWW 旧写被忽略、新写生效、相同 Idempotency-Key 重放。
  - OpenAPI 新路径 + Bearer security scheme；旧 MVP 路由不回归。
- 现有 `tests/test_api_contract.py`、`test_auth.py`、`test_security.py`、`test_library.py`、`test_processing.py` 继续作为回归基线。

## 5. 关键 API 契约摘要

| 方法 | 路径 | 关键点 |
|---|---|---|
| POST | `/api/auth/device-token` | 密码 + 设备名 → 一次性 token/device_id；限速 |
| GET/DELETE | `/api/devices`、`/api/devices/{id}` | 认证后列表/撤销；Bearer 或 Cookie |
| GET | `/api/sync/manifest` | compact Item + Tag + files + tombstone + cursor/epoch |
| GET | `/api/sync/state` | 位置/Consumption State + cursor/epoch |
| PUT | `/api/items/{id}/progress` | `client_updated_at` + `Idempotency-Key`；applied + canonical |
| PUT | `/api/items/{id}/tags` | 整组 Tag + LWW；canonical Tag |
| GET | `/api/items/{id}/files/{kind}` | Range/ETag/If-Range/sha256；kind 白名单 |
| DELETE | `/api/items/{id}` | soft delete + tombstone |
| GET | `/api/health` | `api_version` + capabilities（`sync`/`device_tokens`/`file_download`） |

错误继续 `{code, message, details?}`；新增 `auth.device_revoked`、`auth.device_token_invalid`、`sync.cursor_invalid`、`sync.clock_skew`、`file.artifact_missing`。`applied:false` 是正常 LWW 结果，不作为 HTTP 错误；spec 中的 `sync.stale_write` 预留给显式 `If-Match` 前置条件，V1 不发送 `If-Match`。

## 6. 性能、容量与安全

- APK 目标 <35MB（bundled SQLite + Readium + Media3 会增加体积）；Release 用 R8/resource shrinking。
- 手机存储默认配额 5GB；100 小时音频约 2.8GB；只做选择性同步。
- 本地搜索目标：已下载 1,000 Item p95 <1 秒；FTS5 + doc_kind 重排。
- manifest 分页默认 100；1,000 Item 首同步应在数秒内完成（局域网/Tailscale）。
- 播放/下载不阻塞同步/搜索；同步/下载通过 Mutex/唯一 work 串行。
- 安全：HTTPS-only release、Keystore token、`allowBackup=false`、日志脱敏、EPUB 远程资源阻断、文件 endpoint 白名单、Bearer 不进 URL、设备撤销即时生效。
- 不使用证书 pinning；Caddy 内部 CA 通过用户 CA 信任；Tailscale 是推荐路径。
- 不做 analytics/crash reporting；诊断日志只保留状态/错误码/脱敏 URL。

## 7. 被否决方案

| 方案 | 否决原因 |
|---|---|
| PWA/移动 Web 作为主客户端 | Q10 未接受；后台/离线/大文件续传/本地索引不可靠；现有服务端渲染壳离线改造成本高 |
| React Native/Flutter | 后台播放/下载/Readium 仍要原生模块；多一层运行时，V1 收益不足 |
| Hilt/Koin | 6 个页面 + 4 个 module，手工 DI 足够；少一个 KSP/构建依赖 |
| Navigation Compose 2.x | 已 maintenance mode；Navigation 3 stable 且 Compose-first |
| Room 3 alpha + `@Fts5` | Room 3 尚未 stable；Room 2.8 + raw FTS5 足够 |
| Room FTS4 / 平台 SQLite | 无 porter/unicode61 组合；FTS5 不保证；搜索规则会分叉 |
| Ktor Client | Retrofit/OkHttp 与 Coil/Media3/测试生态更直接；Ktor 会多一个 HTTP engine |
| Android DownloadManager | 自定义 bearer、Range/If-Range、前台进度和 sha 校验控制不足 |
| EncryptedSharedPreferences | 已弃用；改用 Keystore AES-GCM + DataStore |
| Paging 3 | 1,000 Item 级 Room Flow + LazyColumn 足够 |
| Readium Compose navigator（alpha） | 不稳定；用 classic Fragment navigator |
| Readium LCP | V1 只支持 DRM-free；避免二进制 LCP 依赖 |
| FCM/WebSocket | 无云端；WorkManager/轮询足够 |
| OpenAPI 全量代码生成 | 生成客户端增加构建/版本耦合；手写 DTO + 共享 fixture 更可控 |
| 证书 pinning | Host 证书会变；标准 TLS + 用户 CA 更稳 |
| 正式 release 明文 HTTP | 安全面太大；LAN 需求走独立 `lan` flavor，不进入正式包 |

## 8. 风险与应对

| 风险 | 影响 | 应对 |
|---|---|---|
| AGP 9 built-in Kotlin + KSP + Compose + Readium 组合不兼容 | 无法构建 | 先做 toolchain smoke；固定 KGP 2.4.21/KSP 2.3.12；必要时调整版本，不降 AGP 8 |
| Readium 3.4 要求 compileSdk 37/Gradle 9.7 | 构建链被迫升级 | 直接以 Readium 矩阵为基线；CI 固定 JDK 21/SDK 37 |
| bundled SQLite 增加 APK 体积 | 安装包变大 | 目标 <35MB；R8/resource shrinking；按需配置 ABI splits（arm64-v8a 优先） |
| FTS5 raw SQL 与 Room 迁移 | 索引建表/升级出错 | 启动自检 + migration test + 本地索引可重建 |
| Media3 前台服务/OEM 限制 | 后台播放被杀 | 前台服务 + 媒体通知 + 电池优化引导；真机验收 |
| Android 15/16 dataSync 时限 | 大文件下载被停 | 单 Item 文件较小；失败重试；必要时 user-initiated data transfer job |
| Caddy 内部 CA 信任 | 手机连不上 | 文档安装 CA + network security config；Tailscale 推荐 |
| Readium locator 与 Web book_locator 映射 | 跨端续读偏移 | schema 2 + legacy fallback + spine index 测试 |
| Readium WebView 执行 EPUB 内容脚本/远程资源 | 恶意 EPUB 外连或执行 | WebViewClient 阻断 + CSP + 恶意 EPUB fixture；不满足则降级 `book.json` 净化阅读器 |
| LWW 时钟偏移 | 旧写覆盖新写 | Host 5 分钟 skew 规则 + 字段时钟 + applied/canonical |
| API 契约漂移 | 客户端解析失败 | OpenAPI + 共享 fixture + Host/Android 双侧契约测试 |
| 无 Play Store 分发 | 安装/升级靠侧载 | 个人分发；release APK + 版本号；不承诺商店合规 |

## 9. 建议实施顺序

1. **M0 — toolchain smoke + Host 基础**：空 Compose 工程编译 Readium/Media3/Room；Xiaomi 13 启动；Host 设备 token、manifest/state、文件下载、tombstone、LWW 的 seam 测试。
2. **M1 — 登录/Library/播放**：Host URL + 登录 + 设备 token；Library 首同步/增量；Media3 播放/下载/离线播放/媒体通知；1 小时真机后台播放 spike。
3. **M2 — 阅读/搜索/Add**：Readium Reader + locator；transcript/书内搜索；本地 FTS5；Add/分享/播客预览；Continue/Tag/进度同步。
4. **M3 — 收口**：冲突/重装/配额/错误态；删除/tombstone；真实设备验收；性能/安全/包体收口。

M0 的 toolchain smoke 是硬 gate：Readium 3.4 + compileSdk 37 + AGP 9 + KSP 组合不通过，就先解决构建链，不进入功能开发。

## 10. 组件、版本与许可证

> 版本按 2026-11-14 的稳定版；实现时用 version catalog 固定。Readium 3.4.0 的兼容矩阵是构建基线的来源。

| 组件 | 版本 | 用途 | 许可证 |
|---|---|---|---|
| Kotlin | 2.4.21 | 语言/编译器 | Apache-2.0 |
| AGP | 9.5.1 | Android 构建 | Apache-2.0 |
| Gradle | 9.7.0 | 构建 | Apache-2.0 |
| JDK | 21 | 构建/测试 | GPLv2+CE |
| Compose BOM | 2026.09.00 | Compose 1.12.1 / Material3 1.4.0 | Apache-2.0 |
| Activity Compose | 1.13.0 | Activity/Compose 集成 | Apache-2.0 |
| Lifecycle | 2.11.0 | ViewModel/生命周期 | Apache-2.0 |
| Navigation3 | 1.2.1 | Compose 导航 | Apache-2.0 |
| Media3 | 1.11.1 | 播放/MediaSession | Apache-2.0 |
| Room | 2.8.5 | 本地 DB | Apache-2.0 |
| androidx.sqlite bundled | 2.7.1 | bundled SQLite/FTS5 | Apache-2.0；SQLite public domain |
| WorkManager | 2.12.0 | 下载/同步任务 | Apache-2.0 |
| DataStore | 1.3.0 | 设置/token 密文 | Apache-2.0 |
| Retrofit | 3.0.0 | HTTP client | Apache-2.0 |
| OkHttp | 5.5.1 | HTTP/下载/Range | Apache-2.0 |
| Kotlinx Serialization | 1.13.0 | JSON | Apache-2.0 |
| Coil | 3.6.3 | 封面加载 | Apache-2.0 |
| Readium Kotlin | 3.4.0 | EPUB 渲染 | BSD-3-Clause |
| KSP | 2.3.12 | Room 代码生成 | Apache-2.0 |
| JUnit 4 | 4.13.2 | 测试 | EPL-1.0（test-only） |
| Robolectric | 4.17 | Android JVM 测试 | MIT |
| Turbine | 1.2.1 | Flow 测试 | Apache-2.0 |
| MockWebServer | 5.5.1 | HTTP 测试 | Apache-2.0 |

Host 现有 Python 依赖不变；新增代码只用标准库 + 现有 FastAPI/SQLAlchemy/Alembic/Starlette。

## 11. 与 spec 的偏差与已确认决策

1. **Gradle module 数（已确认）**：spec 列了 `core:*`/`feature:*` 模块名；本选型收敛为 4 个 Gradle module（`:app`、`:core`、`:playback`、`:reader`），其余作为 package 边界。若后续构建时间/协作成本上升，再按真实痛点拆。
2. **Release 明文 HTTP（已确认）**：release 收紧为 HTTPS-only；独立 `lan` flavor 允许受信任局域网 cleartext 并持续警告；debug 可对 localhost/模拟器开 cleartext。spec 的用户故事 12 和认证实现已同步此决策。
3. **导航库（已确认）**：spec 没指定；本选型选 Navigation 3 1.2.1（Navigation 2 已 maintenance mode）。若 Readium Fragment 互操作成本过高，可回退 Navigation2。
4. **本地搜索引擎（已确认）**：spec 只要求 CJK/关键词；本选型用 bundled SQLite FTS5，而不是 Room FTS4/平台 SQLite。
5. **Readium navigator（已确认）**：用 classic Fragment navigator，不用 alpha Compose navigator；阅读页会有一个 Fragment 容器，但其余 UI 仍是 Compose。
6. **AI artifact（已确认）**：选中下载的 Item 默认下载 `ai.json`，保持完整 Content Package 镜像；summary/Tag 仍从 manifest 直接读取，`ai.json` 用于离线 provenance/未来导出。
7. **构建版本（已确认，带 smoke gate）**：JDK 21 / Gradle 9.7 / compileSdk 37 由 Readium 3.4 驱动；比 spec 的“最新稳定 Android”更具体。M0 toolchain smoke 不通过时整体回退到 Readium 3.2/compileSdk 36 档，不混搭版本。

1/3/4/5/7 按当前选型执行；2 已同步到 spec；6 是客户端实现细节，不需要改 spec。
