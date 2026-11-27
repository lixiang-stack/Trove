# 10 — LLM/ASR 外部调用幂等缓存

Status: resolved
Type: task
Milestone: P2
Blocked by: 04, 07
Spec: [spec.md](../spec.md)
ADRs: [0007](../../../docs/adr/0007-deepseek-organization-limits.md)

## Context

`organizing` 失败后重试会重新调用 LLM；`transcribing` 失败或自动重试会重新跑 ASR。用户显式点“重新转写”是另一回事，必须真的重跑。需要区分“自动重试复用结果”和“显式重跑强制刷新”，避免重复计费和重复计算。

## Scope

- LLM：
  - 在 `AiResult` 和 `ai.json` 增加 `input_sha256`；key = `(item_id, prompt_version, model, input_sha256)`。
  - `OrganizationWorkflow` 调用前查最新匹配结果；命中则复用 summary/tags，记录 `cached=true`、cost=0，不调用 LLM。
  - 输入文本、prompt_version、model 任一变化都 miss。
- ASR：
  - transcript 文档/DB 记录 `input_sha256`（audio artifact sha256）和 model。
  - 自动重试时，若同一 audio sha + model 的 transcript 已存在，复用结果，不启动 ASR。
- 显式重跑：
  - `reprocess(from_stage="transcribing")`、`reprocess(from_stage="organizing")`、`--reset-ai-tags` 默认 `force=true`，绕过缓存。
  - 自动 retry/worker 回收默认 `force=false`。
- 指标：cache hit/miss、节省的 tokens、节省的 ASR 秒数；日志记录命中来源。
- 数据迁移：新增列用 Alembic；旧 `AiResult`/transcript 没有 hash 时视为 miss。

## Acceptance Criteria

- [x] 同一文本、prompt、model 自动重试时 0 次 LLM 调用，输出与首次一致。
- [x] 文本/prompt/model 变化时重新调用。
- [x] 同一音频、model 自动重试时 0 次 ASR 调用；显式“重新转写”仍会重跑。
- [x] `--reset-ai-tags` 和 `from_stage=organizing` 强制刷新，不受缓存影响。
- [x] 缓存命中不增加 `AiResult` 成本；指标能区分 hit/miss。
- [x] 旧数据（无 hash）可继续处理，不报错。
- [x] 现有组织/处理测试保持绿。

## Testing

- 单测：key 生成、命中/未命中、force 分支。
- 集成：fake LLM/ASR 记录调用次数；自动重试 vs 显式 reprocess。
- 迁移：旧表无 `input_sha256` 升级后可读写。
- 指标：hit/miss 计数和 cost 断言。

## Out of Scope

- 跨 Item 的语义缓存/向量缓存。
- Prompt A/B 或模型路由。
- 把缓存放到 Redis/外部服务；单机用 SQLite/内容包即可。

## Implementation

- `AiResult.input_sha256` and `ai.json`'s `input_sha256` carry the LLM cache
  key with `(item_id, prompt_version, model)`. `OrganizeStage` reads `ai.json`
  directly and reuses it when the hash, model, and prompt version match; the
  content package remains the source of truth, so a matching package still hits
  even if the `ai_results` index row is missing.
- A cache hit restores `item.summary` and AI tags from `ai.json`, does not call
  the LLM, does not insert a new `AiResult`, and therefore adds no cost. The
  per-run log records `ai cache hit` with saved input/output tokens and cost.
- `transcript.json` records the audio artifact's `input_sha256` and the ASR
  model. `TranscribeStage` reuses it when both match, records the transcript
  artifact, and logs saved ASR seconds; a different audio hash, model, or a
  legacy transcript without a hash is a miss.
- `Run.force` marks an explicit reprocess for the whole Run. `reprocess` sets it
  by default and automatic retries keep it, so `--reset-ai-tags` cannot restore
  old tags from the cache. If a Run is already active, `reprocess` marks that
  Run forced instead of starting a second one; stages that already finished are
  not replayed. `retry`, worker recovery, and normal Runs keep it off.
- `AiResult` and `AiDocument` accept `input_sha256 = NULL`; old rows/files load
  normally and count as misses. Migration `0009_external_call_cache` adds the
  history column; the cache lookup itself reads `ai.json`.
- Unsupported content-package versions are not swallowed as cache misses; the
  stage fails with `storage.package_version` before calling the LLM/ASR.
- Cache hit/miss and saved tokens/seconds are logged and counted in
  `trove.metrics` (`external_cache_hits_total`,
  `external_cache_misses_total`, saved-token/cost/ASR-second counters); ticket
  12 exposes the registry through `/metrics`.
- Tests: `tests/test_stages.py` covers hit, force, package-only hits, changed
  text/prompt/model, changed audio, legacy files, and cache counters;
  `tests/test_organization.py` covers non-force reprocess (0 calls) vs explicit
  reprocess (re-run); `tests/test_retry.py` covers a transient failure followed
  by an automatic retry hitting the cache; `test_database_schema.py` covers the
  legacy-row migration.

## Notes

- 缓存是“避免重复副作用”，不是“让显式重跑失效”；force 语义必须在 API/CLI 文档里写清楚。
- ASR 的 transcript 已经写入内容包；优先从内容包读取 hash，避免再建一张缓存表。
- LLM 结果同时存在 `AiResult` 历史和 `ai.json`；以内容包为准，DB 只做查询索引。

## Comments

- 2026-11-27: Docker 视频验收通过。在真实容器内用会抛错的 transcriber/organizer 调用 stage，ASR/AI 均命中 cache；显式 reprocess 走 bypass。见 [acceptance.md](../acceptance.md)。
