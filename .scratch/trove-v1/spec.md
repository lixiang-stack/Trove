# Trove V1 — Native Android Consumption Client — Feature Spec

Status: ready-for-agent
Feature: trove-v1
Date: 2026-11-14
Scope: V1 native Android client（手机是主要听设备）+ Host 的设备认证、同步、文件下载与 tombstone 变更
Sources: [trove-requirements.md §5.8/§8.2](../../docs/ideas/trove-requirements.md)、[trove-tech-selection.md](../../docs/ideas/trove-tech-selection.md)、[ADR-0001](../../docs/adr/0001-python-monolith-sqlite-worker.md) 至 [ADR-0009](../../docs/adr/0009-native-android-client-app-managed-sync.md)、[MVP spec](../trove-mvp/spec.md)、[MVP acceptance](../trove-mvp/acceptance.md)
Tech selection: [tech-selection.md](tech-selection.md)

## Problem Statement

我的库在 Mac Host 上，桌面 Web Shell 已经能完成入库、管理、搜索和桌面消费；但手机浏览器无法稳定承担主要听设备：后台/锁屏播放不可靠，离线音频、离线阅读、离线搜索和可续传下载都缺失，Q10 已关闭为“未接受”。现在确认手机是主要听设备，我需要一个 native Android 客户端，而不是继续强化移动 Web。

当前 Host 的 JSON API 也缺少 V1 客户端所需的契约：没有长期设备 token，没有 manifest/cursor 和 tombstone，没有通用 Content Package 文件下载，删除仍是硬删除，播放/阅读进度没有多设备冲突规则。Android 客户端本身也不存在。

## Solution

做一个 native Android 客户端，连接 Mac 上的 Host over HTTPS，作为手机上的主要消费端：登录一次后保存设备 token；浏览 Library；分享或粘贴链接入库；后台/锁屏播放音频；把选中的 Item 下载到手机，离线播放、阅读 transcript/EPUB、搜索；在线时把播放位置、阅读位置、Consumption State 和 Tag 写回 Host；离线改动排队，重连后按字段 last-write-wins 合并。Host 仍然是处理和存储中心，Content Package 仍然是事实源；Android 本地库是选中的 Content Package 的镜像和派生索引。

Host 增加设备认证、内容 manifest + 状态同步、tombstone、通用 Content Package 文件下载和 LWW 写接口。Consumer Web Shell 保留给桌面使用；Q10 手机 Web 不再是 V1 验收路径。

## User Stories

### 安装、认证与连接

1. 作为 Host 所有者，我想在 Android 上输入或粘贴 Host 地址，以便连接到我的 Mac 库。
2. 作为 Host 所有者，我想用 Host 密码登录一次并换一个长期设备 token，以便不用每次打开都登录。
3. 作为 Host 所有者，我想让 token 存在 Android Keystore 保护的区域，以便 token 不因普通文件读取而泄露。
4. 作为 Host 所有者，我想在密码错误、token 过期、Host 离线或 TLS 证书不受信时看到明确原因，以便知道该修什么。
5. 作为 Host 所有者，我想在 Host Console 或 CLI 查看已登录设备并撤销它，以便丢失手机后能断开访问。
6. 作为 Host 所有者，我想让密码修改或 session 失效同时撤销所有设备 token，以便快速收口。
7. 作为 Host 所有者，我想只通过 Tailscale/Caddy 的 HTTPS 连接，以便局域网里的其他人不能明文嗅探。
8. 作为 Host 所有者，我想看到 Host 的健康状态、API 版本和同步能力，以便判断客户端是否兼容。
9. 作为 Host 所有者，我想在 App 重启、网络切换或 Wi-Fi/移动网络变化后自动重连，以便播放和同步不中断。
10. 作为 Host 所有者，我想登出并清除 token，或单独选择清除本地下载，以便换机或重置。
11. 作为 Host 所有者，我想在 Host 升级后看到“需要升级 App”或“Host 需要升级”的提示，以便不静默失败。
12. 作为 Host 所有者，我想让正式 App 只通过 HTTPS 连接，并保留一个独立的局域网调试包，以便不在正式包里暴露密码和 token。

### Library 与浏览

13. 作为内容收藏者，我想在 Library 看到全部 Item，并按最近添加或最近消费排序，以便浏览。
14. 作为内容收藏者，我想看到每个 Item 的 Processing State 和失败原因，以便知道它是否可消费。
15. 作为内容收藏者，我想按类型、Consumption State、Tag 和 Source 过滤，以便缩小范围。
16. 作为内容收藏者，我想看到每个 Item 是否已下载、文件大小、在线/离线可用状态，以便管理手机空间。
17. 作为内容收藏者，我想在 Item 详情看到标题、作者、Source URL、平台、发布日期、抓取时间、摘要、Tag 和时长，以便追溯来源。
18. 作为内容收藏者，我想打开原始 Source URL，以便回到原平台查看。
19. 作为内容收藏者，我想用 Inbox 过滤“处理中/失败”的 Item，以便知道哪些还没准备好。
20. 作为内容收藏者，我想下拉刷新并看到上次同步时间，以便确认库是最新的。
21. 作为手机用户，我想在离线时清楚看到“只显示已下载 Item”和离线状态，以便不误以为库空了。
22. 作为听众，我想在 Continue 看到最近在听/在读的 Item 并一键继续，以便快速回到未完成内容。
23. 作为内容收藏者，我想看到手机存储占用、下载队列和可清理空间，以便避免手机被占满。
24. 作为内容收藏者，我想移除某个 Item 的本地下载但保留 Host Item，以便只清理手机空间。
25. 作为内容收藏者，我想删除 Item 并确认，以便 Host 和手机都按 tombstone 清理。
26. 作为内容收藏者，我想按 Item、Tag 或大小选择要下载的内容，以便不整库同步。
27. 作为内容收藏者，我想在空库、加载中、无网络和同步失败时看到明确状态，以便知道下一步做什么。

### 入库

