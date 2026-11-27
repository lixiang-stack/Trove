# Trove 产品化验收记录

Status: in progress
Date: 2026-11-27
Spec: [spec.md](spec.md)
Issues: [issues/](issues/)

## 环境

- macOS（Apple Silicon / arm64）+ Docker Desktop。
- 分支：`deploy-acceptance`，基于 `main` 的 `c3e4d65`；镜像 `trove:local` 从该 worktree 构建，包含 ASR。
- 服务：`api`、默认 `worker`；分池模式用 `docker compose --profile pools` 启动 `worker-download / worker-asr / worker-llm / worker-index`。
- 数据卷：`trove_trove-data`；验收后 `items=10`（合集前 10 集）、`runs=22`、`ai_results=22`、`collections=1`。
- ASR：FunASR `paraformer-zh`，CPU。
- LLM：本地 Ollama `qwen3.5:4b`，`http://host.docker.internal:11434/v1`，`prompt_version=organize-2`。
- 认证：验收期间临时设置测试密码；结束后恢复原 `state.toml`，并验证旧 session 和临时密码均已失效。
- 容器以 uid/gid `10001(trove)` 运行；`config.toml`、`state.toml` 为 `0600`。

## 测试输入

| 字段 | 值 |
| --- | --- |
| URL | `https://www.bilibili.com/video/BV1MLqDYxEpN?p=1` |
| 标题 | `2025年曾仕强道德经功成不居高清版 全100讲 p01 第1集 天地之始` |
| 作者 | `冉子学院` |
| 时长 | `901.844667s`（15m02s） |
| 平台 | Bilibili |
| Item ID | `48e1d08e-7998-4a24-9baa-4ecef2cbd710` |

## Issue 结果

只验收已实现的 issue：01–11、13。12、14–18、20、21 未实现或处于 gated / needs-triage；19 仍为进行中。

| Issue | 结果 | 证据 |
| --- | --- | --- |
| 01 ADR/SLO | 通过 | `docs/adr/0014-...` 与 spec SLO 表存在；15 分钟音频最终 5m22s 完成（含故障注入与人工等待），低于 15 分钟目标。 |
| 02 API v1 / 幂等 | 通过 | 创建 201；同 key/body 重放 201 + `Idempotency-Replayed: true`；同 key/异 body 409 `idempotency.key_reused`；无 key 重复创建 200 + `deduplicated: true`；未登录 401 `auth.required`；重启后重放仍命中。 |
| 03 拆分 ProcessingService | 通过 | 运行日志按 stage 记录；`RunCoordinator` / `services/stages/*` 结构测试全绿。 |
| 04 拆分 LLM organizer | 通过 | 本地 Ollama 生成摘要和 3 个 tag；`input_tokens=2102`、`output_tokens=132`、`cost_usd=0.000644`（首次）。 |
| 05 分层门禁 | 通过 | `lint-imports`: 6 kept / 0 broken。 |
| 06 manifest / schema_version | 通过 | `manifest.json` schema_version=1，含 audio/transcript/ai 三个 artifact 的 sha256/size/mime；`trove package verify` 通过；导出 zip 含 manifest。 |
| 07 StageTask 队列 / 租约 | 通过 | 初始 run 的 transcribing attempt 1 在 worker 被杀后以 `run.lease_expired` 失败并重排 attempt 2；最终 run completed。 |
| 08 worker 池 / 并发 | 通过（修复后） | 四个池分别领取 download/asr/llm/index；health 同时列出四个 pool；发现并修复 heartbeat 文件名跨容器冲突。 |
| 09 重试 / 退避 / 死信 | 部分通过 | 租约过期触发 attempt 2 并在完成 ASR 后继续；死信未在真机重复注入，由现有单元测试覆盖。 |
| 10 外部调用缓存 | 通过 | 用“会抛错的 transcriber/organizer”直接调用 stage：ASR/AI 均 cache hit，未发生外部调用；显式 reprocess 日志为 `ai cache bypassed: explicit reprocess`。 |
| 11 Docker Compose 打包 | 通过 | 分支镜像重建；`down` / `up -d` 后 Item、搜索、manifest 保留；API 健康；非 root；doctor 通过。 |
| 12 指标 / tracing | 未实现 | 无 Prometheus / OpenTelemetry；不在本次范围。 |
| 13 升级 / 回滚 / doctor | 部分通过 | `doctor --json` ok；`/api/health` 含 version/build/commit/time；在线备份生成并校验 `items=1/runs=3/ai_results=3`；未重复完整 rollback 演练。 |
| 14–18 | 未实现 / gated | 研究或 Phase 4 服务抽取。 |
| 19 整体验收 | 进行中 | 本报告覆盖单集视频 + 合集前 10 集链路、Docker、分池、故障恢复、缓存、幂等、manifest、doctor/备份；EPUB/播客、Android、100 条容量、观测、launchd、完整回滚仍待做。 |
| 20–21 | 未实现 | ASR warm pool / Web DB baseline 清理。 |

