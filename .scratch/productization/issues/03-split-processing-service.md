# 03 — 拆分 ProcessingService 为 RunCoordinator 与 Stage Handlers

Status: ready-for-agent
Type: task
Milestone: P1
Blocked by: none
Spec: [spec.md](../spec.md)

## Context

`src/trove/services/processing.py` 约 1000 行，混合了队列操作、Run 状态机、六个阶段的业务逻辑、产物安装、标签词表和临时目录清理。它让新增阶段、测试单阶段、按阶段分池都变得困难。Phase 2 的 StageTask 队列需要一个清晰的 coordinator 和可独立执行的 stage handler，所以先做行为不变的结构拆分。

## Scope

- 保留 `ProcessingService` 的公开方法（`create_run`、`claim_next`、`process`、`retry`、`reprocess`、`cancel`、`cancel_item`、`reclaim_stale_runs`、`heartbeat`、`mark_worker_failure`），内部改为委托。
- 新增 `services/stages/`：
  - `base.py`：`StageHandler` 协议、`StageContext` 复用、阶段结果类型（只在确有需要时引入）。
  - `download.py`、`audio.py`、`transcribe.py`、`extract_text.py`、`organize.py`、`index.py`。
- 新增 `services/artifacts.py`：安装、记录、替换、清理产物的逻辑从 `ProcessingService` 移出。
- `RunCoordinator` 负责：创建/领取 Run、按 `stages_for()` 顺序执行、开始/完成/失败/取消 step、重试、回收、心跳。
- 阶段 handler 只依赖传入的 `Session`、`Item`、`SourceDocument`、`StageContext` 和所需 port；不直接打开新 session，不依赖 web/worker。
- 保持现有错误码、日志文案和事务边界不变；不改变目录布局和内容包格式。

## Acceptance Criteria

- [ ] `services/processing.py` 降到 300 行以内；每个 stage 文件 250 行以内。
- [ ] 六个阶段都能被单独实例化并用 fake port 测试，不启动 worker/HTTP。
- [ ] 现有 `test_processing.py`、`test_processing_recovery.py`、`test_host_seam.py` 全绿。
- [ ] Run/Step 状态、错误码、日志字段、重试/取消/回收行为不变。
- [ ] `ProcessingService` 公开方法签名不变；`composition.py` 和 web 层无需改调用点。
- [ ] 没有新增运行时依赖。
- [ ] `ruff`、`mypy` 通过。

## Testing

- 单阶段测试：download/audio/transcribe/extract_text/organize/index 各用 fake port 覆盖成功、失败、取消。
- 集成：现有 host seam 的 video/EPUB/local audio 全链路。
- 回归：`reclaim_stale_runs`、retry、reprocess、cancel 的现有测试。
- 静态检查：`./scripts/check.sh --fast`。

## Out of Scope

- StageTask 队列、租约、worker 池（07/08）。
- 自动重试/退避/死信（09）。
- LLM/ASR 幂等缓存（10）。
- 修改阶段顺序、错误码或 API 响应。

## Notes

- 优先“移动代码 + 委托”，不要顺手重写业务逻辑；每一行改动都要能追溯到拆分。
- 如果某个 helper 同时被多个 stage 使用，放到 `services/stages/base.py` 或 `services/artifacts.py`，不要放回 `ProcessingService`。
- 保持 `StageContext` 不变，避免同时改 ports 和测试。
