# 02 — 数据库 Schema 与迁移

Status: ready-for-agent  
Type: task  
Milestone: M0  
Blocked by: 01  
Spec: [spec.md](../spec.md)  
Requirements: FR-06, FR-07, FR-08, FR-09, FR-17, FR-22, FR-29, FR-40, FR-64, FR-73, NFR-03  
ADRs: [0001](../../../docs/adr/0001-python-monolith-sqlite-worker.md), [0008](../../../docs/adr/0008-content-package-as-source-of-truth.md)

## Context

所有功能共享同一套 SQLite 数据：Item、Processing Run、artifact、transcript 分段、书章节/段落、Tag、AI 结果和 FTS 索引。先把 schema、约束和迁移建对，后续 issue 才能安全地并行开发。

## Scope

- 建表：`items`、`runs`、`run_steps`、`artifacts`、`transcript_segments`、`book_chapters`、`book_paragraphs`、`tags`、`item_tags`、`ai_results`、`search_fts`。
- 关键约束：`items.source_key` 唯一；`artifacts(item_id, kind)` 唯一；`tags.normalized_name` 唯一；`item_tags(item_id, tag_id)` 唯一；外键与级联规则。
- 索引：Item 创建/更新时间、Run 状态、transcript 分段、书章节/段落、Tag 关联。
- FTS5 表与启动自检（缺 FTS5 时给出明确错误）；索引写入/删除/重建由应用负责。
- Alembic 迁移（SQLite batch mode）与 repository 基础接口；时间统一 UTC 毫秒。

## Acceptance Criteria

- [ ] 从空数据库执行迁移可建立全部表和索引；重复执行为 no-op。
- [ ] `source_key`、artifact、Tag 等唯一约束在测试中生效。
- [ ] `search_fts` 可创建、写入、删除；FTS5 缺失时启动失败并提示安装方式。
- [ ] 删除 Item 的数据库级联不触碰用户原始路径（原始路径不在库内删除范围）。
- [ ] 迁移在临时 `TROVE_HOME` 上可测试，失败时事务回滚。

## Testing

- 迁移测试：空库 → 全量迁移 → 关键表/索引/唯一约束断言。
- FTS5 自检测试：正常创建和模拟缺失两种情况。
- Repository 约束测试：重复 source_key、重复 Tag、级联删除。
- `python3 scripts/check-docs.py` 通过。

## Out of Scope

- 业务 API、入库、处理状态机、搜索查询逻辑；由后续 issue 实现。
- V1 的 `version`/`deleted_at`、manifest/cursor、tombstone。
