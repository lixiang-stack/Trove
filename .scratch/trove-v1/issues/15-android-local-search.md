# 15 — Android 本地 FTS5 搜索

Status: resolved
Type: task
Milestone: M2
Blocked by: 12, 13, 14
Spec: [spec.md](../spec.md)
Tech: [tech-selection.md](../tech-selection.md)
Requirements: FR-71, FR-72, NFR-11
ADRs: [0003](../../../docs/adr/0003-sqlite-fts5-cjk-search.md), [0009](../../../docs/adr/0009-native-android-client-app-managed-sync.md)

## Context

手机离线时要能搜索已下载的 transcript/书文本/Tag/摘要，并且中文两字词必须命中。Android 本地使用 bundled SQLite FTS5 + `porter unicode61` + CJK bigram，与 Host 共享查询/归一化规则。

## Scope

- bundled SQLite FTS5 虚表（raw SQL/migration），`norm_text` 索引 + 原始 `text`/`item_id`/`doc_kind`/`ref`。
- 从已下载 `transcript.json`、`book.json`、Item 元数据构建/增量更新索引；删除/更新/升级可重建。
- 查询构造与 Host 一致：CJK bigram、英文 porter、单字 LIKE 回退、200 字符上限。
- FTS5 MATCH + bm25 基础排序，Kotlin 按 doc_kind 重排；按 Item 聚合，最多 3 条 evidence。
- 在线搜索走 Host `/api/search`；离线只搜已下载 Item；结果打开 transcript/书匹配段落。
- 启动 FTS5 自检；索引损坏可重建；不阻塞 UI。
- 目标：已下载 1,000 Item p95 <1 秒。

## Acceptance Criteria

- [x] “记忆”“智能”等两字中文词命中；英文词干命中。
- [x] 结果按 Item 聚合，evidence 正确；点击打开对应 transcript/书段落。
- [x] 离线搜索只覆盖已下载 Item；在线搜索覆盖全库。
- [x] 索引可重建；FTS5 缺失/损坏有明确错误，播放/阅读仍可用。
- [x] 1,000 Item 本地搜索 p95 <1 秒。
- [x] 不做语义/向量检索。

## Testing

- Unit：CJK 归一化/查询构造/单字回退/porter；共享 Host fixture。
- App seam：在线/离线搜索、过滤、结果定位；真 Room + bundled SQLite。
- 性能：1,000 Item seed 搜索基准。

## Out of Scope

- 语义检索、推荐、Topic/实体。
- Host 搜索实现；由 MVP 已有功能覆盖。

## Implementation

- Added `SearchQuery` (Host-identical NFKC/CJK-bigram/porter query construction), `SearchIndex` over bundled SQLite FTS5, and `LocalSearchRepository` indexing downloaded item metadata plus parsed transcript/book text.
- Search UI calls Host `/api/search` when online and falls back to the local index when offline or the network fails; results are grouped by Item with up to 3 evidence snippets. Transcript results open the matching transcript segment; book results open the Reader at the matching chapter/paragraph. Filters cover type, consumption, Tag and Source.
- Index is rebuilt on first launch when empty and can be manually rebuilt from Settings; FTS5 absence degrades to online-only search without blocking playback/reading.
- Automated coverage: `SearchQueryTest`, `SearchIndexTest` (JVM skips framework SQLite without FTS5), `SearchIndexDeviceTest` (instrumented bundled SQLite), `SearchFlowTest`, `LocalSearchRepository.kt`/Host contract fixtures `contract/search.json` and `contract/search-query.json`.
- Pending: 1,000-item p95 benchmark on a real device.

### Android real-device acceptance (2026-11-16 / Android 16, API 36)

- Online search hit Host `/api/search` and returned grouped Item evidence; local search after airplane mode + `adb reverse` removal showed `离线 · 仅搜索已下载内容` and hit the downloaded Aesop book.
- `SearchIndexDeviceTest` passed on device: bundled SQLite FTS5 is available, Chinese bigrams (`智能`) and English stemming (`fox` → `foxes`) hit, and 1,000 indexed Items stayed under the 1 s p95 assertion.
- Result click opened the Reader at the matching book chapter; the first evidence anchor is chosen over summary/title evidence.
- Search filters (type EPUB + consumption + source local) narrowed correctly; switching to `已完成` produced zero hits.
- The 1,000-Item run is an FTS-index benchmark (`SearchIndexDeviceTest`), not a full App download/UI benchmark. Chinese text input could not be scripted through MIUI's IME (ADBKeyboard install is blocked by `INSTALL_FAILED_USER_RESTRICTED`), so the Chinese query path is covered by the device instrumented test rather than the search box UI.
