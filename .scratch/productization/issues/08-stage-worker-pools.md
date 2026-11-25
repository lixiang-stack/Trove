# 08 — 按阶段 worker 池与并发配置

Status: ready-for-agent
Type: task
Milestone: P2
Blocked by: 07
Spec: [spec.md](../spec.md)

## Context

StageTask 让任务可以按阶段领取，但还需要运行形态：下载、ASR、整理、索引的资源特征不同，不能共用同一个串行循环。目标是让长 ASR 不再阻塞下载，同时保持默认单 worker 行为兼容。

## Scope

- CLI：`trove worker` 增加 `--pool`（可重复）或 `--stages`：
  - `all`（默认，保持现有行为）、`download`、`asr`、`llm`、`index`。
  - 每个 pool 映射到 stage 集合；未知 stage 直接报错。
- 并发：每个 pool 支持 `--concurrency N`；默认 `download=3`、`asr=1`、`llm=2`、`index=1`。
  - 使用线程池执行 IO 阶段；每个任务独立 session；ASR 仍走子进程，内存上限由并发数控制。
  - 索引池强制单写者，避免 SQLite 写竞争。
- 配置：`TROVE_WORKER_POOLS`、`TROVE_ASR_CONCURRENCY` 等环境变量；非法值启动时失败并给出修复提示。
- 优雅停机：SIGTERM 后停止领取新任务，等待当前任务完成或释放租约；超时后强制退出，由 reaper 回收。
- 部署模板：
  - `deploy.py` 支持按 pool 生成 launchd agent（至少 `all` 和 `asr` 两种）。
  - Docker Compose 支持 `worker` 与 `worker-asr` 等服务（与 11 联动，先提供配置示例）。
- 健康/指标：每个 pool 暴露当前并发、队列深度、正在处理的 task（指标由 12 接入）。

## Acceptance Criteria

- [ ] `trove worker --pool download` 只领取下载阶段；`--pool asr` 只领取转写阶段。
- [ ] 默认 `trove worker` 行为与当前一致（all，串行或默认并发）。
- [ ] 一个慢 ASR 任务不会阻塞下载池领取新任务（集成测试用 fake slow transcriber）。
- [ ] `--concurrency` 生效，且 index pool 始终单写者。
- [ ] SIGTERM 后不丢任务：完成的提交，未完成的释放租约/重新入队。
- [ ] 非法 pool/并发配置启动失败，错误信息可读。
- [ ] launchd 和 Compose 示例可启动对应 pool。
- [ ] 现有 worker/processing 测试全绿。

## Testing

- 集成：两个 pool 同时跑，fake download 快、fake ASR 慢，断言下载先完成。
- 并发：同一 pool N 个任务；断言不超过配置并发。
- 停机：发送 SIGTERM，断言 running task 被释放或完成，队列无丢失。
- 配置：非法值、空值、重复 pool。
- 回归：默认 `all` 模式跑现有 host seam。

## Out of Scope

- 多机 worker、分布式锁、Kubernetes。
- 按用户/租户配额。
- ASR 模型常驻池/GPU 调度（15）。
- 独立服务抽取（15–17）。

## Notes

- 线程池 + SQLAlchemy sessionmaker 可行，但要确保每个任务独立 session，不跨线程共享 Session。
- ASR 子进程已经是进程隔离；先不要引入新的进程管理框架。
- 默认并发要保守；M1 Pro 上 ASR 并发 2 可能触发内存压力，先 1。