28. 作为手机用户，我想从其他 App 分享一个 URL 到 Trove，以便不复制粘贴也能入库。
29. 作为内容收藏者，我想粘贴一条 B 站或 YouTube 单视频 URL 并入库，以便把它变成可听、可检索的内容。
30. 作为内容收藏者，我想在粘贴播放列表或多 P 链接时被明确拒绝，以便不会只处理其中一条。
31. 作为内容收藏者，我想在重复添加同一 URL 时看到“已存在”并打开原 Item，以便不重复下载和处理。
32. 作为播客听众，我想粘贴 RSS feed URL、预览最近单集并选择一集入库，以便不需要订阅或轮询。
33. 作为内容收藏者，我想在入库前看到“转写/书文本会发送给 DeepSeek”的提示，以便知道数据流向。
34. 作为内容收藏者，我想在添加后看到 Item 的排队和处理进度，以便知道它什么时候能听。
35. 作为内容收藏者，我想在关闭 App 后让 Host 继续处理，以便不用守着页面。
36. 作为内容收藏者，我想在处理失败时看到可读原因并从手机重试，以便不用回桌面。
37. 作为内容收藏者，我想让分享进来的文本自动提取第一个 URL 并预填 Add，以便减少手动操作。
38. 作为内容收藏者，我想在 Host 拒绝不支持平台、内网 URL、元数据地址或超大文件时看到明确原因，以便知道 Host 不是开放下载器。

### 听

39. 作为听众，我想播放/暂停、拖动进度、调整倍速，以便连续听长内容。
40. 作为手机听众，我想在锁屏、后台和切换 App 时继续播放，以便像播客一样听。
41. 作为手机听众，我想在锁屏、通知栏、蓝牙耳机和车机上看到媒体控制，以便不打开 App 也能操作。
42. 作为听众，我想下次打开 App 时回到上次播放位置，以便续听。
43. 作为听众，我想在线流式播放未下载的 Item，以便不等待完整下载。
44. 作为听众，我想把音频下载到手机并在飞行模式播放，以便通勤/运动时不受网络影响。
45. 作为听众，我想看到下载进度、暂停/继续、失败重试和剩余大小，以便控制下载。
46. 作为听众，我想让下载只在 Wi-Fi 或充电时进行（可配置），以便节省流量和电量。
47. 作为听众，我想下载完成后校验 sha256，损坏时自动重新下载，以便不会播放坏文件。
48. 作为听众，我想在音频焦点被来电/其他 App 抢占时正确暂停/恢复，以便不出现两个声音同时播放。
49. 作为听众，我想在播放结束时自动标记 Consumption State 为完成，并可以手动改回未完成，以便不用手动维护状态。
50. 作为听众，我想从 Continue 一键续听，以便快速回到未完成内容。
51. 作为听众，我想在播放页看到 transcript 分段和时间戳，以便需要时读文字。
52. 作为听众，我想在 transcript 内搜索关键词并高亮，以便快速找到一段话。
53. 作为听众，我想在播放出错时看到可读原因并重试，以便判断是网络、文件还是 Host 问题。
54. 作为听众，我想让播放不因同步、下载或 Library 刷新而中断，以便连续听。
55. 作为听众，我想在下载队列多个 Item 时看到排队顺序和并发限制，以便知道什么时候轮到我。

### 读

56. 作为读者，我想在 App 内打开 EPUB、翻章、读正文，以便不离开库就能读书。
57. 作为读者，我想让 EPUB 的重排文本、图片、脚注/内部链接可读，以便 native 阅读器覆盖完整 EPUB 体验。
58. 作为读者，我想下次打开时回到上次阅读的章节/位置，以便续读。
59. 作为读者，我想离线阅读已下载的书，以便没有 Host 网络时也能读。
60. 作为读者，我想在书内搜索关键词并高亮，以便在长书里定位。
61. 作为读者，我想从搜索结果直接打开书的匹配段落，以便不用手动找。
62. 作为读者，我想把 transcript 当作阅读视图打开，以便只看文字不听音频。
63. 作为读者，我想调整字号、行高和阅读主题，以便在手机上舒适阅读。
64. 作为读者，我想在 EPUB 有 DRM、固定版式或解析失败时看到明确原因，以便知道为什么不能读。
65. 作为读者，我想让阅读进度自动进入 Continue，以便下次继续。
66. 作为读者，我想手动标记书为完成/未完成，以便纠正自动判断。

### 检索

67. 作为内容收藏者，我想用一个搜索框搜标题、摘要、transcript、书文本和 Tag，以便一个入口找全部内容。
68. 作为中文用户，我想让“记忆”“智能”这类两字中文词必须命中中文文本，以便关键词搜索可靠。
69. 作为内容收藏者，我想让英文短内容也能被转写并命中关键词，以便中英混合库可用。
70. 作为内容收藏者，我想让搜索结果按 Item 聚合并显示匹配段落，以便看出哪些内容提到它。
71. 作为内容收藏者，我想在结果中看到来源、类型、作者和日期，以便判断是否相关。
72. 作为内容收藏者，我想按类型、Consumption State、Tag 和 Source 组合过滤，以便缩小范围。
73. 作为内容收藏者，我想点击结果打开 Item 并定位到匹配的 transcript 段落或书段落，以便不用手动找。
74. 作为手机用户，我想在离线时搜索已下载的 Item，以便没有 Host 网络也能找回内容。
75. 作为内容收藏者，我想让本地搜索索引可以从已下载 Content Package 重建，以便数据库损坏或迁移后恢复。
76. 作为内容收藏者，我想在千条级 Library 上搜索 <1 秒，以便搜索不打断阅读。
77. 作为内容收藏者，我想现在只做关键词检索、不做语义检索，以便先验证核心搜索是否够用。

### 同步、离线与冲突