## 处理时间线

初始 run `8cbe2747-5b50-4cb9-8851-f69569465bd2`：

| UTC 时间 | 事件 |
| --- | --- |
| 04:43:52.450 | Item 创建 |
| 04:43:52.605 | downloading 完成 |
| 04:43:55.383 | extracting_audio 完成 |
| 04:44:04.221 | transcribing attempt 1 开始 |
| 04:44:33 | 手工 `docker kill worker-asr` |
| 04:44:56.361 | lease 过期，transcribing attempt 1 标记 `run.lease_expired` |
| 04:45:25.635 | attempt 2 `available_at`（退避约 29s） |
| 04:47:12.297 | 默认 worker 接管 attempt 2 |
| 04:49:00.819 | ASR attempt 2 完成（108.5s，RTF 0.120） |
| 04:49:14.136 | organizing 完成（11.3s） |
| 04:49:14.166 | indexing 完成，run completed |

从创建到完成 321.7s（含故障注入和约 2 分钟人工等待）；纯处理时间约 2m30s。15 分钟音频满足 SLO（≤15 分钟）。

显式 reprocess：

- `from_stage=organizing`：202 + 新 run `9881ff96-...`，`force=1`，8.1s 完成；`ai_results` 从 1 增加到 2，新增成本。
- `from_stage=transcribing`：202 + 新 run `3195d677-...`，`force=1`，ASR 100.5s（RTF 0.111），总 112.5s 完成；worker 日志显示 `ai cache bypassed: explicit reprocess`。

## 分池与 heartbeat

分池模式下四个 worker 都运行在各自容器里，PID 都是 `7`。旧实现用 `cache/worker-<pid>.json`，导致：

- 四个 worker 只有 3 个 heartbeat 文件，`/api/health` 的 pool 列表在 download/asr/llm/index 之间闪烁；
- 临时文件 `.tmp` 同名，`worker-asr` 在 `os.replace` 时抛出 `FileNotFoundError`，触发容器重启。

修复：

- heartbeat 文件名改为 `worker-<hostname>-<pid>.json`；
- payload 增加 `hostname`；
- lease 的 `worker_id` 也包含 hostname（截断到 16 字符，保证 `String(64)` 内）；
- doctor / 内置 worker 存活检查在 hostname 不同时信任 fresh heartbeat，不再用其他容器命名空间里的 PID 误判；
- 增加回归测试：不同 hostname、相同 PID 不再冲突；跨 host fresh heartbeat 被信任。

修复后分池验证：

- `cache/` 下出现 4 个独立 heartbeat 文件，health 同时列出 `download/asr/llm/index` 四个 pool；
- run 日志中的 claim 分别来自 `worker-<hostname>-7-asr-0`、`...-llm-0`、`...-index-0`；
- 无 worker 启动/运行错误，`doctor` 在 api 容器内也返回 `worker ok`。

## 内容包、搜索与播放

