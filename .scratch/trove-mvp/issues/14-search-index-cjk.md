# 14 — FTS5 + 中文 Bigram 搜索索引与 API

Status: ready-for-agent  
Type: task  
Milestone: M1  
Blocked by: 05, 13  
Spec: [spec.md](../spec.md)  
Requirements: FR-47, FR-48, FR-51, FR-52, NFR-05  
ADRs: [0003](../../../docs/adr/0003-sqlite-fts5-cjk-search.md)

## Context

中文两字词必须命中，而 SQLite FTS5 默认分词器会把连续中文当成一个 token，trigram 只支持 ≥3 字。需要在应用层做 CJK bigram 归一化，并建立可按 Item 聚合、可定位段落的搜索索引。

## Scope

- CJK 归一化：NFKC/小写/去 HTML/压缩空白；中文连续段生成重叠 bigram；拉丁词保留整词。
- FTS5 `porter unicode61`；`search_fts` 一行一个可定位单元：title、summary、每个 Tag、每段 transcript、书的每个段落。
- 查询构造：中文 bigram 短语、英文 token、单字 `LIKE` 回退；只拼 token，不拼 FTS 语法；查询长度上限。
- bm25 + doc kind 权重；按 Item 聚合，最多 3 条证据；snippet 从原始 text 生成。
- 搜索 API 与索引重建命令；标题/摘要/Tag/transcript 变更时更新索引。
- 搜索评估所需的查询/结果结构。

## Acceptance Criteria

- [ ] 单元测试：`人工智能` → `人工 工智 智能`；`智能`/`记忆` 两字命中；英文 porter 词干；单字回退。
- [ ] 搜索结果按 Item 聚合，带匹配段落和稳定 ref（transcript seq/start_ms；book chapter/paragraph）。
- [ ] 标题、摘要、Tag、transcript 文本均可命中；删除/编辑 Item/Tag 后索引同步。
- [ ] `trove index rebuild` 可从内容包重建，重建前后结果一致。
- [ ] 千条级 p95 <1 秒（26 记录实测）；低于目标的基准测试可运行。
- [ ] 不做向量/语义检索。

## Testing

- 纯函数表驱动：normalizer/query builder/ref 生成。
- Host seam：seed Item/transcript/book/Tag → 搜索 → 分组/证据/过滤（过滤 UI 在 15）→ 删除/编辑后重建。
- 索引重建幂等测试；FTS 注入/长度边界测试。
- 性能基准脚本。

## Out of Scope

- 搜索页面/筛选 UI（15）、语义检索/embedding（P2）。
- 中文分词词典/jieba；bigram 是确定性方案。