78. 作为手机用户，我想首次登录后同步 Library 元数据，以便立刻看到全部 Item，而不是只看到手机上的。
79. 作为手机用户，我想之后只拉取增量变更，以便同步快且省流量。
80. 作为手机用户，我想让 Host 删除的 Item 通过 tombstone 从手机删除，以便不会留下幽灵内容。
81. 作为手机用户，我想让下载文件按 sha256 去重和校验，以便不重复下载同一文件。
82. 作为手机用户，我想在离线时编辑 Tag、标记完成、推进播放/阅读位置，并把改动排队，以便没有网络也能操作。
83. 作为手机用户，我想在重连后自动推送排队的改动，以便不用手动同步。
84. 作为手机用户，我想让冲突按字段 last-write-wins 解决，并在服务端拒绝我的改动时看到可解释的结果，以便不会静默覆盖。
85. 作为手机用户，我想在手机和桌面之间同步播放/阅读进度和 Tag，以便换设备继续。
86. 作为手机用户，我想在重装 App 后登录并恢复 Library、下载选择和进度，以便不丢状态。
87. 作为手机用户，我想让后台周期同步和手动刷新都可控，以便在电量和新鲜度之间取舍。
88. 作为手机用户，我想只下载选中的 Item/Tag/大小范围，以便不把整个库塞进手机。
89. 作为手机用户，我想在存储配额不足时被提前告知并选择清理，以便不出现半下载状态。
90. 作为手机用户，我想在同步失败时看到错误、重试和上次成功时间，以便不让失败静默。
91. 作为手机用户，我想在 Host 不可达时继续播放/阅读已下载内容且不丢本地改动，以便离线可用。
92. 作为手机用户，我想让同步和下载不阻塞播放、阅读和搜索，以便体验流畅。

### 安全、隐私与运维

93. 作为 Host 所有者，我想让 Android 客户端只信任 HTTPS，并可选择信任 Caddy 内部 CA，以便 Tailscale 或自签 HTTPS 都能用。
94. 作为 Host 所有者，我想让 token 不出现在日志、崩溃报告或 Android 备份中，以便降低泄露风险。
95. 作为 Host 所有者，我想让设备撤销立即生效，以便丢失手机后不能继续访问。
96. 作为 Host 所有者，我想让本地音频/书/数据库只存在 App 私有目录，以便其他 App 不能随便读。
97. 作为内容收藏者，我想在 Add 页持续看到 DeepSeek 数据流提示，以便知道转写/书文本会离开 Host。
98. 作为 Host 所有者，我想让 Android 只把 URL 交给 Host 校验和下载，不在手机上做开放下载代理，以便不扩大攻击面。
99. 作为手机用户，我想在 Android 13+ 被正确请求通知权限、在 Android 14+ 正确声明媒体/数据同步前台服务，以便后台播放和下载不被系统直接杀掉。
100. 作为小米用户，我想看到电池优化设置引导，以便减少后台播放被系统清理。
101. 作为手机用户，我想让 App 升级后保留本地数据库和下载文件，或在不可兼容时安全地重建，以便不丢内容。
102. 作为 Host 所有者，我想让诊断日志包含同步/下载状态但不包含 token、密码、Cookie 或完整本地路径，以便排障且不泄露。
103. 作为未来云端用户，我想让客户端只通过 Host base URL 和同一套 API 切换 Mac/云端，以便不用重做数据模型。

## Implementation Decisions

### 范围与优先级

- V1 范围 = 需求文档 §5.8 的 FR-69 至 FR-73 + NFR-11；FR-74（标注）是 P2，不进入 V1。
- V1 的 P0：FR-70（后台/媒体通知/倍速播放）、FR-71 的阅读、FR-72 的离线播放。
- V1 明确包含的 P1：FR-69（手机收藏链接）、FR-71 的搜索/浏览、FR-72 的离线阅读/搜索、FR-73（app-managed sync）。这些 P1 是手机成为主要听设备所必需的，不再按 MVP 的 P1 短名单裁剪。
- 手机是主要听设备；桌面 Consumer Web Shell 保留，但不是 V1 的移动验收路径。Q10 手机 Web 结论已被本 spec 取代。
- 不引入云端、多用户、iOS、PDF、TTS、标注、语义检索、Topic、视频播放、Up Next、睡眠定时。

### 客户端技术形态

- 原生 Android，Kotlin + Jetpack Compose + Material 3。
- 播放使用 Media3 ExoPlayer + MediaSessionService；下载使用 WorkManager + OkHttp；本地数据库使用 Room；序列化使用 Kotlinx Serialization；EPUB 使用 Readium Kotlin toolkit（BSD-3）。
- `minSdk` 26，target 最新稳定 Android；只承诺手机形态，不承诺平板/折叠屏专门布局。
- 模块按职责拆分：`app`（导航/组装）、`core:model`、`core:network`、`core:database`、`core:sync`、`core:playback`、`core:search`、`feature:library`、`feature:player`、`feature:reader`、`feature:search`、`feature:add`、`feature:settings`。不引入跨端框架或 Node 构建链。
- Host 仍是 Python/FastAPI/SQLite/Mac；Android 不复制处理管线，只消费 Host API 和 Content Package。

### 本地数据与事实源

- Content Package 是事实源；Android 本地数据库和文件是选中 Item 的镜像/派生缓存，可从 Host 重新同步或从本地 Content Package 重建索引。
- Android 本地保存 Item 元数据、Artifact 元数据、TranscriptSegment、BookChapter/BookParagraph、Tag、同步游标、待推送 mutation、下载状态。
- 下载文件放在 App 私有目录；文件名和路径由 Item ID + Artifact kind 决定；临时文件下载完成后原子 rename；删除 Item/移除下载时清理对应文件。
- 本地搜索索引从已下载的 `transcript.json`、`book.json` 和 Item 元数据构建；索引损坏时可重建，不阻塞播放/阅读。
- 本地数据库升级使用 Room migration；不可兼容时保留用户可见提示，清空派生索引并重新同步，不静默丢下载。

### 认证与设备

