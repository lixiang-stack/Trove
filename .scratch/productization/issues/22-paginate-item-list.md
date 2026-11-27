# 22 — Item 列表在 10k 规模退化为 O(N)

Status: ready-for-agent
Type: task
Milestone: P3
Blocked by: none
Spec: [spec.md](../spec.md)
Related: [19](19-productization-acceptance.md)

## Context

19 的产品化验收在 10k Item 合成数据上发现：`GET /api/items` 的延迟随库大小线性增长，违反 spec 中“API 读请求 p95 ≤ 200 ms”的 SLO。

实测（2026-11-27，10,118 Items，M1 Pro / Docker）：

| 请求 | p50 | p95 |
| --- | --- | --- |
| `GET /api/items?limit=1` | 3,615 ms | 3,641 ms |
| `GET /api/items?limit=50` | 3,603 ms | 3,630 ms |
| `GET /api/health` | 8.2 ms | 13.0 ms |
| `GET /api/items/{id}` | 5.3 ms | 7.2 ms |
| `GET /api/search?q=人工智能` | 42.2 ms | 75.5 ms |

根因：`web/api/items.py` 先调用 `LibraryService.list_items()` 取出全部未删除 Item，并为每一条构建完整 `ItemBundle`，然后才在 handler 里用 `limit`/`offset` 切片。10k 时每个列表请求都要加载并组装 10k 个 bundle。

## Scope

- 把分页下推到 SQL：在 `adapters/`/`db/` 层实现查询和计数，`LibraryService` 只编排，HTTP handler 只组装响应；`ORDER BY + LIMIT/OFFSET` 只取当前页，`total` 用独立 `COUNT(*)`。
- 保留 `sort`、`state`、`type`、`consumption`、`tag`、`source` 的现有语义；派生状态（run 状态、consumption）需要在不破坏过滤的前提下下推或分两阶段查询。
- 保持 API 响应字段和 Android/契约 fixture 不变。
- 不在本 issue 引入新的搜索后端或向量索引。

## Acceptance Criteria

- [ ] 10k Item 下 `GET /api/items?limit=50` p95 ≤ 200 ms（本机、单进程 API）。
- [ ] `total`、`count`、`offset` 与现有语义一致；分页不重不漏。
- [ ] `state`/`type`/`consumption`/`tag`/`source` 过滤与排序不回归。
- [ ] Android 契约 fixtures、`tests/test_api_contract.py`、`tests/test_library.py`、`tests/test_library_navigation.py` 通过。
- [ ] `./scripts/check.sh` 通过。

## Testing

- 用 `trove bench seed --count 10000` 在临时 `TROVE_HOME` 造数，或复用 acceptance 的 10k 数据。
- 对 `/api/items` 跑 100 次，记录 p50/p95；同时校验首页/中间页/末页。
- 覆盖 `sort=recent_added|recent_consumed`、`state=completed`、`tag`、`source` 组合。
- 既有 `test_library_navigation.py` 与 Android contract fixture 保持绿。

## Out of Scope

- 修改 Android 列表分页 UI；继续使用现有 `limit/offset`。
- 把 `/api/items` 改成游标分页（可作为后续增强）。
- 优化搜索索引布局。

## Notes

- 19 的验收记录和复现命令见 [acceptance.md](../acceptance.md)。
- 这是 19 唯一确认未达标的已测 SLO；搜索 p95（10k）为 75.5 ms，达标。
