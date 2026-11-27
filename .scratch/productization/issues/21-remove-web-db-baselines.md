# 21 — 移除 Web 直接读 DB 的 import-linter baseline

Status: resolved
Type: task
Milestone: P3
Blocked by: none
Spec: [spec.md](../spec.md)
Related: [05](05-layering-guard.md)

## Context

05 引入 import-linter 时，`trove.web` 仍有两个直接读 DB 的地方：

- `web/api/health.py` → `trove.db.engine`（FTS5 可用性与迁移状态）。
- `web/api/runs.py` → `trove.db.models`（直接读 `Run` / `Item`）。

这两个依赖以显式 `ignore_imports` baseline 记录在 `pyproject.toml`，并在
`docs/agents/code-map.md` 注明清理条件。baseline 只允许这两个模块对 DB 的
直接依赖，不允许整层放行；本 issue 负责最终移除它们。

## Scope

- 把 `web/api/runs.py` 的 Run/Item 读取移到 service（例如扩展
  `ProcessingService` 或新增只读查询方法），HTTP handler 只做响应组装。
- 评估 `web/api/health.py` 是否继续需要直接访问 `db.engine`；如果健康检查
  属于明确的运维边界，保留并记录为永久例外，否则移到 service/health 模块。
- 删除 `pyproject.toml` 中不再需要的 `ignore_imports`；同步更新
  `docs/agents/code-map.md` 的 Layers 段。
- 保持 API 响应和现有测试不变。

## Acceptance Criteria

- [x] `pyproject.toml` 的 web→db contract 不再包含 `web.api.runs` baseline。
- [x] `web.api.health` 要么移除 baseline，要么在 issue 和代码中明确记录为永久例外。
- [x] `uv run lint-imports` 通过。
- [x] `./scripts/check.sh --fast` 通过，API 契约测试不回归。

## Testing

- `uv run lint-imports`。
- `uv run pytest -q tests/test_api_contract.py tests/test_processing.py tests/test_host_seam.py`。
- `./scripts/check.sh --fast`。

## Out of Scope

- 重写其它 web handler 或改变 API 形状。
- 放宽 services/adapters/domain 的边界。

## Notes

- 本 issue 只做 baseline 清理；05 的边界不因等待本 issue 而放宽。

## Implementation

- `LibraryService.run_detail` 读取 Run/Item、组装 bundle 和 run payload；`web/api/runs.py` 只做响应组装。
- `ProcessingService.cancel` 现在对不存在的 Run 抛出 `RunNotFoundError`，取消 handler 直接使用返回的 Run，不再预读 DB。
- 新增 `services/health.py` 汇总迁移状态和 FTS5，`web/api/health.py` 只调用 service。
- `pyproject.toml` 的 web→db contract 改为无 basline 的 `Web does not depend on the database`；`docs/agents/code-map.md` 同步更新。
- 验证：`uv run lint-imports` 6 kept / 0 broken；`test_api_contract.py`、`test_processing.py`、`test_host_seam.py`、`test_processing_recovery.py` 通过。

## Comments