- Host 增加设备 token：`POST /api/auth/device-token` 用 Host 密码换取长期 token；token 绑定 `device_id`、设备名和 session epoch。
- token 是随机 opaque secret，只显示一次；Host 只存哈希；Android 存 Android Keystore 保护的加密存储（Keystore + DataStore，不依赖已弃用的 EncryptedSharedPreferences）。
- 所有 API 同时接受 Cookie 会话（Web）和 `Authorization: Bearer <token>`（Android）。Bearer 写请求不依赖 CSRF；Cookie 写请求继续执行 Origin/Sec-Fetch-Site 校验。
- `GET /api/devices` 列出设备，`DELETE /api/devices/{device_id}` 撤销；Host Console 或 `trove device` CLI 至少提供一种管理入口。
- 密码修改、session epoch 变化、显式撤销都使对应 token 失效；撤销后下一次请求返回 `auth.device_revoked`。Android 收到 401/`auth.device_revoked` 时清除 token 并回到登录，不继续重试。
- Android 正式 release 只允许 HTTPS；Caddy 内部 CA 场景允许用户安装 CA 并在 network security config 中信任用户 CA；Tailscale 使用公开证书。明文 HTTP 只存在于独立的 `lan` 调试 flavor（持续警告、不随正式包发布），release 不提供运行时明文开关。
- 登录失败继续沿用 Host 的按 IP 限速；Android 显示 `Retry-After`。
- 登出默认只撤销当前设备 token 并回到登录；清除本地下载/数据库是单独确认动作，不随登出自动执行。

### 同步协议

- 同步分两条流，避免播放进度每 5 秒推进导致内容 manifest 抖动：
  - **Content stream**：Item 元数据、Tag、Artifact 文件清单、Processing State、tombstone。任何内容变化递增 `version` 和 `content_seq`。
  - **State stream**：`audio_position_sec`、`book_locator`、`Consumption State`、`last_consumed_at`。任何状态变化递增 `state_seq`，不改变 `version`/`content_seq`。
- `version` 是 Item 级内容版本；`content_seq`/`state_seq` 是服务端分配的单调同步序号；对客户端暴露为 opaque cursor，不暴露数据库实现。
- Host 维护 `sync_epoch`（数据库身份）；manifest/state 响应都带 `epoch`。客户端发现 epoch 变化（Host 从备份恢复或重建数据库）时保留待推送 mutation，清空游标并做全量重同步，避免旧游标跳过新数据。
- `GET /api/sync/manifest?cursor=&limit=` 返回 Content stream 的一页：Item 元数据、Tag、文件清单、`version`、`deleted_at`（tombstone）、`next_cursor`、`has_more`、`epoch`。
- `GET /api/sync/state?cursor=&limit=` 返回 State stream 的一页：Item ID、`state_seq`、播放/阅读位置、Consumption State、`last_consumed_at`、`next_cursor`、`has_more`、`epoch`。
- manifest 使用 compact Item payload：只包含移动端需要的元数据、`processing_state`、`error_code`/`error_message`、Tag、`version` 和 `files`；不返回 Run steps、日志 tail 或搜索 evidence。完整 Item 详情仍走 `GET /api/items/{id}`。
- 同步 payload 形状：
  - manifest Item：`id`、`version`、`source_type`、`platform`、`title`、`author`、`published_at`、`fetched_at`、`language`、`duration_sec`、`summary`、`tags`、`processing_state`、`error_code`/`error_message`、`has_audio`、`has_book`、`files[]`。
  - `files[]`：`kind`、`sha256`、`size`、`mime`、`version`、`url`。
  - tombstone：`id`、`version`、`deleted_at`、`epoch`。
  - state Item：`id`、`state_seq`、`audio_position_sec`、`book_locator`、`consumption_state`、`last_consumed_at`。
- 文件清单条目包含 `kind`、`sha256`、`size`、`mime`、`version`、下载 `url`；客户端按 `sha256` 判断是否需要下载。
- 删除 Item 改为 soft delete：设置 `deleted_at`、递增 `version`/`content_seq`、删除派生文件和搜索索引、保留 tombstone 行；普通 Library/Search 不返回已删除 Item，manifest 返回 tombstone。V1 不清理 tombstone，单用户库规模可接受。
- 重新添加已 tombstone 的同一 `source_key` 时复活同一 Item ID：清空 `deleted_at`、递增 `version`/`content_seq`、创建新的 Processing Run；旧客户端会先收到 tombstone 再收到复活后的 Item。
- 客户端游标无效/过期，或游标序号大于 Host 当前最大序号（例如 Host 从较旧备份恢复）时，Host 返回 `sync.cursor_invalid`；客户端清空本地游标并做一次全量 manifest 重同步。
- 首次同步只同步元数据，不自动下载所有文件；文件下载由用户按 Item/Tag/大小选择。manifest 分页大小由 Host 控制，客户端按 `has_more` 继续。
- 同步触发：App 启动/回前台、手动下拉刷新、添加成功后、网络恢复、WorkManager 周期任务（系统允许的最小周期，默认 15 分钟，可关闭）。不使用 FCM/服务端 push。
- 所有同步错误必须可见；客户端保留上次成功时间和错误码，不静默吞掉。

### 冲突与幂等

- 单用户、多设备场景按字段 last-write-wins。字段至少包括：`audio_progress`、`book_progress`、`consumption_state`、`tags`。
- Web/Consumer Web Shell 的写操作也参与同一套字段时钟，使用 `device_id = host-web` 和服务端时间；不能因为来自 Web 就绕过 LWW。
- 每个客户端写请求携带 `client_updated_at`（设备 UTC 毫秒）和 `Idempotency-Key`；Host 按字段记录获胜的 `client_updated_at` 和 `device_id`。
- Host 比较顺序：`client_updated_at` 大者胜；相等时按 `device_id` 字典序稳定决胜；超过 Host 当前时间 5 分钟的客户端时间视为无效，Host 使用服务端时间并返回 `sync.clock_skew`（非致命）。
- 写响应返回 `applied: true/false`、服务端 canonical Item/state 和当前字段时钟；客户端用 canonical 值覆盖本地乐观值；`applied: false` 时显示非阻塞的“已在其他设备更新”提示。
- Tag 写入使用整组替换并经过 Host 的 Tag 归一化；Host 返回 canonical Tag 列表。进度写入按字段合并，不因一次 book progress 覆盖更新的 audio progress。
- `Idempotency-Key` 在 Host 保留至少 24 小时；重复请求返回第一次的结果，避免重试造成重复 Processing Run 或 Tag 版本跳变。
- 新建 Item 仍按 `source_key` 去重；重复添加返回已有 Item，不依赖幂等键。

### Host API 变更

