# 09 — 阶段级自动重试、退避与死信

Status: ready-for-agent
Type: task
Milestone: P2
Blocked by: 07
Spec: [spec.md](../spec.md)

## Context

当前失败后 Run 直接进入 failed，重试需要用户手动触发；没有重试次数、退避或死信。下载网络抖动、LLM 429/5xx、临时磁盘错误都会让用户看到失败并手动重试。StageTask 已经提供 `attempt`/`available_at`，现在需要策略和状态。

## Scope

- 定义每个 stage 的默认策略：
  - 可重试错误：`download.network`、`llm.failed`（429/5xx/timeout）、`storage.error` 中可识别的临时错误。
  - 不可重试错误：`download.unsupported`、`download.login_required`、`download.geo_restricted`、`epub.invalid`、`epub.drm`、`epub.fixed_layout`、`llm.not_configured`、`asr.not_configured`、`asr.model_missing`。
  - ASR `asr.failed` 默认不自动重试（可能是模型/音频问题），除非错误明确标记为 transient。
- `max_attempts`：下载/整理默认 3，ASR 默认 1，索引默认 2；可按 stage 配置。
- 退避：指数退避 + jitter，例如 30s、2m、10m；写 `available_at`，不阻塞 worker。
- 死信：超过上限进入 `dead`，保留最后错误码/消息；API/UI 显示“需要人工处理”，支持手动 retry（重置 attempt/available_at）。
- 取消：取消后不再自动重试。
- 日志/指标：每次重试记录 attempt、delay、error_code；指标 `stage_retries_total`、`stage_dead_total`。
- 与幂等缓存（10）配合：自动重试优先复用已完成的外部调用结果；显式 reprocess 不走缓存。

## Acceptance Criteria

- [ ] 可重试错误按策略重试，最终成功；attempt 和日志正确。
- [ ] 不可重试错误立即失败，不消耗重试次数。
- [ ] 超过 `max_attempts` 进入 dead；手动 retry 能重新入队并成功。
- [ ] 退避使用 `available_at`，不会忙等；测试用注入时钟，不真实 sleep。
- [ ] 取消后不再重试。
- [ ] 每个 stage 的策略可配置，默认值有文档。
- [ ] 现有失败/取消/重试测试保持绿。

## Testing

- fake port 注入 transient/permanent 错误，断言调用次数和最终状态。
- 注入 clock，断言 available_at 序列和 jitter 范围。
- 手动 retry：dead → queued → completed。
- 取消：running/queued 两种状态。
- 回归：`test_processing.py`、`test_processing_recovery.py`。

## Out of Scope

- 熔断器、跨服务重试、全局速率限制。
- 自动重试 ASR 模型缺失/配置错误。
- 死信管理 UI 的完整设计；先提供 API + 现有 Item 页面提示即可。

## Notes

- 错误分类放在一个集中映射里（例如 `domain/retry.py` 或 `services/retry.py`），不要散落在每个 stage。
- 重试日志要包含 `run_id`/`task_id`/`stage`/`attempt`/`error_code`/`delay_ms`。
- 不要让自动重试掩盖配置错误；不可重试错误要直接暴露给用户。