- 内容包目录：`audio.m4a`（7,492,450 B）、`transcript.json`（34,121 B，263 段）、`ai.json`、`source.json`、`manifest.json`。
- `manifest.json` 三个 artifact 的 sha256/size 与 `trove package verify` 一致。
- 搜索 `道德经`、`老子` 均返回该 Item。
- `/api/items/{id}/audio` 支持 Range：`206`、`Content-Range: bytes 0-1023/7492450`、`ETag` 为 audio sha256。
- `/api/export` 返回 7.3 MB zip，含 `source.json`、`audio.m4a`、`transcript.json`、`ai.json`、`manifest.json`、`index.md`。
- 摘要由本地 LLM 生成；重跑 organizing 后摘要/tag 会变化（模型非确定性），不是缓存 bug。

## 缓存验证

在真实容器内直接调用 stage，并把 transcriber/organizer 换成“被调用就抛错”的 fake：

- ASR：`transcript cache hit: audio_sha256=14c4... model=paraformer-zh; saved_asr_seconds=901.844667 cost=0`。
- AI：`ai cache hit: input_sha256=577e... model=qwen3.5:4b prompt_version=organize-2; cached=true cost=0 saved_input_tokens=2111 saved_output_tokens=112 saved_cost_usd=0.00063812`。

说明 `transcript.json` / `ai.json` 的 hash、model、prompt_version 键生效，且 cache hit 不发生外部调用。

## Docker / 运维

- `docker compose up -d --build` 从 worktree 构建并启动成功；API `healthy`。
- `docker compose down`（不带 `-v`）后 `up -d`：Item、run、搜索、manifest 全部保留。
- `docker compose exec api trove doctor --json`：`ok=true`，permissions/DB/FTS5/password/port/ffmpeg/ffprobe/yt-dlp/asr/content_packages/worker/disk 均正常。
- `/api/health`：`api_version=0.1.0`，build 字段存在（commit/build_time 为 `unknown`，因为本次未传 build args），DB revision `0009_external_call_cache`。
- 在线备份：`trove-0009_external_call_cache-...db`，`0600`，544,768 B；备份内 `items=1`、`runs=3`、`ai_results=3`、revision `0009`。

## 合集验收（前 10 集）

- URL：`https://www.bilibili.com/video/BV1MLqDYxEpN`
- Collection ID：`23fd8970-cde7-401e-bba3-cda6e84f7c0b`
- 合集标题：`2025年曾仕强道德经功成不居高清版 全100讲`；标题写 100 讲，但 yt-dlp `--flat-playlist` 实际只返回 75 个 part（`playlist_count=75`）。这是上游/yt-dlp 的可见范围，不是 Trove 截断。
- 已有的 p1 Item 被识别为同源 Episode，inspect 返回 `collection.episode_attach` 警告；创建结果：`added=74`、`attached=1`、`run_count=74`，初始合集 `episode_count=75`。
- 当前 API 没有“只导入前 N 集”参数。为了满足“只取前 10 集”，先停 worker，创建合集后删除 `collection_index` 11–75 的 65 个 Item，再启动分池。删除发生在下载前，被删集数没有下载/转写；最终合集 `episode_count=10`。
- 分池运行：`download=3`、`asr=1`、`llm=2`、`index=1`。p1 已在此前完成，p2–p10 共 9 集新处理。
- 05:12–05:25（约 13 分钟）全部完成：`completed=10`、`failed=0`、`cancelled=0`。
- 总音频时长 `7083.148503s`（118m03s）。单集 ASR `48.78–125.92s`，RTF `0.111–0.141`，全部低于 0.15；organizing `4.77–11.24s`。
- 下载池并发 3：05:12:03 时 download 有 3 个 active、6 个 queued；到 05:12:43 下载/抽取已全部完成，ASR 继续串行运行。长 ASR 期间下载没有被阻塞。
- 下载完成后 Episode 标题从 `Episode N` 更新为真实分集标题（如 `p08 第8集 上善若水`）。
- 首轮完成后 10 集使用一致的 collection tag 词表：`Tao Te Ching`、`Zeng Shiqiang`、`Taoism`。
- 执行 `trove collection reprocess <id> --from-stage organizing --reset-ai-tags`：删除 30 条 AI tag link，排队 10 个 organizing run，约 70s 完成；`ai_results` 12→22，总成本 `$0.013218`、input 43,769、output 2,293 tokens。显式重跑绕过了 AI cache。
- 重跑后 tags 出现分叉（`philosophy/tao-te-ching/wu-you` vs `Laozi/Non-action/Natural Order` 等）。原因是两个 LLM worker 并发整理，后完成的 Item 才能看到前面新增的 tag；记录为观察项，不阻塞验收。
- 搜索：`道德经`/`老子` 命中 10 集，`无为` 3 集，`上善若水` 仅 p8。
- 导出：57,697,491 B zip，51 个 entry，10 个 item 目录、10 个 `manifest.json` 和 `index.md`。
- `trove package verify` 对 p2/p10 通过；`source.json` 带 collection 元数据（index 1/2/10）；p10 音频 Range 返回 206、ETag 为 audio sha256。
- Doctor `ok=true`；四个 pool 的 heartbeat 同时可见；批次期间 worker 日志无 traceback/FileNotFound；library 57 MB，磁盘剩余 51.7 GB。