| 方法 | 路径 | 用途 |
|---|---|---|
| POST | `/api/auth/device-token` | Host 密码换取长期设备 token |
| GET | `/api/devices` | 列出已授权设备 |
| DELETE | `/api/devices/{device_id}` | 撤销设备 token |
| GET | `/api/sync/manifest` | Content stream：Item/Tag/文件/tombstone + cursor |
| GET | `/api/sync/state` | State stream：播放/阅读位置/Consumption State + cursor |
| GET | `/api/items/{item_id}/files/{kind}` | 下载 Content Package 文件，支持 Range/ETag/sha256 |
| PUT | `/api/items/{item_id}/tags` | 替换 Tag 集合，带 `client_updated_at` / `Idempotency-Key` |
| PUT | `/api/items/{item_id}/progress` | 扩展现有接口：位置/状态 + `client_updated_at` / `Idempotency-Key` |
| DELETE | `/api/items/{item_id}` | 改为 soft delete + tombstone |
| GET | `/api/items/{item_id}` | 返回 `version`；普通读取不返回已删除 Item |
| GET | `/api/health` | 增加 `api_version`、`capabilities`（至少 `sync`、`device_tokens`、`file_download`） |

- `/api/devices`、`/api/sync/*`、`/files/{kind}` 都需要认证；Cookie 或 Bearer 均可。设备撤销允许撤销当前设备或列表中的其他设备。
- 现有 `/api/items/{id}/audio`、`/transcript`、`/book/chapters/{n}` 保留，供 Web 和在线预览使用；Android 镜像走 `/files/{kind}`。
- `/files/{kind}` 的 `kind` 使用 Content Package 的 `audio`、`transcript`、`book`、`book_json`、`ai`、`cover`；只返回数据库记录的 artifact，不接受任意路径；带 `ETag`（sha256）、`Accept-Ranges: bytes`、`Cache-Control: private`、`X-Content-Type-Options: nosniff`。
- API 错误保持 `{code, message, details?}`；新增稳定错误码：`auth.device_revoked`、`auth.device_token_invalid`、`sync.cursor_invalid`、`sync.clock_skew`、`sync.stale_write`、`file.artifact_missing`。
- OpenAPI 是契约；Android 使用手写 thin client + Kotlinx Serialization，不引入完整代码生成。Host 契约测试与 Android DTO/契约 fixture 测试共同防止漂移。
- 不做 URL 版本前缀；新增字段保持向后兼容；客户端通过 `/api/health` 判断 Host 是否具备同步能力。未来云端 Host 复用同一路径和资源形状。

### 数据库变更（Host）

- `items` 增加 `version`、`deleted_at`、`content_seq`、`state_seq`。
- 新增 `device_tokens`（`device_id`、`name`、`token_hash`、`created_at`、`last_used_at`、`revoked_at`、`session_epoch`）。
- 新增 `sync_sequence`（全局单调序号 + `epoch` 数据库身份）；新增 `sync_mutations`（`device_id` + `mutation_id` 唯一，保存结果和时间，用于幂等）。
- 新增按字段的同步时钟：`sync_field_clocks`（`item_id`、`field`、`client_updated_at`、`device_id`），覆盖 `audio_progress`、`book_progress`、`consumption_state`、`tags`。
- soft delete 后，Library/Search/Continue 默认过滤 `deleted_at IS NOT NULL`；FTS 删除对应行；Content Package 删除派生文件；保留 Item 行和 tombstone 元数据。
- 迁移需要为现有 Item 回填 `version=1`、`content_seq`、`state_seq`；已有音频/书/文本文件继续可用。迁移前备份提示由部署文档负责。
- Content Package 布局不变；`source.json` 不新增同步字段，同步状态只存在 Host SQLite 和 Android 本地库。

### Android 本地模型

- `ItemEntity`：Item 元数据、`version`、`content_seq`、`state_seq`、Processing State、Consumption State、下载状态、最后同步时间。
- `ArtifactEntity`：`item_id`、`kind`、`sha256`、`size`、`mime`、`local_path`、`download_state`。
- `TranscriptSegmentEntity`、`BookChapterEntity`、`BookParagraphEntity`、`TagEntity`、`ItemTagEntity`。
- `SyncCursorEntity`：content/state 两条游标、`sync_epoch`、上次成功时间、错误码。
- `PendingMutationEntity`：字段、Item ID、payload、`client_updated_at`、`Idempotency-Key`、重试次数、最后错误。
- `SearchFtsEntity`：`norm_text`、原文 `text`、`item_id`、`doc_kind`、`ref`；与 Host 相同的 CJK bigram 归一化。
- 所有本地表可重建；下载文件不能从本地数据库单独恢复，但可以从 Host 重新下载；删除前必须确认。

### 播放与后台

- Media3 ExoPlayer 放在 `MediaSessionService` 中；前台服务类型 `mediaPlayback`；媒体通知使用 MediaSession；锁屏/蓝牙/车机通过系统媒体控制。
- 播放状态保存每 5 秒 + 暂停/停止/切换 Item 时；先写本地，再按节流推 Host；离线时进入 PendingMutation。
- 支持 1×/1.25×/1.5×/2×；不实现睡眠定时、Up Next、播放队列页；一次只播放一个 Item。
- 已下载优先本地文件；未下载使用 Host `/api/items/{id}/audio` 的 Range 流。播放开始前不强制完整下载。
- 音频焦点、耳机拔出、来电由 Media3/系统音频焦点处理；错误映射为可读提示并允许重试。
- 播放结束自动标记完成；用户手动标记完成/未完成时写本地并排队同步；自动状态规则与 Host 保持一致。

### 下载与存储

- WorkManager 管理下载队列；同一时间 1 个前台下载，其余排队；下载使用临时 `.part` 文件，完成后校验 sha256 再原子 rename。
- 只有已经存在对应 Artifact 的 Item 才能下载/播放；Processing State 可以是 completed 或 failed（失败但音频/书已保留），但处理中且没有 artifact 时只显示状态。
- 支持 Range 续传；服务端返回 ETag/sha256；客户端保存已下载字节和 ETag；续传使用 `Range` + `If-Range: <ETag>`，ETag 变化时丢弃半成品并全量重下。
- 下载约束：默认 Wi-Fi；可选“仅充电时下载”；用户可临时允许移动网络。
- 下载前检查用户设置的存储配额（默认 5 GB，可配置）和系统剩余空间；不足时阻止并提示清理，不静默删除已有下载。
- 下载使用前台服务通知（Android 14+ 声明 `dataSync` 类型）；失败/重试/暂停在下载中心可见。
- 移除下载只删除本地文件、索引和下载记录，不调用 Host DELETE；删除 Item 才走 Host soft delete。
- 文件清单变化时，删除不再存在的旧 artifact 本地副本；正在播放的文件延迟到播放结束再清理。

