# 05 — 增加分层依赖门禁（import-linter）

Status: resolved
Type: task
Milestone: P1
Blocked by: 03
Spec: [spec.md](../spec.md)

## Context

当前分层靠约定和 review 维持：`domain` 不应依赖 `services/adapters/web/db`，`services` 不应依赖 `web/adapters`，`adapters` 不应依赖 `services/web`。随着 stage 拆分和服务化推进，如果没有自动门禁，依赖会慢慢反向渗透，端口边界会失效。

## Scope

- 增加 dev 依赖 `import-linter`，在 `pyproject.toml` 配置 contracts。
- 初始 contracts：
  - `trove.domain` 不依赖 `trove.services`、`trove.adapters`、`trove.web`、`trove.db`。
  - `trove.services` 可依赖 `domain/ports/db/content_package/errors`，不依赖 `web/adapters`。
  - `trove.adapters` 可依赖 `domain/ports/config/errors`，不依赖 `services/web`。
  - `trove.web` 不依赖 `adapters`；对 `db` 的依赖只允许通过 service/health 边界，若现有代码违反则记录 baseline 并在 issue 中说明。
- 把 `uv run lint-imports` 加进 `scripts/check.sh --fast` 和 CI。
- 处理现有违规：优先小改；如果改动大，使用显式 `ignore_imports` baseline，并在 issue/代码注释中标注清理条件，不允许静默放过。
- 更新 `docs/agents/code-map.md` 的 Layers 说明，注明门禁命令。

## Acceptance Criteria

- [x] `uv run lint-imports` 在本地和 CI 通过。
- [x] contracts 覆盖 domain/services/adapters/web 四条边界。
- [x] 故意在 `domain` 里 import `services` 会让检查失败（人工验证一次）。
- [x] 现有违规要么修复，要么有明确 baseline 和清理 issue；baseline 不能包含整层。
- [x] `./scripts/check.sh --fast` 包含 import 检查，且总时长增加可接受。
- [x] `ruff`、`mypy`、现有测试不受影响。

## Testing

- 运行 `uv run lint-imports`。
- 临时制造一个违规 import，确认失败，然后还原。
- 运行 `./scripts/check.sh --fast`。
- CI 上确认新步骤执行。

## Out of Scope

- 把 FastAPI/DB 从 web 层完全隔离；本 issue 只锁住已达成/可低成本达成的边界。
- 引入更多架构工具（dependency-cruiser、pydeps 等）。
- 重写 `web/api/runs.py` 等已知直接读模型的 handler；已有 code map 记录，后续单独处理。

## Notes

- 契约要描述“允许的依赖”，不是“所有 import 都禁止”；避免为了过门禁制造无意义的转发模块。
- 如果 `web/api/health.py` 需要 `db.engine`，允许 `trove.web -> trove.db` 的明确例外，但 services/adapters 的边界不能放宽。

## Implementation

- dev 依赖新增 `import-linter>=2.17`；`[tool.importlinter]` 配置五条 `forbidden` contract：domain、services、adapters、web→adapters、web→db；另加一条 core→entry-point contract，禁止 domain/services/adapters 反向依赖 app/cli/composition/worker 等入口层。
- `services -> adapters` 的唯一违规是 `services/inspect.py` 捕获 `SafeHttpError`。把异常类从 `adapters/safe_http.py` 移到 `trove/errors.py`，`safe_http.py` 继续导入并抛出它，测试与调用点不变。
- `web -> adapters` 允许经组合根间接依赖（`composition.py` 是 composition root），只禁止直接 import；`allow_indirect_imports = true`。
- `web -> db` 保留两个显式 baseline，并在 `pyproject.toml` 注明清理条件：`web.api.health -> db.engine`（FTS5/迁移状态）和 `web.api.runs -> db.models`（已知直接读模型的 handler，code map 已有记录）。清理工作单独跟踪于 [21](21-remove-web-db-baselines.md)。
- `uv run lint-imports` 已加入 `scripts/check.sh --fast` 和 `--full`；CI 的 fast step 复用该脚本，因此新检查在 CI 执行。
- `docs/agents/code-map.md` 的 Layers 段补充门禁命令、四条边界和两个 DB baseline 的清理条件。
- 人工验证：临时在 `domain/items.py` 顶部 import `trove.services.processing`，`lint-imports` 以 5 条 contract 中的 domain 失败退出；还原后 5 kept / 0 broken。

## Comments

- 2026-11-25：从 `Blocked by: 03, 04` 改为 `Blocked by: 03`，与 03 同 PR 落地。04 只是把 `LLMOrganizer` 拆成 workflow/client/prompts；`adapters/llm.py` 当前已经只依赖 `domain/ports/config`，不会挡住本 issue 的四条边界，因此不等 04。
