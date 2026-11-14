# 02 — Host V1 Schema 与迁移

Status: ready-for-agent
Type: task
Milestone: M0
Blocked by: none
Spec: [spec.md](../spec.md)
Tech: [tech-selection.md](../tech-selection.md)
Requirements: FR-73, NFR-08
ADRs: [0001](../../../docs/adr/0001-python-monolith-sqlite-worker.md), [0008](../../../docs/adr/0008-content-package-as-source-of-truth.md), [0009](../../../docs/adr/0009-native-android-client-app-managed-sync.md)

## Context

V1 同步需要 Item 级版本/墓碑、全局同步序号、字段时钟和幂等记录。先把 schema 和迁移建对；API 和客户端行为由后续 issue 接入。Content Package 布局不能改变。

## Scope

- `items` 增加 `version`、`deleted_at`、`content_seq`、`state_seq`；为 `content_seq`/`state_seq` 建索引。
- 新增 `device_tokens`：`device_id`、`name`、`token_hash`（唯一索引）、`created_at`、`last_used_at`、`revoked_at`、`session_epoch`。
- 新增 `sync_sequence` 单行表：`value`、`epoch`。
- 新增 `sync_field_clocks`：`(item_id, field)` 主键，`client_updated_at`、`device_id`；field 为 `audio_progress`/`book_progress`/`consumption_state`/`tags`。
- 新增 `sync_mutations`：`(device_id, mutation_id)` 主键，`response_json`、`created_at`；用于 Idempotency-Key。
- 新增一个 Alembic migration（在 0003 之后），SQLite batch mode；为现有 Item 回填 `version=1` 和同步序号。
- 更新数据库 schema 测试；不改变 Content Package 文件布局。

## Acceptance Criteria

- [ ] 空库和已有 MVP 数据库都能迁移到 V1 schema；重复执行为 no-op。
- [ ] 现有 Item 全部回填 `version`/`content_seq`/`state_seq`，无 NULL。
- [ ] `device_tokens.token_hash`、`sync_mutations(device_id, mutation_id)` 唯一约束生效。
- [ ] FTS5 索引和现有 Item/Run/Artifact 数据不回归。
- [ ] 迁移失败时事务回滚；临时 `TROVE_HOME` 可重复测试。

## Testing

- 迁移测试：空库 → 全量迁移 → 关键列/表/索引/唯一约束断言。
- 回填测试：预置 MVP Item 后迁移，断言 seq/version 有值且顺序稳定。
- 运行现有数据库测试与 `python3 scripts/check-docs.py`。

## Out of Scope

- 设备 token API、manifest/state API、soft delete、LWW 写接口；由 03–07 实现。
- 修改 Content Package 的 `source.json` 或文件布局。
