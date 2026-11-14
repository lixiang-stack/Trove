# 15 — Android 本地 FTS5 搜索

Status: ready-for-agent
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

- [ ] “记忆”“智能”等两字中文词命中；英文词干命中。
- [ ] 结果按 Item 聚合，evidence 正确；点击打开对应 transcript/书段落。
- [ ] 离线搜索只覆盖已下载 Item；在线搜索覆盖全库。
- [ ] 索引可重建；FTS5 缺失/损坏有明确错误，播放/阅读仍可用。
- [ ] 1,000 Item 本地搜索 p95 <1 秒。
- [ ] 不做语义/向量检索。

## Testing

- Unit：CJK 归一化/查询构造/单字回退/porter；共享 Host fixture。
- App seam：在线/离线搜索、过滤、结果定位；真 Room + bundled SQLite。
- 性能：1,000 Item seed 搜索基准。

## Out of Scope

- 语义检索、推荐、Topic/实体。
- Host 搜索实现；由 MVP 已有功能覆盖。