### 阅读

- EPUB 使用 Readium Kotlin toolkit 渲染 `book.epub`；支持重排文本、图片、内部链接/脚注；书内搜索作为 P1。
- Readium 只加载本地 EPUB 资源，禁用脚本、远程图片/字体/请求和外部导航；Host 已拒绝 DRM/固定版式，Android 仍按不可信内容处理。
- `book.json` 用于搜索文本、章节索引和与 Web 的阅读位置映射；`book.epub` 用于 native 渲染。
- `book_locator` 升级为 `schema: 2` 的 JSON：保留 `chapter_index`/`paragraph_index`/`scroll_ratio`，并增加 Readium 可用的 `epub_href`/`epub_progression`。Host 原样存储并校验，Web 使用 legacy 字段，Android 优先使用 EPUB 字段并可回退。
- Transcript 使用 Compose 列表显示 `seq`/`start_ms`/`end_ms`/`text`；支持文内搜索/高亮；不实现点击 transcript 跳音频或同步滚动。
- 阅读进度滚动节流写回；离线进入 PendingMutation；继续阅读从本地位置恢复。
- 阅读器提供字号、行高、浅色/深色/护眼主题；不要求分页模式。
- 书内搜索、脚注、图片加载失败要有明确占位/错误，不白屏。

### 搜索

- 在线搜索调用 Host `/api/search`；离线搜索查询 Android 本地索引，只覆盖已下载 Item。
- 本地索引与 Host 使用同一套中文 bigram 归一化和查询构造规则；单字回退 `LIKE`，英文使用词干/小写归一化；共享契约 fixture 验证“人工智能 → 人工 工智 智能”等用例。
- 搜索结果按 Item 聚合；每条结果保留最多 3 条 evidence；`ref` 对 transcript 是 `seq/start_ms`，对书是 `chapter/paragraph`。
- 点击结果：transcript 打开播放页并高亮对应段落；书打开 Reader 并定位章节/段落；不做音频跳转/同步滚动。
- 本地索引在下载完成、Item 更新、删除、App 升级后增量或重建；索引重建不阻塞 UI。
- 目标：已下载 1,000 Item 的本地搜索 p95 <1 秒；在线搜索沿用 Host 目标。

### 入库与处理状态

- Add 支持：系统分享 `text/plain`（提取第一个 URL）、手动粘贴 URL、播客 feed 预览后选集。
- URL 校验、平台白名单、playlist/多 P 拒绝、SSRF/大小/类型限制全部由 Host 执行；Android 只展示 Host 返回的稳定错误码和中文提示。
- 重复添加返回已有 Item 并直接打开详情；不创建第二个 Processing Run。
- Add 页持续显示 DeepSeek 数据流提示；MVP 的 per-item 开关仍不做。
- 添加成功后进入 Item 详情/Inbox，显示 Processing State；App 在前台时轮询 Item/Run 状态（有上限和退避），后台由周期同步更新；不使用 WebSocket。
- 失败原因映射为网络、需要登录、地区限制、DRM、不支持、解析、ASR、LLM、存储、内部错误；支持从手机重试失败 Run。
- 手机不负责上传本地音频/EPUB 文件；本地文件入库继续走 Host Console 浏览器上传。分享本地文件到 Trove 作为后续需求。

### UI 与平台行为

- 主导航：Library、Search、Add；Continue 是 Library 的入口/分组；Item 详情进入 Now Playing 或 Reader。
- Library 默认队列式列表；行内播放按钮；下载/在线状态图标；Processing State 徽标；Inbox 过滤。
- Now Playing：封面/标题/作者、进度、倍速、播放控制、下载状态、transcript 折叠区；媒体通知与锁屏元数据一致。
- Reader：章节导航、正文、文内搜索、字号/主题设置、阅读进度。
- Search：查询框、过滤 chip、按 Item 聚合结果、evidence 高亮、离线状态。
- Add：URL 输入/分享预填、播客预览、DeepSeek 提示、提交/错误/处理中状态。
- Settings：Host 地址、账号/设备、同步状态、下载约束、存储配额/占用、电池优化引导、关于/版本、登出/清除数据。
- 所有网络/同步/下载错误都有可见状态和重试入口；不允许无限 loading 或静默失败。
- Android 13+ 请求 `POST_NOTIFICATIONS`；Android 14+ 声明 `mediaPlayback`/`dataSync` 前台服务权限；小米等 OEM 提供电池优化设置引导。
- 默认中文 UI；不要求多语言。无障碍至少保证 TalkBack 可读主要按钮和状态。

### 安全与隐私

- Android 正式 release 只信任 HTTPS；network security config 默认禁止 cleartext；Caddy 内部 CA 通过用户安装 CA + 显式信任用户 CA 支持。独立 `lan` 调试 flavor 可按需允许受信任局域网 cleartext，但持续警告且不随正式包发布。
- token 存 Keystore 保护的存储；日志、崩溃报告、诊断导出中脱敏 token/password/Cookie/Authorization。
- Android 本地文件/数据库在 App 私有目录；Android backup 排除 token 和媒体文件，避免云备份泄露。
- 设备撤销立即生效；密码修改使所有 token 失效。
- Android 不提供开放 URL 下载代理；所有 Source 校验和下载由 Host 执行。
- DeepSeek 提示保留；V1 不做 per-item LLM 开关。
- 本地媒体/书籍删除必须用户确认；清除 App 数据前提示会删除下载。

### 运维与兼容

