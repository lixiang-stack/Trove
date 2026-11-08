# 拾藏 / Trove — MVP 技术选型

> 状态：v0.2（关键选择已确认）  
> 日期：2026-11-08  
> 依据：[trove-requirements.md](trove-requirements.md)（最终需求）与 [GLOSSARY.md](../../GLOSSARY.md)  
> 范围：MVP（Mac 主机 + Host Console Core + Consumer Web Shell）；V1 Android、云端、同步只做接口预留，不实现。  
> **Q10**：手机浏览器能否承担主要听设备（连续播放、后台/锁屏、倍速、进度续听、媒体通知）？定义见 [trove-requirements.md 的 Q10 门控](trove-requirements.md#q10)。

## 0. 结论

MVP 采用 **Python 单体 + SQLite + 本地文件库 + 独立 worker**：

- **Host Console 与 Consumer Web Shell 是同一个 FastAPI 应用的两组路由**，服务端渲染 + HTMX，不引入 React/Node 构建链；主机运行时只有 Python，浏览器只加载少量原生 ES modules。
- **处理在独立 worker 进程**，队列持久化在 SQLite，不引入 Redis/Celery。
- **搜索用 SQLite FTS5 + 中文 bigram 归一化**，保证“两字中文词必须命中”。
- **转写用 Apple Silicon 原生 mlx-whisper**，整理用 DeepSeek API；两者都放在可替换的适配器后面。
- **Mac 原生运行 + launchd**，手机通过 Tailscale Serve（或 Caddy）获得 HTTPS；不使用 Docker。

### 0.1 决策表

| 层 | 选择 | 关键理由 |
|---|---|---|
| 主机运行时 | Python 3.12 + uv | ASR/EPUB/yt-dlp/LLM 生态最全；单一运行时，减少跨语言桥 |
| Web/API | FastAPI + Uvicorn + Jinja2 | OpenAPI 给 Android 复用；服务端渲染足够 |
| 交互 | HTMX 2 + 原生 ES modules + Pico CSS | 无 Node 构建链；适合可丢弃的验证壳 |
| 数据库 | SQLite（WAL）+ SQLAlchemy 2 + Alembic | 单用户本地；事务、迁移、FTS5 |
| 队列 | SQLite 作业表 + 独立 worker | 持久化、重试、取消；零额外服务 |
| 下载 | yt-dlp + httpx | B 站/YouTube/播客；可做安全校验 |
| 媒体 | ffmpeg / ffprobe | 抽音频、转码、探测 |
| 转写 | mlx-whisper + `whisper-large-v3-turbo` | Apple Silicon 快；中英双语；分段输出 |
| 整理 | DeepSeek `deepseek-flash` | 中文摘要/Tag；OpenAI 兼容；按 token/调用数限额 |
| 搜索 | SQLite FTS5 + 中文 bigram | 两字中文必中；千条级 <1s；可重建 |
| 电子书 | `zipfile` + `lxml` + `nh3` | 避开 AGPL；薄阅读器足够 |
| 认证 | Argon2id + 签名 Cookie | 单用户；无第三方依赖 |
| 部署 | launchd + Tailscale Serve | 原生、HTTPS、局域网/VPN；Caddy 仅作无 Tailscale 备选 |
| 测试 | pytest + Playwright（Python） | 单语言；真实浏览器覆盖音频/阅读 |

> 各组件的 GitHub/源码地址、许可证和备选见第 11 节。

## 1. 约束与决策驱动

| 约束 | 来源 | 对选型的影响 |
|---|---|---|
| Mac（M1 Pro）单机、单用户、本地优先 | NFR-01、NFR-05 | 原生进程优先；SQLite/文件而非云服务 |
| 1 小时音频处理 <30 分钟 | NFR-05 | ASR 必须用 Apple Silicon 加速；模型/参数可换 |
| 千条级搜索 <1 秒 | NFR-05 | 本地 FTS 索引；不引入远程搜索服务 |
| 100 小时音频 + 100 本书 <5GB | NFR-06 | 音频 64kbps 单声道；不存视频 |
| 中文两字词必须命中 | FR-51 | 默认分词器不可用；必须做 CJK bigram |
| Consumer Shell [Q10](trove-requirements.md#q10) 门控、可丢弃 | FR-87 | 不为 Web 壳过度投入；保留升级/替换路径 |
| Android 复用同一套 API/数据 | FR-82、NFR-08 | API 与展示分离；OpenAPI；文件带 sha256 |
| MVP 不做离线 Web、不做云端 | 8.1 | 不缓存内容；不做同步/对象存储 |
| 个人/开源自用，未来可能闭源 | NFR-10 | 优先 MIT/BSD/Apache；避开 AGPL 核心依赖 |

## 2. 总体架构

```
手机/桌面浏览器
    │  HTTPS（Tailscale Serve 或 Caddy）
    ▼
FastAPI 进程
    ├─ HTML 路由（Jinja2 + HTMX）── Host Console / Consumer Shell
    ├─ JSON API（OpenAPI）────────── 未来 Android、脚本
    ├─ 认证/会话
    ├─ SQLite（WAL）─────────────── 元数据、队列、Tag、FTS5
    └─ 本地文件库 ────────────────── source/audio/transcript/book/ai
    ▲
    │ 同一个 SQLite
    │
Worker 进程
    ├─ yt-dlp / ffmpeg / mlx-whisper（子进程，可取消）
    └─ DeepSeek API（httpx/OpenAI SDK）
```

- **两个进程**：API 与 worker 分开，处理崩溃不影响浏览/播放；两者都通过 launchd 常驻。
- **一个数据库**：SQLite WAL，API 读多写少，worker 单写者；`busy_timeout` 处理短锁。
- **一个文件库**：内容包是普通文件；数据库可重建；导出 zip 即迁移/备份。
- **没有额外服务**：不引入 Redis、Meilisearch、Postgres、消息队列；MVP 的单机单用户不值得这些运维成本。

## 3. 技术选型

### 3.1 运行时与 Web 框架

**选择**：Python 3.12（`uv` 管理） + FastAPI + Uvicorn + Pydantic v2 + SQLAlchemy 2.0 + Alembic。

**理由**：

- 转写（mlx-whisper）、下载（yt-dlp）、EPUB、LLM SDK 都在 Python 生态；用 Python 做主运行时可以少一层跨语言桥。
- FastAPI 自动生成 OpenAPI，天然适合 FR-82 的“Android 复用同一套 API”。
- 同步 SQLAlchemy + SQLite 对单用户足够；不需要异步 ORM 的复杂度。
- Alembic 用 SQLite batch mode 处理 `ALTER TABLE`，schema 演进可控。

**放弃**：

- **Node/TypeScript 全栈**：前端更统一，但 ASR/EPUB 生态弱；yt-dlp 本身就是 Python，仍要带一个 Python 子进程。为了一个 Web 壳引入第二运行时，收益不足。
- **Django**：自带 admin/auth 很诱人，但本项目核心是处理管线、搜索和自定义播放/阅读，不是 CRUD；async/子进程/长任务不如 FastAPI 直接。
- **Go/Rust**：性能好，但 ASR/EPUB/LLM 集成和迭代速度不占优；MVP 的瓶颈不在 Web 框架。

### 3.2 前端形态（关键决策）

**选择**：Jinja2 服务端渲染 + HTMX 2 + 原生 ES modules + Pico CSS（本地 vendored，无 CDN、无构建链）。

**理由**：

- Consumer Web Shell 在需求里是 **Q10 gated、预期被 Android 替代的验证壳**；Host Console 是管理界面。两者都不需要 SPA 的复杂度。
- 音频是核心：把 `<audio>` 放在布局的持久区域（`#player`），HTMX 只替换 `#main`；导航时音频元素不被销毁。播放器用原生 Media Session API。
- 搜索、Library、Add、状态轮询都是表单/列表/分页，HTMX 的 `hx-get`/`hx-trigger="every 3s"` 足够。
- 不引入 Node/Vite/React，部署只需 Python + 静态文件；CSP 也更容易收紧（不用 Alpine 的 `eval`）。
- UI 用 Pico 只做 reset/表单基线，视觉层用自定义 CSS 变量和组件样式，避免“默认主题感”。

**关键实现约束**：

- 全局播放器在 `#main` 之外；HTMX 链接使用 `hx-target="#main"`、`hx-select="#main"`、`hx-push-url="true"`。
- 播放器模块：播放/暂停/进度/倍速、Media Session 元数据与动作、进度每 5 秒 + 暂停/结束/pagehide 写回、打开时恢复上次位置。
- transcript 页服务端渲染分段；文内搜索用一个小模块做过滤/高亮（FR-37）。
- EPUB 阅读页服务端渲染已净化的章节 HTML；滚动进度节流写回（FR-39）。
- 全局搜索用 GET 表单 + 服务端结果聚合；筛选是链接，不做前端状态机。
- 上传用 `XMLHttpRequest` 获取进度；其余交互不引入框架。
- PWA 只做 manifest + 最小 service worker（只缓存 app shell，不缓存 API/媒体）；Q10 前可暂缓。

**唯一的接近替代**：React + Vite SPA。若 Q10 手机 spike 发现 HTMX 导航会中断音频，或 Web 壳意外变成长期主入口，则只替换表现层为 React；JSON API 和数据模型不变。这是本方案最主要的可逆决策。

**放弃**：Next.js（无 SSR/SEO 需求，增加服务端复杂度）、Alpine.js（CSP 需要放宽）、Tauri/Electron（需求明确不做桌面 App）。

### 3.3 数据与搜索

**选择**：SQLite + WAL + FTS5；FTS5 使用 `porter unicode61` 分词器，文档/查询先做 **CJK bigram 归一化**。

**核心表**（详见第 4 节）：

- `items`：Item 元数据、来源、消费状态与进度。
- `runs` / `run_steps`：Processing Run 与阶段状态。
- `artifacts`：内容包文件（kind/path/sha256/size/mime）。
- `transcript_segments`：分段文本 + start/end 毫秒。
- `book_chapters` / `book_paragraphs`：章节与段落。
- `tags` / `item_tags`：Tag 与关联。
- `ai_results`：摘要、Tag、模型、prompt 版本、token、成本。
- `search_fts`：全文索引。

**为什么必须自定义 bigram**（SQLite 3.53.4 实测）：

| 分词方式 | 查 `人工智能` | 查 `智能` | 查 `记忆` | 结论 |
|---|---|---|---|---|
| `unicode61` | 0 命中 | 0 命中 | 0 命中 | 连续中文被当成一个 token |
| `trigram` | 1 命中 | 0 命中 | 0 命中 | 只支持 ≥3 字 |
| bigram + `porter unicode61` | 1 命中 | 1 命中 | 1 命中 | 满足两字中文要求 |

**归一化规则**：

1. NFKC、转小写、去 HTML 标签、压缩空白。
2. 中文/日文/韩文连续段：长度 1 保留单字；长度 ≥2 生成重叠 bigram（`人工智能` → `人工 工智 智能`）。
3. 拉丁字母/数字连续段：保留整词（`AI agents` → `ai agents`）。
4. 写入 `search_fts.norm_text`；原始文本放在 `text UNINDEXED`，用于结果摘要。

**查询构造**：

- `人工智能` → 短语查询 `"人工 工智 智能"`，保证是连续子串，不是三个词分散命中。
- `AI 记忆` → `"ai" AND "记忆"`。
- 单个中文字符：退化为 `LIKE '%字%'`（需求只要求两字；单字不建 bigram）。
- 用户输入只作为 token 拼接，绝不直接拼 FTS5 语法；查询长度上限 200 字符。

**索引与结果**：

- 一行一个可定位单元：transcript 分段、book 段落、title、summary、tag。
- `ref` 记录定位：transcript 的 `seq/start_ms`，book 的 `chapter/paragraph`；结果点击后滚动到对应锚点（不做音频跳转，FR-46）。
- 排序：`bm25` + kind 权重（title/summary/tag 加权）；按 Item 聚合，每个 Item 取最佳分数和最多 3 条证据。
- 索引可重建：`trove index rebuild` 从内容包和数据库重建，不依赖外部服务。

**搜索评估**：内置 `trove eval search`，输入 50+ 条真实内容与 30 个预注册 query，输出 recall@10、首个相关结果排名、按类型分列和漏召回列表，对应 9.2 的验收。

**放弃**：

- Meilisearch/Typesense/Elasticsearch：能力过剩，且多一个常驻服务、索引同步和备份问题；千条级 SQLite 足够。
- 只靠 jieba 分词：词典外的新词/人名两字词可能切不出来；bigram 是确定性兜底。
- 只靠 trigram：两字中文直接不命中，正是 FR-51 的红线。
- 现在做向量/语义检索：FR-53 是 P2；先证明关键词检索达标。

### 3.4 处理管线

**状态机**（与 GLOSSARY 的 Processing State 对齐）：

```
queued
  ├─(URL/播客)→ downloading → extracting_audio → transcribing → organizing → indexing → completed
  ├─(本地视频/音频)→ extracting_audio → transcribing → organizing → indexing → completed
  └─(EPUB)→ extracting_text → organizing → indexing → completed
                                   │
                                   └─ 任一步失败 → failed（记录原因，可 retry）
```

- **一个 Item 一个当前 Run**；`run_steps` 记录每个阶段的 attempt/状态/错误。retry 只重置失败/取消的阶段，已完成阶段不重做（FR-09）。
- **幂等**：所有阶段输出先写临时文件，再原子 rename；数据库事务在文件落盘后提交。崩溃后清理半成品，重跑当前阶段。
- **取消排队**：直接把 `runs.state` 置为 `cancelled`，worker 不会领取。
- **取消运行中**：写 `cancel_requested_at`；worker 在阶段边界检查，并 `terminate` 子进程组（yt-dlp/ffmpeg/ASR），清理当前阶段半成品；已完成的阶段保留。best-effort，符合 FR-11。
- **重启恢复**：worker 启动时把所有 `state=running` 的 Run 回收为 `queued`（单 worker，启动时不可能有其他 worker 在跑），清理当前阶段的临时文件；队列不丢、不重复处理（FR-83）。
- **队列实现**：`runs` 表 + 单 worker 轮询；用 `UPDATE ... WHERE state='queued' RETURNING id` 原子领取。不引入 broker。
- **失败不阻塞消费**：下载/抽音频/转写已完成时，即使整理或索引失败，已有音频/文本仍可播放/阅读；UI 显示失败阶段和重试入口，Run 状态保持 `failed`。

**各阶段工具**：

| 阶段 | 工具 | 输出 | 说明 |
|---|---|---|---|
| 下载 | yt-dlp（子进程） | 临时音轨 | 只允许 B 站/YouTube 单条视频；拒绝 playlist/多 P |
| 播客 | httpx + feedparser | 单集音频 | 预览最近 50 集；不订阅、不轮询 |
| 抽音频 | ffmpeg/ffprobe | `audio.m4a` | 视频/播客转 64kbps 单声道 AAC；本地视频不复制原文件 |
| 转写 | mlx-whisper（子进程） | `transcript.json` | `large-v3-turbo`；分段 start/end；不做词级时间戳 |
| 整理 | DeepSeek（httpx/OpenAI SDK） | `ai.json` | 摘要 + 3–5 个 Tag；分块 map-reduce；记录 token/成本 |
| 电子书 | zipfile + lxml + nh3 | `book.epub` + `book.json` | 只支持 DRM-free、可重排 EPUB 2/3；薄阅读器 |
| 索引 | FTS5 | `search_fts` | 可重建；写 Item/分段/段落 |

**ASR 细节**：

- `mlx-whisper` 0.4.x + `mlx-community/whisper-large-v3-turbo`（约 1.6GB）；首次 `trove setup` 预下载，避免卡在单条任务里。
- 子进程运行，输出 `transcript.json`；主 worker 只负责超时、取消、心跳。转写阶段没有百分比进度，UI 显示阶段 + 已用时间；阶段级恢复符合 FR-09。
- 参数：`language=auto`（中文优先）、`task=transcribe`、`word_timestamps=False`、`condition_on_previous_text=False`，并设置 `no_speech_threshold`/`logprob_threshold`/`compression_ratio_threshold` 抑制静音幻觉。
- 若实测中文质量或速度不达标：先换 `mlx-community/whisper-large-v3`（更慢、更准），再评估 SenseVoiceSmall（中文优先、CPU/ONNX）或 whisper.cpp（内置 VAD）。适配器边界不变。

**LLM 细节**：

- 默认 `deepseek-flash`（当前 DeepSeek API 的 Flash 档），OpenAI 兼容接口；`response_format={"type":"json_object"}`，prompt 中明确要求 JSON。
- 短文本单次调用；长文本按约 20k 字符分块，先产出分块摘要/候选 Tag，再 reduce 成 1–2 句摘要 + 3–5 个 Tag（FR-30）。
- Tag 归一化：NFKC/小写/去 `#`/英文单数化（`inflect`）；调用时把现有 Tag 词表传给模型，要求优先复用；MVP 不做全局合并（P2）。
- **不按金额止损**：按单次输出 tokens 和单条调用数限额，避免长内容被金额阈值误伤；实际 token 仍记录，`cost_usd` 只作观察。
  - `llm.chunk_chars = 20000`：长文本分块大小。
  - `llm.max_calls_per_item = 16`：单条最多 LLM 调用数（含 map + reduce）；1 小时转写约 1–2 次，10 万字符书约 5–6 次。
  - `llm.max_output_tokens_per_call = 1024`：单次输出上限；prompt 要求短 JSON。
  - `llm.max_input_tokens_per_item = 200000`：单条输入总量上限，防止异常长文本无限分块。
  - 任一限制超出 → `llm.limit_exceeded`；明确失败，不静默截断；音频/转写仍可消费，可调整配置后重试。
- 记录 `model`、`prompt_version`、`input_tokens`、`output_tokens`、`cost_usd`；成本由配置的价格表估算，仅用于观察。
- JSON 模式可能返回空白 content（DeepSeek 文档明确提示）；解析失败/空白时重试一次并校验 schema，仍失败则标记 `llm.invalid_output`。
- 隐私：Add 页明确提示“转写/书文本会分块发送给 DeepSeek”；不做 per-item 开关（NFR-02）；测试可用 `TROVE_LLM_ENABLED=false` 跳过。

**EPUB 细节**：

- 走 `META-INF/container.xml` → OPF → spine；EPUB3 读 nav，EPUB2 读 NCX，缺失时按 spine + 标题兜底。
- 检测 `META-INF/encryption.xml`：内容加密（ADEPT/LCP）拒绝；仅字体混淆可放行。固定版式（fixed-layout）拒绝，提示“仅支持可重排 EPUB”。
- 每章提取纯文本 + 基础标签（p/h1-6/blockquote/li/em/strong），用 `nh3` 白名单净化；MVP 不渲染图片/脚注弹窗/书内搜索（这些是 V1/native）。
- 原始 EPUB 复制进库；`book.json` 保存元数据、章节 HTML 和纯文本；封面单独提取。

**本地文件与去重**：

- 本地音频/EPUB：复制进库，原文件不动（FR-15）；浏览器不支持的音频格式转码为 `audio.m4a`。
- 本地视频：只存原始路径 + 抽取的音频，不复制视频（FR-14）；原文件移动后音频仍可播放，来源路径保留。
- `source_key`：URL 用规范化 URL；本地文件用 SHA-256；播客单集用 `feed_url#episode_guid`（GUID 缺失时用 enclosure URL）。唯一索引保证第二次 add 返回已存在（FR-07）。
- 规范化 URL 去掉 utm/fbclid 等跟踪参数；YouTube 归一到 `watch?v=<id>`，B 站归一到 `video/<BV|av>`；带 `list=` 或 `p>1` 明确拒绝。

### 3.5 认证与安全

- **单用户认证**：Argon2id 密码哈希；`trove auth set-password` 写入配置（0600）。登录成功设置签名 Cookie（HttpOnly、SameSite=Lax、HTTPS 时 Secure，30 天）。失败按 IP 限速（5 次/5 分钟）。
- **CSRF**：所有写操作只用 POST/PATCH/DELETE；SameSite=Lax + 校验 `Origin`/`Sec-Fetch-Site`；不使用 GET 改状态。
- **绑定**：默认 `127.0.0.1`；手机优先走 Tailscale Serve（VPN + HTTPS）。需要纯 LAN 时 `trove serve --lan` 绑定 `0.0.0.0`，仍强制认证；启动时警告“非 HTTPS 仅建议可信局域网”。这比 FR-80 的“默认只绑定局域网”更严格：默认根本不暴露到网卡。
- **SSRF**：播客 feed/附件走 `SafeHttpClient`：只允许 http/https；每次重定向重新校验；DNS 解析后拒绝私网/回环/链路本地/元数据/CGNAT 地址；限制重定向次数、超时、feed 10MB、媒体 1GB。视频 URL 只允许平台白名单，不做通用下载代理（FR-85）。
- **上传**：流式落临时文件，边写边算 SHA-256；限制大小（默认视频 4GB/音频 500MB/EPUB 100MB，可配）；扩展名/MIME 白名单 + ffprobe/EPUB 结构校验；失败清理。
- **文件服务**：只按数据库中的 artifact 路径返回；`FileResponse` 支持 Range/ETag；`ETag=sha256`；`Accept-Ranges: bytes`；`X-Content-Type-Options: nosniff`；`Cache-Control: private`。Starlette 必须 ≥0.49.1（CVE-2025-62727 Range DoS）。
- **HTML 注入**：Jinja2 自动转义；EPUB 章节 `nh3` 白名单净化；CSP `default-src 'self'`，禁止远程脚本/图片；不把用户文本标记为 safe。
- **密钥**：`DEEPSEEK_API_KEY` 放 `~/Trove/.env`（0600）；session secret 随机生成；日志不打印 Cookie/Key。
- **不暴露开放下载器**：没有任意 URL 代理接口；播客只抓取 feed 里的 enclosure，且类型/大小受限。

### 3.6 部署与运维

- **数据目录**：`~/Trove/`（`TROVE_HOME` 可覆盖），权限 0700；`config.toml`、`.env`、`trove.db`、`library/`、`cache/`、`logs/`。
- **进程**：`uv run trove serve`（API/HTML）与 `uv run trove worker`（处理）两个 launchd LaunchAgent，`RunAtLoad` + `KeepAlive`；升级时先 `trove db upgrade` 再重启。
- **依赖**：`uv.lock` 锁定 Python；`ffmpeg`/`ffprobe`、`yt-dlp` 用 Homebrew/uv 安装并记录版本；模型首次 `trove setup` 下载。
- **不使用 Docker**：MLX/Metal 在 macOS 容器里不可用；本地视频路径和 launchd 也更适合原生进程。
- **休眠/重启**：队列和阶段状态在 SQLite；worker 启动回收 stale run；可选在处理时用 `caffeinate -i -w <pid>` 防止空闲睡眠，不做常驻阻止睡眠。
- **备份/导出**：P1 的导出 zip 即备份；日常可用 `sqlite3 trove.db ".backup ..."` 或文件快照；不做云同步。
- **日志**：`logs/trove.log` 轮转（10MB × 5）；每个 Run 单独 `logs/runs/<run-id>.log`，UI 只读 tail；不把完整日志塞进数据库。

**HTTPS 访问矩阵**：

| 场景 | 入口 | HTTPS | 说明 |
|---|---|---|---|
| 桌面本机 | `http://127.0.0.1:8765` | 否（secure context 例外） | 开发/管理；Media Session 可用 |
| 手机 + Tailscale | `https://<host>.<tailnet>.ts.net` | 是 | **已选**；有效证书、无需装 CA |
| 手机 + 局域网 Caddy | `https://trove.local` | 是（内部 CA） | 备选；需在手机安装 Caddy 根证书 |
| 手机直连 LAN HTTP | `http://<mac-ip>:8765` | 否 | 仅受信任局域网；Media Session/PWA 不承诺 |

### 3.7 测试与工具

- **单元/集成**：pytest + httpx；临时 SQLite；下载/ASR/LLM 用 fake adapter，真实适配器只在标记为 `network` 的测试里跑，不进默认 CI。
- **真实 golden**：EPUB2/EPUB3、短音频、播客 RSS XML、transcript JSON；用真实公开领域素材，不用凭空捏造的占位数据。
- **浏览器 E2E**：Playwright（Python）跑 WebKit + Chromium；覆盖登录、添加、播放/续听、transcript、搜索定位、EPUB 翻章、进度写回。
- **基准/评估**：`trove bench asr`、`trove bench search`、`trove eval search`；结果写入 `docs/` 或 `.scratch/` 供验收记录。
- **静态检查**：`ruff check`、`ruff format --check`、`mypy`；新增 `scripts/check.sh` 汇总，lefthook 在提交前跑文档检查。前端 JS 保持少量原生模块，由 Playwright 覆盖行为，不引入 Node 构建/类型链。

## 4. 数据与文件契约

### 4.1 内容包目录

```
~/Trove/library/<item-id>/
  source.json        # 原始/规范化 URL、平台、标题、作者、日期、路径
  audio.m4a          # 视频/播客抽取音频；本地音频可为原格式
  transcript.json    # 分段文本 + start/end
  book.epub          # 原始 EPUB（仅书）
  book.json          # 元数据、章节 HTML/纯文本（仅书）
  ai.json            # 摘要、Tags、模型、prompt 版本、生成时间、usage
  cover.jpg          # 可选
```

- 文件名固定，Item 目录用 UUID；标题不进路径，避免改名导致路径变化。
- `transcript.json`/`book.json` 是可移植的文本源；数据库里的分段/段落是索引派生，可重建。
- 视频不落盘；本地视频只在 `source.json` 保留原始路径，`audio.m4a` 是库内副本。
- 删除 Item 只删 `library/<item-id>/`、数据库行和 FTS 行；绝不删除用户的原始路径（FR-17）。
- 导出 zip 包含 `source.json`、音频、transcript、书文件、`ai.json` 和 `index.md`；视频条目只含 `source.json` + 音频，不含视频文件（FR-64）。

### 4.2 关键字段

- `items`：`id`、`source_key`（唯一）、`source_type`、`platform`、`source_url_raw`、`source_url_canonical`、`source_path`、`title`、`author`、`published_at`、`fetched_at`、`language`、`duration_sec`、`summary`、`consumption_state`、`audio_position_sec`、`book_locator`、`created_at`、`updated_at`。
- `runs`：`id`、`item_id`、`state`、`current_stage`、`error_code`、`error_message`、`cancel_requested_at`、`heartbeat_at`、`created_at`、`started_at`、`finished_at`。
- `run_steps`：`run_id`、`stage`、`state`、`attempt`、`error_code`、`error_message`、`started_at`、`finished_at`。
- `artifacts`：`item_id`、`kind`、`path`、`sha256`、`size`、`mime`、`duration_sec`。这组字段直接服务 V1 的 manifest/可续传下载，但 MVP 不暴露同步接口。
- `transcript_segments`：`item_id`、`seq`、`start_ms`、`end_ms`、`text`。
- `book_chapters`：`item_id`、`chapter_index`、`title`、`html`、`text`。
- `book_paragraphs`：`item_id`、`chapter_index`、`paragraph_index`、`text`。
- `tags`：`id`、`name`、`normalized_name`（唯一）。
- `item_tags`：`item_id`、`tag_id`、`source`（`ai`/`user`）。
- `ai_results`：`item_id`、`run_id`、`summary`、`model`、`prompt_version`、`input_tokens`、`output_tokens`、`cost_usd`、`created_at`。
- 时间统一存 UTC 毫秒整数；API 输出 ISO 8601；`published_at` 保留原字符串（可能是“2026”或“2026-10”）。

### 4.3 V1 同步预留（不在 MVP 实现）

- 文件不可变：`artifacts.sha256/size/mime` + HTTP `ETag` + `Range` 已经就绪。
- V1 迁移时给 `items` 加 `version`/`deleted_at`，新增 manifest/cursor 接口；MVP 不提前实现 tombstone/双向同步。
- 单用户、按字段 last-write-wins 的同步策略在 V1 再定；当前消费进度直接存在 `items`，不阻碍未来拆表。
- V1 客户端形态（Android native vs PWA）不在本次选型范围；本方案只保证 JSON API、文件元数据和认证方式不阻碍任一形态。

## 5. API 契约

### 5.1 JSON API

| 方法 | 路径 | 用途 |
|---|---|---|
| POST | `/api/items` | 添加 URL/本地路径/播客单集；已存在返回 200 + `deduplicated: true` |
| POST | `/api/uploads` | 流式上传本地文件，返回 upload id |
| POST | `/api/feeds/preview` | 播客 feed URL → 最近单集列表 |
| GET | `/api/items` | Library 列表；类型/状态/Tag/来源过滤与排序 |
| GET | `/api/items/{id}` | 详情、来源、Run 状态、Tag、消费进度 |
| PATCH | `/api/items/{id}` | 修改标题/作者/Tag |
| DELETE | `/api/items/{id}` | 删除派生文件和索引，不动原始文件 |
| GET | `/api/items/{id}/audio` | Range/ETag 音频流 |
| GET | `/api/items/{id}/transcript` | 分段文本 |
| GET | `/api/items/{id}/book/chapters/{n}` | 薄阅读器章节 HTML |
| PUT | `/api/items/{id}/progress` | 播放/阅读位置 + 消费状态 |
| POST | `/api/items/{id}/retry` | 重试失败 Run，从断点继续 |
| POST | `/api/items/{id}/reprocess` | 从指定阶段重跑（如更换 prompt 后整理） |
| GET | `/api/runs/{id}` | Run/阶段状态、失败原因、日志 tail |
| POST | `/api/runs/{id}/cancel` | 取消排队/运行中任务（best-effort） |
| GET | `/api/search` | 统一搜索；按 Item 聚合 + 匹配证据 |
| GET | `/api/tags` | Tag 列表/计数 |
| GET | `/api/export` | P1：导出 zip |
| POST | `/api/auth/login` `/logout` | 单用户会话 |
| GET | `/api/health` | 主机/DB/worker 健康检查 |

- FastAPI 自动生成 OpenAPI（`/api/openapi.json`），作为未来 Android 的契约；不在 MVP 做客户端代码生成。
- 错误统一 `{code, message, details?}`；失败原因用稳定 code（如 `download.login_required`、`epub.drm`、`asr.failed`），UI 映射中文提示。
- 音频/文件响应必须带 `ETag`、`Accept-Ranges`；避免自定义 Range 解析，直接用 Starlette `FileResponse`（已修 CVE 的版本）。
- API 与 HTML 路由共用同一 application service；HTML 不通过 HTTP 调自己的 API。
- Android 可直接复用会话 Cookie（HTTP 客户端持有 cookie jar）；V1 若需要长期设备 token，再增加 bearer 认证，不改变现有资源和路径形状。

### 5.2 HTML 路由

- `/login`、`/library`、`/search`、`/add`、`/items/{id}`、`/items/{id}/listen`、`/items/{id}/read`。
- Inbox 是 Library 的过滤视图（`/library?state=processing,failed`），不单独占导航位（FR-58）。
- Continue 是 Library 的排序/过滤入口（P1），不做 Up Next。
- Consumer Shell 的 listen/read 路由独立成模板/JS 模块；如果 Q10 失败或未来移除，不影响 Host Console。

## 6. 性能与容量核算

- **音频**：64kbps 单声道 AAC ≈ 28.8MB/小时；100 小时 ≈ 2.75GB。加 transcript（约 1.2M 字符，JSON 约 5–10MB/100h）、EPUB 原件、`book.json`、AI 结果，目标 <5GB；导入 20 条真实内容后按实际值外推校准（NFR-06）。
- **搜索**：约 11M 中文字符 → 约 22M bigram token；FTS 索引预计数百 MB；千条级查询目标 <100ms，验收 <1s。用 `trove bench search` 在 1k 条合成/真实数据上实测。
- **ASR**：`large-v3-turbo` 在 M1 Pro 上的组件目标是 ≥3× 实时（1h ≤20min），给下载/整理/索引留余量；端到端 1h 视频必须 <30min。实际以 `trove bench asr` 和完整管线计时为准。模型权重约 1.6GB，运行时内存需留 4–6GB。
- **数据库**：1k Item、约 50 万 transcript 段/书段落，SQLite 单文件足够；WAL + 短事务；不做分库分表。
- **并发**：单 worker、单 API 进程；同时只处理 1 条。20 条真实内容的验证不需要并发；后续可加第二个 worker，领取逻辑不变。

## 7. 验证计划与门控

| 门控 | 方法 | 通过标准 | 不通过的动作 |
|---|---|---|---|
| ASR 组件速度 | `trove bench asr` 跑 1 小时真实中文音频 | ≤20 分钟 | 换 large-v3 / SenseVoice / whisper.cpp；仍不达标则调整 MVP 预期并记录 |
| 端到端 1h 视频 | 完整管线：下载→抽音频→转写→整理→索引 | <30 分钟 | 定位瓶颈；换 ASR/降码率/并行下载与转写；不达标不宣称满足 NFR-05 |
| 中文两字搜索 | 单元测试 + 20 条真实内容 | `记忆`/`智能` 等两字词命中 | 调整 bigram/查询构造；不接受“只支持三字” |
| 搜索评估 | 50+ 条内容、30 个预注册 query | recall@10、首个相关排名达标；漏召回可解释 | 调权重/分段粒度；语义检索仍留 P2 |
| 搜索延迟 | `trove bench search` 在 1k 条数据上跑 | p95 <1s（目标 <100ms） | 调索引/分段粒度；仍不达标再考虑外部索引 |
| 来源成功率 | 10 B 站 + 10 YouTube + 10 播客 + 10 EPUB + 10 本地文件手动跑 | 各 8/10（EPUB/本地 10/10） | 按失败原因分类；cookie/地区/DRM 明确提示，不静默失败 |
| Tag 可用率 | 20 条真实内容人工判分 | ≥70% | 调 prompt/模型/Tag 词表；记录模型版本 |
| 重启/续跑/取消 | 处理中 kill worker、重启；取消排队/运行中 | 不丢任务、不重复已完成阶段、可重试 | 修状态机/子进程清理 |
| Q10 手机播放 | 1 周手机浏览器（HTTPS）连续听/锁屏/倍速/续听 | 满足“听”的验收；音频不因导航中断 | 收缩到桌面；native 进下一里程碑；或换 React 表现层 |
| 存储 | 导入 20 条真实内容后 `du -sh ~/Trove` | 外推 100h+100 本 <5GB | 降码率/清缓存/重算 EPUB 策略 |
| 安全 | 未认证访问、私网 URL、超大上传、恶意 EPUB HTML | 全部拒绝且提示清晰 | 修校验；安全项不降级 |
| 媒体流 | `curl -H 'Range: bytes=0-1023'` | 206 + ETag/Accept-Ranges | 修文件服务；用于 V1 可续传 |

## 8. 被否决或未采用的方案

| 方案 | 否决/未采用原因 |
|---|---|
| Audiobookshelf sidecar（旧草案） | GPL-3.0；Tag/搜索/队列/内容包会出现两套事实源；最终需求已定义 Host Console API |
| Node/TypeScript 全栈 | ASR/EPUB 生态弱；yt-dlp 仍是 Python；双运行时收益不足 |
| React + Vite | 不是否决，是备选：只有 Q10 音频连续性失败或 Web 壳长期化时才升级 |
| Celery/Redis、Dramatiq | 多一个常驻服务；SQLite 作业表 + 单 worker 已满足持久化/重试/取消 |
| Postgres/Meilisearch/Elasticsearch | 单用户千条级不需要；运维、备份、索引同步成本更高 |
| FTS5 `unicode61` 或 `trigram` | 实测两字中文不命中，直接违反 FR-51 |
| EbookLib | AGPL-3.0；核心依赖不适合未来闭源；EPUB 解析需求很薄，直接解析可控 |
| Tauri/Electron 桌面 App | 需求明确不做桌面 App |
| Next.js/SSR 框架 | 本地认证应用无 SEO/首屏需求；Jinja2 + HTMX 更简单 |
| Docker | macOS 容器无法用 MLX/Metal；本地视频路径/launchd 也更适合原生 |
| 现在做向量检索/语义搜索 | P2；关键词 + 评估先达标，避免过早引入 embedding/索引服务 |
| 词级时间戳/WhisperX | FR-23 明确不要求；增加对齐依赖和成本 |

## 9. 风险与应对

| 风险 | 影响 | 应对 |
|---|---|---|
| mlx-whisper 中文质量/静音幻觉 | 摘要/Tag/搜索质量下降 | 评估 20 条真实内容；调阈值/换 large-v3；必要时换 SenseVoice/whisper.cpp VAD |
| B 站/YouTube 登录/地区限制 | 来源成功率达不到 8/10 | 支持用户提供 cookies.txt；按原因分类提示；不绕过 DRM/地区限制 |
| iOS Safari 后台/锁屏播放 | Q10 不通过 | 首先验证 `<audio>` + Media Session；失败则按需求收缩到桌面，native 进下一里程碑 |
| HTMX 导航中断音频 | Consumer Shell 不可用 | 播放器放在 swap 区域外；Q10 spike 第一周验证；失败换 React 表现层，API 不变 |
| EPUB 多样性/DRM/固定版式 | 10/10 不达标 | 明确拒绝不可重排/加密书；真实书库回归；必要时后续引入 Readium/foliate |
| DeepSeek 调用/输出 token 超限或内容质量 | 整理失败/Tag 不可用 | 单次输出 token 上限；单条调用数上限；分块 map-reduce；prompt 版本化；记录实际 token/成本；超限明确报错 |
| SQLite FTS5 在 Python 构建中缺失 | 搜索不可用 | 启动时创建测试 FTS 表自检；`uv` Python 需带 FTS5；失败给出安装指引 |
| EPUB 图片/本地无损音频导致超 5GB | 容量目标失守 | 薄阅读器不存图片；只保留原 EPUB + 封面；本地音频按 FR-15 保留原件，按真实库重算并提示转码 |
| Whisper 输出繁体导致简体两字搜索漏召回 | 中文搜索不达标 | 评估时统计繁体输出；若出现，索引层加 OpenCC t2s（只影响索引，不改展示） |
| 手机直连 LAN HTTP 泄露密码 | 安全风险 | 默认 127.0.0.1；非本机访问要求 HTTPS（Tailscale/Caddy）；纯 HTTP 仅受信任局域网并显示警告 |
| Tailscale 依赖 | 用户不想装 | Caddy 内部 CA 备选；纯 LAN HTTP 仅管理，不承诺 Media Session/PWA |
| 单机安全暴露 | 局域网/公网风险 | 默认 127.0.0.1；Tailscale/VPN；认证；SSRF/上传/CSP；不暴露开放下载器 |

## 10. 建议实施顺序

1. **M0 — 主机骨架**：uv 项目、配置、SQLite/Alembic、认证、布局/模板、health；worker + SQLite 队列；添加 URL/本地文件；yt-dlp/ffmpeg；音频播放与进度。验收：一条 B 站/YouTube 视频可入库、播放、重启后续跑。
2. **M1 — 文本与搜索**：mlx-whisper 子进程、transcript 分段、FTS5 bigram、搜索页/API、transcript 阅读；两字中文测试。验收：端到端 1h 视频 <30min；`记忆`/`智能` 命中；搜索 <1s。
3. **M2 — 书与整理**：EPUB 解析/薄阅读器、DeepSeek 摘要/Tag、Tag 编辑/过滤、Continue、导出 zip。验收：EPUB 10/10；Tag ≥70%；导出可读。
4. **M3 — P1 与 Q10**：文内搜索、搜索定位段落、PWA、手机 HTTPS 一周 spike；按 Q10 结果决定是否保留/收缩 Consumer Shell。

## 11. 第三方组件、源码地址与许可证

> 源码地址以官方 GitHub 仓库为准；模型权重和 API 服务不是 GitHub 代码组件，单独标注。许可证以仓库为准，商业化前复核。

### 11.1 选用的代码依赖

| 组件 | 用途 | GitHub | 许可证 |
|---|---|---|---|
| CPython | Python 3.12 运行时 | https://github.com/python/cpython | PSF-2.0 |
| uv | Python 环境/依赖 | https://github.com/astral-sh/uv | Apache-2.0/MIT |
| FastAPI | Web/API | https://github.com/fastapi/fastapi | MIT |
| Starlette | ASGI/FileResponse | https://github.com/encode/starlette | BSD-3-Clause |
| Uvicorn | ASGI server | https://github.com/encode/uvicorn | BSD-3-Clause |
| Pydantic | 校验/配置 | https://github.com/pydantic/pydantic | MIT |
| Jinja2 | 服务端模板 | https://github.com/pallets/jinja | BSD-3-Clause |
| SQLAlchemy | ORM | https://github.com/sqlalchemy/sqlalchemy | MIT |
| Alembic | 数据库迁移 | https://github.com/sqlalchemy/alembic | MIT |
| SQLite | 数据库/FTS5 | https://github.com/sqlite/sqlite | Public domain |
| httpx | HTTP 客户端 | https://github.com/encode/httpx | BSD-3-Clause |
| feedparser | 播客 RSS | https://github.com/kurtmckee/feedparser | BSD-2-Clause |
| lxml | EPUB/XML 解析 | https://github.com/lxml/lxml | BSD-3-Clause |
| nh3 | HTML 净化 | https://github.com/messense/nh3 | MIT |
| argon2-cffi | 密码哈希 | https://github.com/hynek/argon2-cffi | MIT |
| itsdangerous | 签名 Cookie | https://github.com/pallets/itsdangerous | BSD-3-Clause |
| python-multipart | 文件上传解析 | https://github.com/Kludex/python-multipart | Apache-2.0 |
| openai-python | DeepSeek 兼容 SDK | https://github.com/openai/openai-python | Apache-2.0 |
| inflect | 英文 Tag 单数化 | https://github.com/jaraco/inflect | MIT |
| yt-dlp | 视频/播客下载 | https://github.com/yt-dlp/yt-dlp | Unlicense |
| FFmpeg | 抽音频/转码 | https://github.com/FFmpeg/FFmpeg | LGPL-2.1+ / GPL |
| MLX | Apple Silicon 推理 | https://github.com/ml-explore/mlx | MIT |
| mlx-whisper | 语音转写 | https://github.com/ml-explore/mlx-examples/tree/main/whisper | MIT |
| Whisper | 转写模型代码 | https://github.com/openai/whisper | MIT |
| HTMX | 服务端交互 | https://github.com/bigskysoftware/htmx | BSD-2-Clause |
| Pico CSS | CSS 基线 | https://github.com/picocss/pico | MIT |
| Tailscale | 手机 HTTPS/VPN | https://github.com/tailscale/tailscale | BSD-3-Clause |
| pytest | 测试 | https://github.com/pytest-dev/pytest | MIT |
| Playwright Python | 浏览器 E2E | https://github.com/microsoft/playwright-python | Apache-2.0 |
| ruff | lint/format | https://github.com/astral-sh/ruff | MIT |
| mypy | 类型检查 | https://github.com/python/mypy | MIT |

> Tailscale 客户端为 BSD-3，Tailscale 服务另有条款；Homebrew 的 FFmpeg 构建可能含 GPL 组件，个人使用；若分发需用 LGPL-only 构建。

### 11.2 模型与服务

| 组件 | 用途 | 地址 | 许可证/条款 |
|---|---|---|---|
| Whisper large-v3-turbo（MLX） | 转写权重 | https://huggingface.co/mlx-community/whisper-large-v3-turbo | MIT（以模型卡为准） |
| DeepSeek API | 摘要/Tag | https://api-docs.deepseek.com/ | 商业服务条款；GitHub 组织：https://github.com/deepseek-ai |

### 11.3 备选与回退

| 组件 | 触发条件 | GitHub | 许可证 |
|---|---|---|---|
| Caddy | 不装 Tailscale 时的 HTTPS | https://github.com/caddyserver/caddy | Apache-2.0 |
| React | HTMX 音频连续性失败时的表现层 | https://github.com/facebook/react | MIT |
| Vite | React 方案构建 | https://github.com/vitejs/vite | MIT |
| whisper.cpp | ASR 回退（VAD/Metal） | https://github.com/ggml-org/whisper.cpp | MIT |
| FunASR / SenseVoice | 中文 ASR 回退 | https://github.com/modelscope/FunASR | MIT（模型条款另核） |
| OpenCC | 繁体→简体索引回退 | https://github.com/BYVoid/OpenCC | Apache-2.0 |
| foliate-js | 完整 EPUB 渲染（V1 以后） | https://github.com/johnfactotum/foliate-js | MIT |
| Readium | 完整 EPUB 渲染（V1 Android） | https://github.com/readium/kotlin-toolkit | BSD-3（各仓库另核） |
| sqlite-vec | P2 语义检索 | https://github.com/asg017/sqlite-vec | MIT/Apache-2.0 |

### 11.4 明确不采用

| 组件 | GitHub | 许可证 | 原因 |
|---|---|---|---|
| EbookLib | https://github.com/aerkalov/ebooklib | AGPL-3.0 | 核心依赖不适合未来闭源；EPUB 解析需求很薄 |
| Audiobookshelf | https://github.com/advplyr/audiobookshelf | GPL-3.0 | 两套事实源；与 Host Console/API 冲突 |
| Meilisearch | https://github.com/meilisearch/meilisearch | MIT | 多一个常驻服务；千条级 FTS5 足够 |
| WhisperX | https://github.com/m-bain/whisperX | BSD（以仓库为准） | 词级时间戳/对齐不是 MVP 需求 |
| Celery | https://github.com/celery/celery | BSD-3-Clause | 需要 broker；SQLite 队列足够 |
| Redis | https://github.com/redis/redis | 以仓库为准 | 仅为队列引入额外服务 |
| Postgres | https://github.com/postgres/postgres | PostgreSQL License | 单用户本地 SQLite 足够 |
| Next.js | https://github.com/vercel/next.js | MIT | 无 SSR/SEO 需求；Jinja2 + HTMX 更简单 |
| Tauri | https://github.com/tauri-apps/tauri | MIT/Apache-2.0 | 需求明确不做桌面 App |
| Electron | https://github.com/electron/electron | MIT | 同上；且体积/内存不划算 |

## 12. 已确认的选择

1. **前端形态**：Python + Jinja2 + HTMX 的单语言薄壳；不引入 React/Node 构建链。Q10 音频连续性失败时再换 React 表现层，API/数据模型不变。
2. **手机 HTTPS**：Tailscale Serve；Caddy 内部 CA 只作为不装 Tailscale 时的备选。
3. **LLM 限额**：不按金额止损；按单次输出 tokens（默认 1024）和单条调用数（默认 16）限制，另设单条输入 token 上限（默认 200000）。实际 token 和估算成本只记录，不阻断。

关键决策已拆分为 ADR：

- [0001 MVP 主机采用 Python 单体、SQLite 与独立 worker](../adr/0001-python-monolith-sqlite-worker.md)
- [0002 Web 客户端采用服务端渲染 + HTMX，不引入 React SPA](../adr/0002-server-rendered-htmx-web-shell.md)
- [0003 搜索使用 SQLite FTS5 + 中文 bigram](../adr/0003-sqlite-fts5-cjk-search.md)
- [0004 转写使用 mlx-whisper large-v3-turbo](../adr/0004-mlx-whisper-local-asr.md)
- [0005 EPUB 直接解析，不引入 EbookLib/Audiobookshelf](../adr/0005-direct-epub-extraction.md)
- [0006 原生 macOS 部署 + launchd + Tailscale Serve](../adr/0006-native-launchd-tailscale.md)
- [0007 DeepSeek 整理按 token/调用数限额，不按金额止损](../adr/0007-deepseek-organization-limits.md)
- [0008 内容包是便携事实源，数据库是可重建索引](../adr/0008-content-package-as-source-of-truth.md)

下一步：进入 M0 实施。
