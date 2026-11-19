# 27 — 删除合集及全部单集时重置进度

Status: implemented
Type: bug
Milestone: M3
Spec: [spec.md](../spec.md)
Tech: [tech-selection.md](../tech-selection.md)
Requirements: FR-73
ADRs: [0009](../../../docs/adr/0009-native-android-client-app-managed-sync.md)

## Context

真机删除合集时选择「删除合集及全部单集」，随后重新添加同一合集，合集仍显示
「已听 2/75」。原因是 `delete_items` 只 soft delete 子 Item，重新添加按
`source_key` 复活同一 Item ID，Consumption State 和播放位置被保留。

删除确认文案明确说明「会从 Host 和手机移除，无法撤销」，保留旧进度与该语义冲突；
而 `ungroup` 的文案明确写「进度和文件不变」。两者应区分。

同一路径还观察到：重新添加时新的 inspection 标题（部分为 `Episode N` 占位）
覆盖了旧 Item 的真实标题；本票只处理进度，标题保留另记 TODO。

## Scope

- `delete_items` 软删除子 Item 时重置：
  `consumption_state=unstarted`、`audio_position_sec=0`、`book_locator=null`、
  `last_consumed_at=null`。
- 通过现有 sync tracking 自动递增 `state_seq`，客户端会收到状态变化。
- `ungroup` 和单项删除保持现状（保留进度）。
- 当前已重新添加的合集：一次性把进度重置为 0/75。

## Acceptance Criteria

- [x] `DELETE /api/collections/{id}?mode=delete_items` 后重新添加，合集进度为 0。
- [x] `ungroup` 重新添加时保留进度。
- [x] 单项删除/复活的既有行为不变。
- [x] Host seam 回归全绿。

## Testing

- `tests/test_collections_intake.py`：写入进度 → `delete_items` → 重新添加 →
  每集 `consumption_state=unstarted`、`audio_position_sec=0`。
- `./scripts/check.sh --fast`、`python3 scripts/check-docs.py`。

## Out of Scope

- 重新添加时保留旧标题/避免占位标题覆盖；单独处理。
- 改变单个 Item 删除/复活的状态语义。
- UI 增加单独的「重置进度」动作。

## Implementation

- `LibraryService.delete(..., reset_consumption: bool = False)`：在 soft delete 前清空
  消费状态和位置；sync tracking 自动 bump `state_seq`。
- `CollectionService.delete(delete_items=True)` 传入 `reset_consumption=True`。
- 当前合集通过 `SyncService.apply_progress` 逐集写回 unstarted/0 后同步到设备。
- 处理队列的 `llm.invalid_output: empty response` 是运行中的 Host 未加载 17:24 修改后的
  `llm.toml`；重启 Host 并重试后已恢复。README 已说明改 LLM 配置必须重启。