- `GET /api/health` 返回 `api_version` 和 capabilities；App 在登录后检查 `sync` 能力，不兼容时阻止进入并提示升级 Host/App。
- API 变更保持向后兼容；破坏性变更必须新增 capability/版本，不静默改变现有字段语义。
- Host 升级流程仍为 `uv sync` → `trove db upgrade` → 重启；V1 迁移在部署文档中说明备份和回滚。
- Host 从备份恢复后需要通过 CLI 更换 `sync_epoch`，强制所有客户端做一次全量重同步，避免旧游标跳过恢复后缺失的数据。
- Android APK 以 sideload/个人分发为主；Play Store 上架、签名托管和商店合规不在 V1。
- Android CI 至少跑 JVM/Compose 测试和 lint；instrumented 测试在本地/专用 runner 跑；真实设备验收手动执行。
- 诊断信息包括：Host URL（脱敏）、API 版本、最后同步时间、cursor 状态、下载队列、错误码、存储占用；不包含 token/密码/完整文件路径。

## Testing Decisions

### 主测试缝

V1 采用两个 seam：

1. **Host HTTP seam（复用现有）**：启动真实 Host（API + worker）和临时 `TROVE_HOME`，使用真实 SQLite、迁移、文件系统、FTS5；外部 `Downloader`、`FeedClient`、`Transcriber`、`Organizer` 继续用 fake。通过 HTTP 像客户端一样驱动，覆盖设备认证、manifest/cursor、state sync、文件 Range/ETag、tombstone、LWW、幂等和 soft delete。
2. **Android App seam（新增）**：通过 App 的公开 ViewModel/Compose UI 测试，底层用 fake `TroveApi`（实现 Host 契约）+ 真实 Room/临时文件/Robolectric。覆盖 Library、Add、播放状态、阅读、搜索、离线队列、同步状态和错误状态。同步游标/断点/冲突/tombstone 这些边界也从这个 seam 进入，必要时用 fake API 精确编排响应，不另建纯 SyncEngine seam。
3. Android 平台相关行为（Media3 前台服务、媒体通知、WorkManager 下载/续传）用少量 instrumented tests 覆盖；真实设备行为放到手动验收，不用模拟器假装覆盖。

### 好测试的标准

- 只测外部行为：HTTP 状态/JSON/headers、Content Package 文件、Android 可见 UI/状态、Room 的公开查询结果、播放/同步状态；不测私有方法、内部调用顺序或 SQL 细节。
- 确定性：临时目录、固定时钟/固定 fixture、fake 外部适配器；不访问真实网络；等待用有超时的轮询，不用固定 sleep。
- 失败路径与 happy path 同等重要：token 过期/撤销、Host 离线、cursor 无效、manifest 分页、tombstone、重复添加、私网 URL、超大文件、DRM EPUB、下载中断/校验失败、LWW 旧写入、时钟偏移、存储不足、同步冲突。
- 数据契约可以断言文件存在、sha256、zip/Content Package 内容，因为这是用户可见的 Export/离线行为。
- Android UI 测试断言用户能看到/操作的内容，不依赖 Compose 节点内部实现；对媒体/下载只断言对外状态和通知，不测 ExoPlayer 内部。

### Host HTTP seam 覆盖

| 区域 | 场景 | 断言 |
|---|---|---|
| 设备认证 | 密码换 token；Bearer 访问；撤销；密码修改；错误 token | 200/401；`auth.device_revoked`；token 不出现在响应/日志 |
| 同步 manifest | 首次全量；分页；增量；文件清单；版本递增；epoch 变化 | 游标推进；无重复/遗漏；`has_more` 正确；epoch 变化触发全量重同步 |
| State sync | 播放/阅读位置、Consumption State；进度写不 bump content_seq | state_seq 推进；content manifest 不抖动 |
| Tombstone | 删除 Item；Library/Search 不再返回；manifest 返回 tombstone；重新添加复活 | 文件/索引删除；tombstone 正确；复活后新版本 |
| 文件下载 | 音频/transcript/book/book_json/ai/cover；Range；ETag；sha256；路径穿越 | 200/206；`Accept-Ranges`；sha 匹配；404/403 |
| 冲突/幂等 | 旧 `client_updated_at` 被忽略；新值生效；相同 `Idempotency-Key` 重放 | `applied` 正确；canonical 值正确；无重复副作用 |
| Tag | 替换/归一化/大小写/单复数；离线重放 | canonical Tag；content_seq 递增；搜索更新 |
| 兼容性 | OpenAPI 包含新路由；Bearer security scheme；health capabilities | 契约测试通过；旧 MVP 路由不回归 |

### Android App seam 覆盖

| 区域 | 场景 | 断言 |
|---|---|---|
| 连接/认证 | 输入 Host；错误密码；token 失效；Host 离线；TLS 错误 | 明确错误/重试；不丢本地数据 |
| Library | 全量/增量；过滤；排序；Processing State；Inbox；离线列表 | 可见 Item/状态正确；空/加载/错误状态 |
| Add | 分享文本；粘贴 URL；重复；playlist 拒绝；播客预览；DeepSeek 提示 | 预填/错误/已有 Item；处理状态可见 |
| 播放 | 播放/暂停/seek/倍速；恢复位置；本地/流式；播放错误 | 状态正确；位置保存；不因同步中断 |
| 下载 | 排队；暂停/继续；Wi-Fi 约束；sha 校验；断点续传；配额不足 | 下载状态/通知/文件正确；失败可重试 |
| 阅读 | EPUB 翻章；图片/脚注；阅读位置；离线；书内搜索；transcript 搜索 | 内容/位置/高亮正确；错误可读 |
| 搜索 | 中文两字；英文；按 Item 聚合；过滤；离线；定位段落 | 命中/不命中；evidence/锚点正确 |
| 同步 | 首同步；增量；tombstone；离线队列；LWW；冲突提示；cursor 无效；epoch 变化 | 本地状态收敛；无静默覆盖；错误可见；epoch 变化全量重同步 |
| 存储 | 移除下载；删除 Item；配额/剩余空间；App 升级 | 文件清理正确；Host Item 保留/删除正确 |
| 平台 | 通知权限；前台服务；电池优化引导；媒体通知 | 系统权限/通知状态正确 |

### Fixtures、纯函数与手动验收

