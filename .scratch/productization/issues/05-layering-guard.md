# 05 — 增加分层依赖门禁（import-linter）

Status: ready-for-agent
Type: task
Milestone: P1
Blocked by: 03, 04
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

- [ ] `uv run lint-imports` 在本地和 CI 通过。
- [ ] contracts 覆盖 domain/services/adapters/web 四条边界。
- [ ] 故意在 `domain` 里 import `services` 会让检查失败（人工验证一次）。
- [ ] 现有违规要么修复，要么有明确 baseline 和清理 issue；baseline 不能包含整层。
- [ ] `./scripts/check.sh --fast` 包含 import 检查，且总时长增加可接受。
- [ ] `ruff`、`mypy`、现有测试不受影响。

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
