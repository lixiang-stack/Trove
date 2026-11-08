# Trove MVP — Feature Spec

Status: ready-for-agent  
Feature: trove-mvp  
Date: 2026-11-08  
Scope: MVP = 需求文档的 P0 + 明确列出的 P1 短名单  
Sources: [trove-requirements.md](../../docs/ideas/trove-requirements.md)、[trove-tech-selection.md](../../docs/ideas/trove-tech-selection.md)、[docs/adr/](../../docs/adr/)、[GLOSSARY.md](../../GLOSSARY.md)

## Problem Statement

我收藏的长内容散落在 B 站、YouTube、播客和本地 EPUB 里。我想把它们变成一个可听、可读、可检索的个人库：粘贴链接或上传文件后自动处理，之后主要靠听，需要时读 transcript 或书，按关键词和 Tag 找回来。现有播放器、稍后读工具和笔记软件要么不转文本，要么不统一检索，要么把内容锁在云端；我也不想手动整理每一条。

MVP 还要回答一个具体问题（[Q10](../../docs/ideas/trove-requirements.md#q10)）：手机浏览器能否成为我主要的“听”设备？如果能，MVP 的消费验收在手机上；如果不能，消费收缩到桌面，native 播放器进入下一里程碑。

## Solution

在 Mac 上运行一个本地 Host：浏览器打开 Host Console 入库、管理、搜索，Consumer Web Shell 负责播放、阅读和搜索定位。我可以粘贴 B 站/YouTube 单条视频、上传本地音视频/EPUB、粘贴播客 feed 选单集；Host 下载、抽音频、转写、生成摘要和 Tag、建立索引。音频是主要消费方式；transcript 和 EPUB 可读；中文两字词可搜；搜索结果按 Item 聚合并定位到匹配段落。内容包是普通文件，可导出 zip；DeepSeek 只接收转写/书文本用于整理，入库时明确提示。

## User Stories

### 安装与认证

1. 作为 Host 所有者，我想在首次运行时设置单用户密码，以便只有我能使用这个库。
2. 作为 Host 所有者，我想从桌面或手机浏览器登录，以便随时入库、播放和搜索。
3. 作为 Host 所有者，我想让登录会话保持一段时间，以便不用每次打开都登录。
4. 作为 Host 所有者，我想让未认证请求被拒绝，以便局域网里的其他人不能操作我的库。
5. 作为 Host 所有者，我想让 Host 在登录 macOS 后自动启动，以便不用手动开进程。
6. 作为 Host 所有者，我想在 Host 重启后看到队列和运行中的 Processing Run 恢复，以便不丢 Processing Run、不重复处理。
7. 作为 Host 所有者，我想看到 Host/数据库/worker 的健康状态，以便知道服务是否正常。

### 收藏与入库

8. 作为内容收藏者，我想粘贴一条 B 站单视频 URL 并入库，以便把它变成可听、可检索的内容。
9. 作为内容收藏者，我想粘贴一条 YouTube 单视频 URL 并入库，以便把它变成可听、可检索的内容。
10. 作为内容收藏者，我想在粘贴播放列表或多 P 链接时被明确拒绝，以便不会错误地只处理其中一条。
11. 作为内容收藏者，我想上传本地音频并让库内保留副本，以便原文件不被移动或删除。
12. 作为内容收藏者，我想添加本地视频并只保留原始路径和抽出的音频，以便不把大视频复制进库。
13. 作为读者，我想添加 DRM-free、可重排的 EPUB 2/3，以便提取元数据、章节和正文。
14. 作为播客听众，我想粘贴 RSS feed URL、预览最近单集并选择一集入库，以便不需要订阅或轮询。
15. 作为内容收藏者，我想看到 Item 的原始 URL、平台、类型、标题、作者、发布日期和抓取时间，以便追溯来源。
16. 作为内容收藏者，我想在重复添加同一 URL/文件时得到“已存在”，以便不重复下载和处理。
17. 作为内容收藏者，我想在 URL 指向内网、元数据地址或不支持的平台时被拒绝，以便 Host 不被当成开放下载器。
18. 作为手机用户，我想从手机浏览器上传音频/EPUB 并看到上传进度，以便不用把文件先放到 Mac 上。
19. 作为桌面用户，我想输入 Mac 上的本地文件路径来添加音频/视频，以便处理大文件时不用先上传。
20. 作为内容收藏者，我想在入库时看到“转写/书文本会发送给 DeepSeek”的提示，以便知道数据流向。
21. 作为读者，我想在 EPUB 有 DRM、固定版式或缺章节时看到明确原因，以便知道为什么不能入库。
22. 作为内容收藏者，我想让入库在浏览器关闭后继续，以便不用守着页面。

### 处理

23. 作为内容收藏者，我想看到每个 Item 的 Processing State（排队/下载/抽音频/转写/整理/索引/完成/失败），以便知道它在哪一步。
24. 作为内容收藏者，我想在失败时看到可读的失败原因，以便判断是网络、登录、地区、DRM 还是解析问题。
25. 作为内容收藏者，我想重试失败的 Processing Run，以便不用重新添加 Item。
26. 作为内容收藏者，我想让重试从断点继续、不重做已完成阶段，以便节省时间和 API 调用。
27. 作为内容收藏者，我想取消排队中的 Processing Run，以便它不会开始处理。
28. 作为内容收藏者，我想取消运行中的 Processing Run（best-effort），以便尽快停止并清理当前阶段的半成品。
29. 作为内容收藏者，我想在取消/失败后保留已完成的音频和文本，以便仍然可以听/读。
30. 作为内容收藏者，我想在 Host 重启后回收运行中的 Processing Run 并从安全阶段继续，以便不留下永久卡住的 Processing Run。
31. 作为内容收藏者，我想看到每个 Run 的阶段记录和日志 tail，以便排查失败。
32. 作为内容收藏者，我想让下载的视频只保留音频，以便不占大量磁盘。
33. 作为读者，我想得到带分段时间戳的 transcript，以便阅读和定位；我不需要词级时间戳。
34. 作为内容收藏者，我想得到 1–2 句摘要和 3–5 个 Tag，以便不用手动整理。
35. 作为内容收藏者，我想让 Tag 做大小写/单复数/同义词归一化，以便同类 Tag 不重复出现。
36. 作为内容收藏者，我想看到 AI 结果使用的模型、prompt 版本、token 用量和估算成本，以便追溯和重跑。
37. 作为内容收藏者，我想在整理失败或超过 token/调用限额时看到明确错误，以便调整后重试。
38. 作为内容收藏者，我想让长转写/书文本分块 map-reduce 且不静默截断，以便摘要覆盖全文。
39. 作为内容收藏者，我想在更换 prompt 后只重跑整理/索引阶段，以便不重新下载和转写。
40. 作为读者，我想让 EPUB 提取出章节结构、正文和分页阅读所需的段落，以便薄阅读器可以翻章阅读。
41. 作为内容收藏者，我想让失败的 Item 不丢原始文件，以便随时重试或导出。

### 听

42. 作为听众，我想播放/暂停/拖动进度/调整倍速，以便连续听长内容。
43. 作为手机听众，我想在锁屏/后台继续播放并看到媒体通知，以便像播客一样听。
44. 作为听众，我想下次打开时回到上次播放位置，以便续听。
45. 作为听众，我想在 Continue 里看到最近在听/在读的 Item 并一键继续（P1），以便快速回到未完成内容。
46. 作为听众，我想让 Consumption State 自动从未开始变成进行中/完成，以便不用手动维护状态。
47. 作为听众，我想手动标记完成/未完成，以便纠正自动判断。
48. 作为听众，我想在 Library/Search/详情之间切换时播放器不被销毁，以便音频不中断。
49. 作为听众，我想在播放时看到 transcript 分段和时间戳，以便需要时读文字。
50. 作为听众，我想在 transcript 页面内搜索关键词并高亮，以便快速找到一段话。
51. 作为听众，我想音频支持 Range 请求和 ETag，以便拖动进度和续播更快。
52. 作为手机用户，我想在手机布局下完成播放、搜索和入库，以便不需要桌面。

### 读

53. 作为读者，我想用薄阅读器翻章、读正文，以便不离开库就能读 EPUB。
54. 作为读者，我想下次打开时回到上次阅读的章节/位置（P1），以便续读。
55. 作为读者，我想从搜索结果直接打开书的匹配段落（P1），以便定位到相关内容。
56. 作为读者，我想在 Item 详情看到来源 URL，以便追溯书的来源。
57. 作为读者，我想在 Continue 里看到最近在读的书（P1），以便一键续读。
58. 作为手机用户，我想薄阅读器在窄屏上可读，以便手机上也能看书。

### 检索

59. 作为内容收藏者，我想用统一搜索框搜标题、摘要、transcript、书文本和 Tag，以便一个入口找全部内容。
60. 作为中文用户，我想让“记忆”“智能”这类两字中文词必须命中中文文本，以便关键词搜索可靠。
61. 作为内容收藏者，我想让英文短内容也能被转写并命中关键词，以便中英混合库可用。
62. 作为内容收藏者，我想让搜索结果按 Item 聚合并显示匹配段落，以便看出哪些内容提到它。
63. 作为内容收藏者，我想在结果中看到来源、类型、作者和日期，以便判断是否相关。
64. 作为内容收藏者，我想按类型、Consumption State、Tag、来源组合过滤，以便缩小范围。
65. 作为内容收藏者，我想点击结果打开 Item 并定位到匹配段落（P1），以便不用手动找。
66. 作为内容收藏者，我想在千条级 Library 上搜索 <1 秒，以便搜索不打断阅读。
67. 作为内容收藏者，我想从内容包重建搜索索引，以便数据库损坏或迁移后恢复。
68. 作为内容收藏者，我想现在只做关键词检索、不做语义检索，以便先验证核心搜索是否够用。

### 浏览与管理

69. 作为内容收藏者，我想在 Library 看到全部 Item，并按最近添加/最近消费排序，以便浏览。
70. 作为内容收藏者，我想有 Library + Search + Add 三个核心入口，Continue 在 P1 补上，以便导航简单。
71. 作为内容收藏者，我想用 Inbox 过滤“处理中/失败”并看到状态徽标，以便知道哪些还没准备好。
72. 作为内容收藏者，我想修改 Item 标题和作者，并让 Library/搜索/详情同步，以便修正元数据。
73. 作为内容收藏者，我想在 Item 上增删 Tag（P1），并让搜索/过滤立即生效，以便手动修正分类。
74. 作为内容收藏者，我想删除 Item 时只删派生文件、索引和库记录，不删我的原始文件，以便安全清理。
75. 作为内容收藏者，我想查看 Item 的 Processing Run 历史/失败原因，以便管理异常。
76. 作为内容收藏者，我想把 Library 或 Item 子集导出成 zip（P1），包含内容包和 Markdown 索引，以便迁移/备份。
77. 作为内容收藏者，我想导出的视频 Item 只含 source.json + 音频，不含视频文件，以便符合“视频不落盘”。
78. 作为内容收藏者，我想让库完全在本地，MVP 不做云同步，以便先验证本地体验。

### 安全、运维与 Q10

79. 作为 Host 所有者，我想默认只让本机/Tailscale 访问，未认证不能操作，以便不把库暴露到公网。
80. 作为 Host 所有者，我想让 URL 校验阻止内网/元数据地址，并限制上传类型/大小，以便 Host 不是开放下载器。
81. 作为 Host 所有者，我想让媒体文件只能通过库内 artifact 路径访问，防止路径穿越，以便不能读任意文件。
82. 作为 Host 所有者，我想让 EPUB 章节 HTML 被白名单净化、CSP 禁止远程脚本，以便恶意书不能执行脚本。
83. 作为 Host 所有者，我想让密钥/密码哈希/session secret 不出现在日志里，以便降低泄露风险。
84. 作为手机听众，我想参加一周的 Q10 手机播放 spike，验证连续播放、后台/锁屏、倍速、续听和媒体通知，以便决定手机浏览器是否能作为“听”的验收设备。
85. 作为手机用户，我想在 Q10 通过时用手机浏览器完成收藏链接、查看状态、播放、读 transcript、搜索和看来源 URL，以便手机成为主要消费端。
86. 作为手机用户，我想在 HTTPS 下可选安装 PWA，以便像应用一样打开；MVP 不承诺离线内容。
87. 作为 Host 所有者，我想在 Q10 失败时把消费收缩到桌面，并保留 Host Console 的入库/管理/搜索，以便 MVP 仍可验证。
88. 作为 Host 所有者，我想在 HTMX 导致音频中断时只替换 Consumer Web Shell 的表现层为 React，而 API/数据模型不变，以便保留可逆性。
89. 作为未来 Android 开发者，我想复用同一套 JSON API/OpenAPI 和 artifact 元数据，以便客户端不需要另建库。
90. 作为未来 Android 用户，我想让音频/文件带 sha256/size/mime 和 ETag/Range 语义，以便 V1 可以做 manifest + 可续传下载；MVP 不实现同步。

## Implementation Decisions

### 范围与架构

- MVP 只实现需求文档 8.1 的全部 P0 + 明确列出的 P1 短名单；P2/P3 不进入本 spec。
- 单 Host、单用户、Mac（M1 Pro）本地运行；Host Console 与 Consumer Web Shell 是同一个 FastAPI 应用的两组 HTML 路由，另有一套 JSON API 供未来 Android 复用。
- Python 3.12 + FastAPI/Uvicorn + Jinja2/HTMX + SQLite（WAL）+ SQLAlchemy 2 + Alembic；不引入 Redis、Celery、Postgres、Meilisearch、Node 构建链或 Docker。
- API 与 worker 是两个原生进程，通过 SQLite 作业表协作；worker 默认并发 1，处理失败不影响 API/播放。
- 技术细节和依赖以 [技术选型](../../docs/ideas/trove-tech-selection.md) 与 [ADR-0001](../../docs/adr/0001-python-monolith-sqlite-worker.md) 至 [ADR-0008](../../docs/adr/0008-content-package-as-source-of-truth.md) 为准。

### 领域模块与端口

- **Library**：Item/Source/Library 的 CRUD、来源元数据、去重、标题/作者编辑、删除、导出清单。
- **Intake**：URL 规范化与平台白名单、上传、播客 feed 预览、EPUB/本地文件入口；负责在写入前做大小/类型/安全校验。
- **Processing**：Processing Run/Processing State 状态机、队列领取、重试/续跑/取消、启动回收、阶段日志、失败分类。
- **Media**：ffprobe/ffmpeg 抽音频/转码、artifact 路径、媒体响应所需的时长/MIME/sha256。
- **Transcription**：ASR 端口与分段 transcript；语言检测结果和模型版本随结果保存。
- **Books**：EPUB 解析、DRM/固定版式检查、章节/段落、白名单 HTML。
- **Organization**：DeepSeek 客户端、分块 map-reduce、Tag 归一化、token/成本记录、限额。
- **Search**：CJK 归一化/查询构造、FTS 索引行、bm25/分组、索引重建与评估。
- **Consumption**：播放/阅读位置、Consumption State、Continue 查询。
- **Auth**：单用户密码、会话、登录限速。
- **Web**：HTML 路由/模板/HTMX、持久播放器、薄阅读器、Add/Library/Search 页面。
- **API**：JSON 路由、OpenAPI、错误形状、Range/ETag。
- **Worker**：轮询/领取/执行/心跳/取消；外部工具和 API 通过端口调用。
- **Adapters**：yt-dlp、FFmpeg、mlx-whisper、DeepSeek、播客 HTTP、EPUB/文件系统。

端口（测试时在组合根替换为 fake）：`Downloader`、`FeedClient`、`AudioExtractor`、`Transcriber`、`Organizer`、`BookExtractor`、`SearchIndex`、`RunQueue`、`MediaStore`。不引入 DI 框架；手工组装，依赖从外向内。

### 数据模型

| 实体 | 关键字段 | 不变量 |
|---|---|---|
| Item | id、source_key（唯一）、source_type、platform、source_url_raw、source_url_canonical、source_path、title、author、published_at、fetched_at、language、duration_sec、summary、consumption_state、audio_position_sec、book_locator、created_at、updated_at | 来源元数据必须保留；Consumption State 与 Processing State 独立；时间存 UTC 毫秒 |
| Processing Run | id、item_id、state、current_stage、error_code、error_message、cancel_requested_at、heartbeat_at、created_at、started_at、finished_at | 一个 Item 一个当前 Run；取消/失败可重试；阶段级断点 |
| Run Step | run_id、stage、state、attempt、error_code、error_message、started_at、finished_at | 已完成阶段不重做；attempt 可追溯 |
| Artifact | item_id、kind、path、sha256、size、mime、duration_sec | 文件不可变；删除 Item 只删派生文件；为 V1 同步预留元数据 |
| Transcript Segment | item_id、seq、start_ms、end_ms、text | 分段有序；不做词级时间戳 |
| Book Chapter | item_id、chapter_index、title、html、text | 章节顺序正确；HTML 已净化 |
| Book Paragraph | item_id、chapter_index、paragraph_index、text | 用于搜索定位 |
| Tag | id、name、normalized_name（唯一） | 归一化后唯一；可手动编辑 |
| Item Tag | item_id、tag_id、source（ai/user） | 同一 Item/Tag 不重复 |
| AI Result | item_id、run_id、summary、model、prompt_version、input_tokens、output_tokens、cost_usd、created_at | 保留历史；当前摘要/标签可重跑 |
| Search FTS | norm_text、text UNINDEXED、item_id、doc_kind、ref | 派生索引；可重建；一行一个可定位单元 |

- `source_key`：URL 用规范化 URL；本地文件用 SHA-256；播客单集用 `feed_url#episode_guid`（GUID 缺失时用 enclosure URL）。
- V1 的 `version`/`deleted_at`、manifest/cursor、tombstone 不在 MVP 建表；MVP 只保证 artifact 元数据和 HTTP Range/ETag 语义。
- FTS5 表由迁移创建；应用负责写入/删除/重建；不依赖外部搜索服务。

### 内容包

- 每个 Item 一个普通文件夹：`source.json`、音频、`transcript.json`、`book.epub`/`book.json`、`ai.json`、可选封面。
- 内容包是可移植事实源；SQLite 是元数据、Processing State、消费进度和搜索索引。索引可从内容包重建。
- 文件写入先临时文件再原子 rename；数据库事务在文件落盘后提交；崩溃清理半成品。
- 删除 Item 只删库内派生文件和索引，不删除用户原始路径；视频只存 `source.json` + 音频。
- Export（P1）为 zip：内容包 + `index.md`；视频 Item 只含 `source.json` + 音频。

### 处理管线

- 视频/播客：`queued → downloading → extracting_audio → transcribing → organizing → indexing → completed`。
- 本地音频/视频：`queued → extracting_audio → transcribing → organizing → indexing → completed`。
- EPUB：`queued → extracting_text → organizing → indexing → completed`。
- 任一步失败 → `failed`，记录稳定错误码和原因；重试只重置失败/取消阶段及其后续阶段，已完成阶段跳过。
- 取消排队：直接把 Run 置为 `cancelled`；取消运行中：写 `cancel_requested_at`，worker 在阶段边界终止子进程组并清理当前阶段半成品。
- Worker 启动时把所有 `running` Run 回收为 `queued` 并清理当前阶段临时文件；单 worker 前提下这是安全的。
- 外部工具：yt-dlp 只允许 B 站/YouTube 单条视频，拒绝 playlist/多 P；FFmpeg 输出 64kbps 单声道 AAC 供播放，视频不落盘；mlx-whisper `large-v3-turbo` 子进程转写，关闭词级时间戳；DeepSeek 走 JSON 模式、分块 map-reduce；EPUB 用 `zipfile + lxml + nh3` 直接解析。
- LLM 限额：`chunk_chars=20000`、`max_calls_per_item=16`、`max_output_tokens_per_call=1024`、`max_input_tokens_per_item=200000`；超限报 `llm.limit_exceeded`，不静默截断；实际 token/估算成本只记录。
- 失败原因分类：网络、需要登录、地区限制、DRM、不支持、解析、ASR、LLM、存储、内部错误；UI 映射中文提示。

### 搜索

- FTS5 使用 `porter unicode61`；文档/查询先做 CJK bigram 归一化：`人工智能` → `人工 工智 智能`；中文查询用 bigram 短语匹配，单字退化为 `LIKE`。
- 一行一个可定位单元：title、summary、每个 Tag、每段 transcript、书的每个段落；`text` 保留原文用于 snippet。
- 查询只拼接 token，不直接拼 FTS5 语法；查询长度上限 200 字符。
- 排序用 bm25 + doc kind 权重（title/summary/tag 加权）；结果按 Item 聚合，每个 Item 取最佳分数和最多 3 条证据。
- `ref` 定位：transcript 的 seq/start_ms；book 的 chapter/paragraph；点击结果滚动到锚点，不做音频跳转/同步滚动。
- `trove index rebuild` 从内容包和数据库重建索引；搜索评估用 50+ 条真实内容、30 个预注册 query，输出 recall@10、首个相关排名、分类型结果和漏召回。
- 不做向量/语义检索；FR-53 留到 P2。

### Web Shell

- HTML 路由：登录、Library、Search、Add、Item 详情、Item 听、Item 读；Inbox 是 Library 的过滤视图；Continue 是 P1 的 Library 入口。
- **手机消费壳结构（原型已选定 C + B）**：默认 Library 是 C 的队列式列表；行内播放按钮用于快速播放并在当前列表就地展开；点击 Item 主体进入 B 的 Now Playing 全屏视图。B 顶部返回 C 列表；B 的 transcript 默认折叠，点击就地展开/收起；Search/Add 通过 C 底部导航或 B 抽屉进入。搜索结果在 C 中打开 B；不做 Up Next/队列页。
- 同一个 FastAPI 应用提供 HTML 和 JSON API；HTML 路由调用 application service，不通过 HTTP 调自己的 API。
- HTMX 只替换 `#main`，播放器在持久区域；链接用 `hx-target="#main"`/`hx-select="#main"`/`hx-push-url`；直接打开 URL 时渲染完整布局。
- 播放器：原生 `<audio>` + Media Session；播放/暂停/进度/倍速；每 5 秒 + 暂停/结束/pagehide 写回；打开时恢复位置。
- Transcript：服务端渲染分段；文内搜索/高亮用少量原生 JS；不做点击跳转。
- EPUB 阅读：服务端渲染净化后的章节 HTML；章节导航；滚动进度节流写回；MVP 不渲染图片/脚注/书内搜索。
- 搜索：GET 表单 + 服务端结果聚合；筛选是链接；不做前端状态机。
- PWA：manifest + 最小 service worker，只缓存 app shell，不缓存 API/媒体；不承诺离线。
- Q10：手机浏览器连续播放、后台/锁屏、倍速、续听、媒体通知；失败则收缩到桌面，或仅替换 Consumer Shell 为 React。
- 不引入 React/Node 构建链；如果 Q10/HTMX 音频连续性失败，只替换表现层，JSON API/数据模型不变。

### JSON API

| 方法 | 路径 | 用途 |
|---|---|---|
| POST | `/api/items` | 添加 URL/本地路径/播客单集；已存在返回 200 + `deduplicated: true` |
| POST | `/api/uploads` | 流式上传本地文件，返回 upload id |
| POST | `/api/feeds/preview` | 播客 feed URL → 最近单集列表 |
| GET | `/api/items` | Library 列表；类型/Consumption State/Tag/来源过滤与排序 |
| GET | `/api/items/{id}` | 详情、来源、Run 状态、Tag、消费进度 |
| PATCH | `/api/items/{id}` | 修改标题/作者/Tag |
| DELETE | `/api/items/{id}` | 删除派生文件和索引，不动原始文件 |
| GET | `/api/items/{id}/audio` | Range/ETag 音频流 |
| GET | `/api/items/{id}/transcript` | 分段文本 |
| GET | `/api/items/{id}/book/chapters/{n}` | 薄阅读器章节 HTML |
| PUT | `/api/items/{id}/progress` | 播放/阅读位置 + Consumption State |
| POST | `/api/items/{id}/retry` | 重试失败 Run，从断点继续 |
| POST | `/api/items/{id}/reprocess` | 从指定阶段重跑（如更换 prompt 后整理） |
| GET | `/api/runs/{id}` | Run/阶段状态、失败原因、日志 tail |
| POST | `/api/runs/{id}/cancel` | 取消排队/运行中的 Processing Run（best-effort） |
| GET | `/api/search` | 统一搜索；按 Item 聚合 + 匹配证据 |
| GET | `/api/tags` | Tag 列表/计数 |
| GET | `/api/export` | P1：导出 zip |
| POST | `/api/auth/login`、`/api/auth/logout` | 单用户会话 |
| GET | `/api/health` | 主机/DB/worker 健康检查 |

- FastAPI 自动生成 OpenAPI（`/api/openapi.json`）；MVP 不做客户端代码生成；Android 可直接复用会话 Cookie，V1 需要长期设备 token 时再加 bearer，不改变资源和路径形状。
- 错误统一 `{code, message, details?}`；失败原因用稳定 code（如 `download.login_required`、`epub.drm`、`asr.failed`、`llm.limit_exceeded`）。
- 音频/文件响应带 `ETag`（sha256）、`Accept-Ranges: bytes`，使用 Starlette `FileResponse` 的 Range 支持；Starlette ≥0.49.1。
- API 与 HTML 共用 application service；API 是未来 Android 的契约。

### 安全

- 单用户认证：Argon2id 密码哈希；`trove auth set-password` 写入配置（0600）；登录成功设置 HttpOnly、SameSite=Lax 的签名 Cookie（HTTPS 时 Secure，30 天）；失败按 IP 限速。
- CSRF：写操作只用 POST/PATCH/DELETE；SameSite=Lax + 校验 Origin/Sec-Fetch-Site；不使用 GET 改状态。
- 绑定：默认 127.0.0.1；手机通过 Tailscale Serve；`trove serve --lan` 才绑定 0.0.0.0，仍强制认证并提示仅受信任局域网。
- SSRF：播客 feed/附件走 `SafeHttpClient`：只允许 http/https；每次重定向重新校验；拒绝私网/回环/链路本地/元数据/CGNAT 地址；限制重定向、超时、feed 10MB、媒体 1GB；视频 URL 只允许平台白名单，不做通用下载代理。
- 上传：流式落临时文件，边写边算 SHA-256；限制视频 4GB/音频 500MB/EPUB 100MB（可配）；扩展名/MIME 白名单 + ffprobe/EPUB 结构校验；失败清理。
- 文件服务：只返回数据库中的 artifact 路径；`ETag=sha256`；`X-Content-Type-Options: nosniff`；`Cache-Control: private`；防路径穿越。
- HTML：Jinja2 自动转义；EPUB 章节 `nh3` 白名单净化；CSP `default-src 'self'`，禁止远程脚本/图片；不把用户文本标记为 safe。
- 密钥：`DEEPSEEK_API_KEY` 放 `~/Trove/.env`（0600）；session secret 随机生成；日志不打印 Cookie/Key。
- 不暴露开放下载器：没有任意 URL 代理接口；播客只抓 feed 里的 enclosure，类型/大小受限。

### 部署与运维

- 数据目录 `~/Trove/`（`TROVE_HOME` 可覆盖），权限 0700：config、`.env`、SQLite、library、cache、logs。
- 两个 launchd LaunchAgent：API/HTML 与 worker；`RunAtLoad` + `KeepAlive`；升级时先迁移数据库再重启。
- `uv` 管理 Python 3.12 和锁文件；FFmpeg/ffprobe、yt-dlp 记录版本；模型首次 `trove setup` 预下载。
- 不使用 Docker：MLX/Metal 在 macOS 容器不可用；本地视频路径和 launchd 更适合原生。
- 休眠/重启：队列和阶段状态在 SQLite；worker 启动回收 stale Run；可选 `caffeinate -i -w <pid>` 防止处理时空闲睡眠。
- 备份/导出：P1 导出 zip；日常可用 SQLite backup 或文件快照；不做云同步。
- 日志：`logs/trove.log` 轮转（10MB × 5）；每个 Run 单独日志，UI 只读 tail。
- HTTPS：桌面本机 `http://127.0.0.1`（secure context 例外）；手机用 Tailscale Serve；无 Tailscale 时 Caddy 内部 CA；直连 LAN HTTP 仅受信任局域网且不承诺 Media Session/PWA。

### P1 短名单

MVP 只包含这些 P1：

- transcript 阅读（FR-37）。
- 阅读进度（FR-39）。
- Continue（FR-36）。
- 基础过滤：类型/Consumption State/Tag/来源（FR-50）。
- Item 上 Tag 编辑（FR-28）。
- 搜索结果打开到匹配段落（FR-52）。
- 导出 zip（FR-64）。
- 取消运行中 Processing Run best-effort（FR-11）。
- PWA 安装（FR-86，可选，依赖 HTTPS，不进验收）。
- Consumer Web Shell（FR-87）：播放/transcript/Continue/搜索定位；Q10 通过才作为手机听验收。

### 限额与性能

- ASR 组件目标 ≤20 分钟/1 小时；端到端 1 小时视频 <30 分钟。
- 千条级搜索 p95 <1 秒（目标 <100ms）。
- 100 小时音频 + 100 本书 <5GB；音频 64kbps 单声道；本地无损音频按 FR-15 保留原件可能导致超预算，按真实库重算。
- 单 worker、单 API 进程；MVP 不同时处理多条；后续可加 worker，领取逻辑不变。
- LLM：`chunk_chars=20000`、`max_calls_per_item=16`、`max_output_tokens_per_call=1024`、`max_input_tokens_per_item=200000`；不按金额止损，记录实际 token/估算成本。

## Testing Decisions

### 主测试缝

采用 **Host HTTP/HTML 缝**（已与用户确认）：启动真实的 Host（API + worker）和临时 `TROVE_HOME`，使用真实 SQLite、迁移、文件系统、模板、FTS5、EPUB 解析和 FFmpeg；通过 HTTP/HTML 像用户一样驱动。外部网络/重工具在组合根替换：

- `Downloader`、`FeedClient`、`Transcriber`、`Organizer` 用 fake，返回 fixture 结果；不访问 YouTube/B 站/播客/DeepSeek。
- `AudioExtractor` 用真实 FFmpeg + 1–2 秒小音频 fixture；`BookExtractor` 用真实解析 + golden EPUB。
- `RunQueue`/worker 真实运行；测试轮询 Run 状态直到完成/失败，不用固定 sleep。
- Playwright 复用同一个 Host，只在浏览器特定行为上使用；不另建产品缝。
- CJK tokenizer/query builder、URL 规范化/source_key、Processing State 转换、Tag 归一化用纯函数单测；它们编码微妙规则，值得独立覆盖。

### 好测试的标准

- 只测外部行为：HTTP 状态/JSON、HTML 中的可见内容、内容包文件、搜索/过滤结果、进度持久化、Run 状态；不测内部调用顺序、私有方法或 SQL 细节。
- 可重复、确定性：临时目录、固定时钟/固定 fixture、fake 外部适配器；不使用真实网络；需要等待 worker 时用有超时的轮询。
- 数据契约可以断言文件存在/sha256/zip 内容，因为这是用户可见的 Export/Content Package 行为。
- 失败路径和边界与 happy path 同样重要：未认证、重复添加、私网 URL、超限上传、DRM EPUB、取消/重启、LLM 超限、搜索无结果。

### 测试模块与范围

| 区域 | 场景 | 断言 |
|---|---|---|
| 认证 | 未登录访问 API/HTML；登录/登出；错误密码限速 | 401/跳转登录；成功后有会话；错误不泄露细节 |
| 入库 | B 站/YouTube 单视频；playlist/多 P 拒绝；本地音频/视频；EPUB；播客 feed 预览/选集 | Item/Processing Run 创建；source_key 去重；来源元数据；拒绝原因 |
| 处理 | 状态推进；失败；重试续跑；取消排队/运行中；worker 重启回收 | 阶段不重复；已完成 artifact 保留；失败不删原文件；Run 终态正确 |
| 听 | 音频 Range/ETag；进度保存/恢复；Consumption State；Continue | 206/ETag；位置持久化；状态自动/手动更新；列表正确 |
| 读 | EPUB 章节/段落；DRM/固定版式拒绝；阅读进度 | 章节顺序/文本；错误码；位置恢复 |
| 搜索 | 两字中文、英文、标题/摘要/transcript/书/Tag；过滤；按 Item 聚合；定位段落；重建 | 命中/不命中；证据/排序；过滤器组合；锚点 ref |
| 浏览/管理 | Library 排序；Inbox 过滤；编辑标题/作者；Tag 编辑；删除 | 列表/详情同步；派生文件删除；原始文件保留 |
| 导出 | zip 内容；Markdown 索引；视频只含 source+audio | 文件清单/内容正确；不含视频 |
| 安全 | 私网/元数据 URL；超大上传；路径穿越；恶意 EPUB HTML；未认证 | 拒绝/净化；不泄露文件；CSP/转义 |
| Q10/浏览器 | C 列表 → B 播放页 → 返回 C；B transcript 展开/收起；HTMX 导航时播放不中断；Media Session 元数据；文内搜索；EPUB 翻章；手机布局 | 返回列表后播放/进度保持；展开/收起不丢状态；元数据/进度正确；布局可用 |

### 纯函数与 fixture

- CJK 归一化/查询：`人工智能` → `人工 工智 智能`；两字词单 token；单字回退；英文 porter 词干。
- URL 规范化/dedupe：YouTube `youtu.be`/watch、B 站 BV/av、跟踪参数、playlist/多 P 拒绝。
- Processing State：允许的转换、retry 从失败阶段、cancel 终态、启动回收。
- Tag 归一化：大小写/单复数/已有 Tag 复用/超长与空值。
- Golden fixtures：EPUB2、EPUB3、短公开领域音频、播客 RSS XML、transcript JSON；不使用凭空捏造的占位数据。

### 手动验收

这些不替代自动测试，按需求 9.x 执行并记录：

- `trove bench asr`：1 小时真实中文音频 ≤20 分钟；完整管线 1 小时视频 <30 分钟。
- 来源：10 B 站 + 10 YouTube + 10 播客 + 10 EPUB + 10 本地文件；B 站/YouTube/播客 8/10，EPUB/本地 10/10。
- 20 条真实内容；Tag 可用率 ≥70%；摘要事实错误少。
- 50+ 条内容、30 个预注册 query；recall@10、首个相关排名、漏召回记录。
- 20 条真实内容后的存储外推：100h + 100 本 <5GB。
- Q10：一周手机播放 spike（HTTPS）；连续播放、后台/锁屏、倍速、续听、媒体通知；记录中断/失败。
- 重启/取消/续跑；未认证/私网 URL/超大上传/恶意 EPUB 的安全检查。
- `python3 scripts/check-docs.py` 通过；后续实现增加 `scripts/check.sh` 汇总 ruff/mypy/pytest。

### Prior art

仓库目前只有文档检查脚本，没有应用测试或测试框架；本 spec 建立第一个产品级测试缝。测试风格遵循仓库现有约定：Python 标准库优先、零多余依赖、真实数据优先于 mock 数据。Playwright 仅在浏览器特定行为上引入；纯函数用 pytest 表驱动。

## Out of Scope

- V1 Android 客户端（native 或 PWA）、离线播放/阅读/搜索、app-managed sync、manifest/cursor、tombstone、device_id、last-write-wins。
- 云端处理、云存储、云同步、公网暴露、多用户、账号体系。
- PDF、TTS、标注/标注搜索、语义/向量检索、Topic 层、实体抽取、全局 Tag 重命名/合并。
- 视频播放、时间戳跳转、同步滚动、点击 transcript 跳音频、Up Next、睡眠定时。
- 完整 EPUB 渲染（图片版式、脚注弹窗、书内搜索）、独立 Markdown 导出、备份/恢复 UI。
- 每日 feed/streak、主题冲刺、社交、推荐、iOS、桌面 App（Tauri/Electron）。
- 批量导入、RSS 自动轮询/订阅、开放下载代理、DRM 绕过。
- 大众市场/合规/单位经济/每用户成本模型；MVP 只记录单条 token/成本。
- 任何 P2/P3 需求，除非明确列入本 spec 的 P1 短名单。

## Further Notes

- **Q10 定义**：手机浏览器能否承担主要听设备（连续播放、后台/锁屏、倍速、进度续听、媒体通知）？见 [trove-requirements.md 的 Q10 门控](../../docs/ideas/trove-requirements.md#q10)。Host Console 不依赖 Q10；Consumer Web Shell 的消费验收依赖 Q10。
- **手机壳原型结论**：已选定 C（队列列表）+ B（Now Playing）的组合；B 的 transcript 就地展开/收起。原型在 `.scratch/trove-mvp/prototype/mobile-shell.html`，是 throwaway artifact，不进入产品代码；Q10 仍需真机 spike。
- **数据隐私**：DeepSeek 会收到分块后的转写/书文本；Add 页必须提示；MVP 不做 per-item 开关；测试可用 `TROVE_LLM_ENABLED=false` 跳过。
- **许可证**：核心依赖保持 MIT/BSD/Apache；避开 EbookLib（AGPL）和 Audiobookshelf（GPL）；完整清单见 [技术选型第 11 节](../../docs/ideas/trove-tech-selection.md)。
- **技术决策**：实现时以 [ADR-0001](../../docs/adr/0001-python-monolith-sqlite-worker.md) 至 [ADR-0008](../../docs/adr/0008-content-package-as-source-of-truth.md) 为准；如果实现中发现某个 ADR 的前提不成立，先更新 ADR，再改代码。
- **验收边界**：MVP 的“完成”不是 Q10 通过；Host Console 的入库/管理/搜索可以先完成。Q10 失败时按需求收缩消费端，不降低 Host Console 的范围。
- **实施顺序建议**：M0 主机骨架/认证/队列/下载/播放；M1 转写/搜索/transcript；M2 EPUB/DeepSeek/Tag/Continue/导出；M3 P1 与 Q10。每个阶段应独立可用，不把全部功能压到最后一次交付。
- **Issue 拆分**：后续按 `.scratch/trove-mvp/issues/NN-<slug>.md` 拆分；本 spec 不替代 issue 级验收。
