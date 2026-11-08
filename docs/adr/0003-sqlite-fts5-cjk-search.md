# 搜索使用 SQLite FTS5 + 中文 bigram

MVP 需要千条级本地搜索、中文两字词必中、结果按 Item 聚合并定位到段落，且索引可重建。SQLite FTS5 的 `unicode61` 会把连续中文当成一个 token，`trigram` 只支持 ≥3 字；因此文档/查询先做 CJK bigram 归一化，再用 FTS5 `porter unicode61` 建索引，中文查询用 bigram 短语匹配。

**Status**: Accepted · 2026-11-08

## Considered Options

- 只靠 `unicode61`/`trigram`：实测两字中文不命中，违反 FR-51。
- jieba 分词：词典外的新词/人名可能切不出来；bigram 是确定性兜底。
- Meilisearch/Typesense/Elasticsearch：多一个常驻服务、索引同步和备份问题；千条级不需要。
- 向量/语义检索：P2；先用关键词 + 评估达标。

## Consequences

- 索引 token 约为中文字符数的 2 倍；需要 tokenizer 单元测试和 `trove index rebuild`。
- 查询构造必须只拼接 token，不能直接拼 FTS5 语法；单字查询退化为 `LIKE`。
- 搜索质量用 50+ 条真实内容、30 个预注册 query 评估；不达标先调权重/分段，不直接上语义检索。
- 见 [技术选型](../ideas/trove-tech-selection.md) 第 3.3 节；需求 FR-47/48/51/52、NFR-05。