- 共享契约 fixture：Host 契约测试生成/校验 manifest、state、错误、文件元数据的 JSON fixture；Android DTO/App 测试消费同一组 fixture，避免两边各写一份想象。
- 纯函数单测：CJK bigram 归一化/查询构造、URL 提取/规范化、Tag 归一化、`book_locator` 新旧 schema 解析、LWW 比较、cursor 分页边界。它们编码微妙规则，值得独立覆盖。
- Golden fixtures：公开领域 EPUB（现有 Aesop/Oedipus）、短音频、transcript JSON、podcast RSS XML；不使用受版权保护内容或凭空捏造的占位数据。
- 手动验收（Xiaomi 13 / Android，真实 Host，Caddy 或 Tailscale HTTPS）：
  - 分享链接入库，Host 处理完成，手机看到状态和可播放内容。
  - 下载一条 ≥60 分钟音频，飞行模式连续播放、锁屏、媒体通知、蓝牙控制、倍速、续听。
  - 下载 EPUB，离线阅读、翻章、图片/脚注、书内搜索、阅读位置恢复。
  - 离线搜索已下载内容，中文两字词命中；打开 transcript/书匹配段落。
  - 离线改 Tag、标记完成、推进进度；重连后同步；另一设备/Web 看到 canonical 结果。
  - Host 删除 Item，手机同步删除；重装 App 后登录恢复 Library 和进度。
  - 下载中断/续传、sha 校验失败重下、存储配额不足提示。
  - token 撤销后手机立即 401；密码修改后所有设备失效。
  - 记录电量、存储、失败/重试；不把“模拟器通过”当作真机通过。

### Prior art

- `tests/test_host_seam.py`、`tests/test_api_contract.py`、`tests/test_browser.py`、`tests/test_security.py`、`tests/test_processing.py` 是 Host seam 的现有范例：真实 Host、fake 外部依赖、HTTP/UI 行为断言。
- `tests/test_domain_search.py`、`tests/test_domain_*` 风格的纯函数表驱动测试用于 CJK/URL/Tag/locator/LWW。
- Android 测试是新代码：Compose UI test + Robolectric/JVM + 少量 instrumented tests；不引入第三套 seam。共享 fixture 是两边契约的唯一来源。

## Out of Scope

- iOS、PWA/移动 Web 作为主要消费端；Consumer Web Shell 保留但不在 V1 移动验收。
- 云端处理、云存储、云同步、公网暴露、多用户、账号体系。
- Android 标注（FR-74，P2）、PDF、TTS、语义/向量检索、Topic、实体抽取、全局 Tag 重命名/合并。
- 视频播放、时间戳跳转、同步滚动、点击 transcript 跳音频、Up Next、播放队列页、睡眠定时。
- 手机上传本地音频/EPUB 文件；本地文件入库继续走 Host Console 浏览器上传。
- Android 端编辑标题/作者；Host Console 仍是元数据修正入口，Android 只编辑 Tag。
- 批量导入、RSS 自动轮询/订阅、开放下载代理、DRM 绕过。
- 整库自动下载；V1 只做选择性同步（Item/Tag/大小）。
- 后台推送（FCM）、服务端 push、实时 WebSocket；同步用轮询/WorkManager。
- Play Store 上架、商店合规、应用内购买、多语言、平板/折叠屏专门布局、Android TV/Wear/Auto。
- 完整备份/恢复 UI、独立 Markdown 导出、桌面 App、Docker/云端 Host 部署。
- 任何 P2/P3 需求，除非明确列入本 spec 的 V1 范围。

## Further Notes

- **决策记录**：V1 明确选择 native Android；手机是主要听设备。这个决定取代 Q10 手机 Web 的验收路径，但不否定 Consumer Web Shell 作为桌面/管理壳的价值。
- **ADR**：实现前新增 ADR-0009（Native Android client + app-managed sync），记录设备 token、两条同步流、tombstone、LWW 和 Content Package 镜像决策。ADR-0001/0002/0006/0008 继续有效；如果实现发现 ADR 前提不成立，先更新 ADR 再改代码。
- **需求映射**：FR-69/70/71/72/73、NFR-11；FR-74 排除。需求文档 §8.2 的同步验收（断点续传、校验、删除同步、冲突可解释、选择性同步）是本 spec 的验收底线。
- **主要风险**：
  - OEM 后台限制（小米/Android）：前台服务 + 媒体通知是标准路径，但仍需真机手动验收和电池优化引导；不承诺所有 OEM 行为一致。
  - Caddy 内部 CA：Android 默认不信任用户 CA；需要 network security config 和安装 CA 的明确文档。Tailscale 是更省事的默认。
  - Readium locator 与 Web `book_locator` 的映射：用 versioned locator + legacy fallback，并用跨客户端测试覆盖。
  - 本地搜索与 Host 搜索漂移：共享 CJK 归一化 fixture，任何规则变更两边同时更新。
  - 时钟偏移/LWW：客户端时间超过 Host 5 分钟会被规范化；冲突提示必须可解释，不静默覆盖。
  - 存储：100 小时音频约 2.8 GB；手机配额默认 5 GB，只做选择性同步，不承诺整库离线。
  - 契约漂移：OpenAPI + 共享 fixture + Host/Android 双侧契约测试；不用完整代码生成。
- **建议实施顺序**：
  - M0：Host 设备 token、manifest/state、文件下载、tombstone、LWW；Android 工程骨架、登录、Library 首同步。
  - M1：Media3 播放、下载/续传、离线播放、媒体通知；真机后台播放 spike。
  - M2：EPUB Reader、transcript 搜索、本地搜索、Add/分享、Continue、Tag/进度同步。
  - M3：冲突/重装/配额/错误态、真机验收、性能与安全收口。
- **V1 完成定义**：真实 Xiaomi 13 上完成“分享链接 → Host 处理 → 下载 → 飞行模式听 1 小时 → 锁屏/通知/续听 → 读 transcript/EPUB → 搜索 → 离线改 Tag/进度 → 重连同步 → Host 删除同步 → 重装恢复”的闭环；Host seam 与 Android App seam 测试全绿；无未声明的 P2/P3 功能进入 V1。
- **Issue 拆分**：实现 issue 已拆分到 [issues/](issues/)（01–22），按 M0–M3 拆分；本 spec 不替代 issue 级验收。