## SLO 快照

| SLO | Target | 本次观测 |
| --- | --- | --- |
| 30 分钟音频入库到可搜索 p95 | ≤ 15 分钟 | 单集 15 分钟音频 5m22s（含故障注入和人工等待）；合集 10 集（118 分钟音频，9 集新处理）约 13m。 |
| ASR RTF（M1 Pro 参考机） | ≤ 0.15 | 单集 0.111 / 0.120；合集 10 集 0.111–0.141。 |
| API 读请求 p95 | ≤ 200 ms | 本机 health/items/search 均为个位数到几十 ms（未做 10k Item 压测）。 |
| 搜索 p95（10k Item） | ≤ 300 ms | 10 Item 合集查询 1–10 条结果；未做 10k 规模。 |
| worker 崩溃恢复 | ≤ 30 秒 | lease 在 kill 后约 24s 被回收并重排；下一 attempt 退避约 29s。 |
| 自动重试重复外部调用 | 0 | ASR/AI cache hit 验证为 0 次外部调用。 |
| 全新安装（不含模型下载） | ≤ 10 分钟 | 本次为已有卷升级/重建，未重新计时全新安装。 |
| 非源错误导致 Run 失败率 | < 2% | 本样本 0 个非源错误失败（1 次 lease 重试为注入故障）。 |

## 遗留与后续

1. **未做真机覆盖**：EPUB、播客、Android 契约、100 条容量、launchd、完整 rollback 演练、Prometheus/tracing（issue 12）。
2. **合集不能只导入前 N 集**：当前 `POST /api/collections` 会创建所有可发现 Episode；本次先停 worker、创建 75 集、删除 11–75，再启动 worker，未下载被删集数。若这是常见需求，建议新增 `limit` 或 Episode 选择参数。
3. **合集分集数与标题不一致**：Bilibili 标题写 100 讲，但 yt-dlp 只返回 75 个 part；这是上游/yt-dlp 可见范围，记录为外部数据差异。
4. **合集重跑 tag 分叉**：`--reset-ai-tags` 后两个 LLM worker 并发整理，早期 Item 看不到后续新增 tag；标签词表不一致。若要求强一致，可考虑先收敛词表再批量整理。
5. **死信未在真机重复注入**：lease 重试已验证；死信路径由 `tests/test_retry.py` / `tests/test_stage_tasks.py` 覆盖。
6. **`language` 为空**：transcript 有分段，但 `language` 为 null；FunASR 未返回语言，不影响播放/搜索，记录为观察项。
7. **摘要语言**：中文音频会得到中文或英文摘要（取决于本地模型输出）；是否要求摘要跟随内容语言，需要在产品层明确，不是本次验收阻塞项。
8. **`docker kill` 语义**：手工 kill 被 Compose 视为手动停止，未自动重启；真实崩溃由 `restart: unless-stopped` 处理。故障注入时因此人工切换到默认 worker。
9. **旧 heartbeat 文件**：升级后旧 `worker-<pid>.json` 仍留在 cache，15s 后变为 stale；7 天后由 prune 清理，不影响新逻辑。
