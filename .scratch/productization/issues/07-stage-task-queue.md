# 07 — StageTask 队列：租约、心跳、回收

Status: resolved
Type: task
Milestone: P2
Blocked by: 03
Spec: [spec.md](../spec.md)

## Context

当前 worker 一次领取整条 Run，然后在进程内顺序执行所有 stage；`RunStep` 只是记账，不是可领取的任务。这导致长 ASR 阻塞后续 Item，也无法按阶段分池。需要把阶段执行变成可领取、可租约、可回收的 StageTask，同时保留 `Run` 作为 API/UI 的聚合根。

## Scope

- 复用/升级 `run_steps` 为 StageTask（避免新增重复表）：
  - 新增 `lease_until`、`worker_id`、`available_at`、`max_attempts`、`priority`（默认 0）。
  - `state` 使用 `queued/running/completed/failed/dead/cancelled`；现有 `attempt` 保留。
- `RunCoordinator`：
  - 创建 Run 时只入队第一个 stage。
  - 一个 stage 完成后入队下一个 stage；所有 stage 终态后汇总 Run。
  - 保留 `uq_runs_active_item`：同一 Item 最多一个 active Run。
- 领取：
  - `claim_next(stages, worker_id)` 原子地把一条 queued 且依赖已满足的 task 标为 running，写 `lease_until`/`worker_id`。
  - 领取条件包含 `available_at <= now`，避免退避中的任务被提前拿走。
- 租约：
  - worker 定期续租；reaper 周期性把过期 running task 重新入队（attempt 增加，超过 `max_attempts` 进 dead）。
  - 进程崩溃后不需要等 worker 启动才回收；reaper 可在 API/worker 任一侧运行。
- 取消：`cancel_requested_at` 在 stage 边界和长循环检查点生效；running task 释放租约并标 cancelled。
- 迁移：现有 Run/RunStep 数据映射到新状态；active Run 重新入队，completed 保持 completed。

## Acceptance Criteria

- [x] 两个 worker 并发领取同一队列时拿到不同 task；同一 task 不会被执行两次。
- [x] 过期租约在 reaper 周期内重新入队；超过 `max_attempts` 进入 dead。
- [x] 阶段依赖正确：前一个 stage 未完成时，后一个 stage 不会被领取。
- [x] Run 的最终状态、step 历史、错误码与现有 API/UI 兼容。
- [x] 取消在 queued/running 两种状态下都能生效；running 任务释放租约。
- [x] 迁移后旧库可正常启动，active Run 能继续处理。
- [x] 现有 `test_processing.py`、`test_processing_recovery.py` 全绿。

## Testing

- 并发测试：多线程/多进程同时 `claim_next`，断言唯一领取。
- 租约测试：注入 clock，推进时间，触发 reaper，断言 requeue/dead。
- 依赖测试：只有 downloading 完成后 extracting_audio 才可领取。
- 崩溃测试：kill worker，等 reaper，断言任务恢复。
- 迁移测试：预置旧 schema 的 Run/RunStep，升级后断言状态和可执行性。

## Out of Scope

- 按阶段 worker 池与并发配置（08）。
- 自动重试策略/退避/死信 UI（09）。
- 外部 LLM/ASR 幂等缓存（10）。
- 多机分布式队列；本 issue 只保证单机 SQLite。

## Implementation

- `run_steps` is now the StageTask table: added `lease_until`, `worker_id`,
  `available_at`, `max_attempts`, and `priority`; `state` now includes
  `queued`/`running`/`completed`/`failed`/`dead`/`cancelled`.
- `RunCoordinator.create_run` enqueues only the first stage. Claiming atomically
  moves one available, dependency-satisfied task to `running` and writes the
  worker lease. Completing a stage enqueues the next one; the Run is summarized
  only when all stages are terminal.
- `Run.state` is now only `queued`/`completed`/`failed`/`cancelled`. The API and
  Item views still derive the current stage from the running task, so existing
  clients keep seeing `downloading`, `transcribing`, etc.
- `reap_expired` requeues expired leases as a new attempt. The attempt that lost
  its lease is kept as `failed` (`run.lease_expired`) and the final attempt
  becomes `dead` (`run.dead`), failing the Run without silently retrying.
- Completion and failure are fenced by `worker_id`, `running` state, and an
  unexpired lease. A worker that finishes after losing its lease rolls back and
  lets the requeued attempt win, so one stage cannot be completed twice.
- HTTP podcast/EPUB downloads check `should_cancel` per chunk; yt-dlp already
  polls it through `run_command`.
- `trove worker` renews leases through the heartbeat thread and runs the reaper
  every `TROVE_WORKER_REAPER_INTERVAL_SECONDS` (default 5s). Lease length is
  `TROVE_WORKER_LEASE_SECONDS` (default 25s) and the heartbeat is
  `TROVE_WORKER_HEARTBEAT_SECONDS` (default 5s); a lease that is not longer than
  the heartbeat is rejected at startup. `recover_active_runs` repairs
  active Runs that have no claimable task (for example after migration).
- Cancelling a queued Run marks its queued task cancelled; cancelling a running
  one sets `cancel_requested_at`, and the stage releases its lease when it stops.
  `run.reclaimed`, `run.lease_expired`, and `run.dead` have user-facing labels.
- Migration `0007_stage_tasks` backfills active Runs with a queued next-stage
  task and maps old stage-named Run states to `queued`; completed Runs stay
  completed.
- Tests: `tests/test_stage_tasks.py` covers concurrent claims, `available_at`,
  dependencies, lease expiry/dead, and lease renewal; `test_database_schema.py`
  covers the migration backfill. Existing processing and recovery tests remain
  green, with the restart test now exercising lease reaping.

## Notes

- SQLite 的原子领取可以用 `UPDATE ... WHERE id = (SELECT ... ) AND state='queued' RETURNING ...`，或用短事务 select + 条件 update；必须用 rowcount 判断成功。
- 不要把 `Run.state` 继续当作 stage 名；Run 状态只保留 queued/completed/failed/cancelled，stage 进度看 task/step。
- reaper 频率和租约时长放到 config，默认值按最长 stage 设置；不要用固定魔法数散落在代码里。
