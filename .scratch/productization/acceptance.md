# Trove 产品化验收记录

Status: complete
Date: 2026-11-27
Commit: `59be2d050a8cef40b385a65f051c43a47764cc69`（`productization-acceptance` 分支）
Spec: [spec.md](spec.md)
Issues: [issues/](issues/)

本记录合并三次验收：

- Pass 1：Docker 视频链路、分池、lease 恢复、缓存、幂等、manifest、doctor/备份。
- Pass 2：Bilibili 合集前 10 集、批量下载、collection reprocess、导出、搜索。
- Pass 3：当前 commit 上的 Docker/launchd 全新安装、EPUB/播客/视频三链路、故障注入、100 条容量、10k 搜索、Prometheus/Grafana/OTel、升级/回滚、Android 回归。

Pass 1/2 的原始证据保留在下方；Pass 3 使用独立 `trove-acceptance` Compose project 和独立卷，未修改 Pass 1/2 数据。

## 环境

### 主机

- macOS 14.6.1（23G93），Apple M1 Pro / arm64，Docker Desktop 29.5.2。
- Python 3.12.14；uv 管理虚拟环境；FFmpeg/ffprobe 5.1.9（容器内）。
- 磁盘：验收结束时剩余约 126 GB。
- 分支 `productization-acceptance`，基于 `main` 的 `59be2d0`。
- 镜像 `trove:acceptance`，`sha256:8f7af0c6...`，构建参数 `commit=59be2d050a8c`，`build_time=2026-11-27T07:35:53Z`。

### Docker 路径

- Compose project：`trove-acceptance`；端口 `127.0.0.1:18765`。
- 全新命名卷：`trove-acceptance_trove-data`；首次 `up` 前只预置 ASR 模型缓存（1.2 GB，模型下载不计入安装 SLO）。
- 服务：`api`、默认 `worker`；功能/容量阶段切换为 `worker-download`、`worker-asr`、`worker-llm`、`worker-index`。
- ASR：FunASR `paraformer-zh`，CPU；LLM：本地 mock OpenAI-compatible 服务（`host.docker.internal:18080`），用于确定性验收；真实 Ollama `qwen3.5:4b` 链路见 Pass 1。
- 认证：验收专用密码；结束时删除整个验收卷。

### launchd 路径

- 临时 home：`$HOME/.cache/trove-acceptance/launchd-home`；端口 `127.0.0.1:18766`。
- 临时 LaunchAgents 目录：`$HOME/.cache/trove-acceptance/LaunchAgents`，未写入 `~/Library/LaunchAgents`。
- `uv sync --extra asr` 已预热依赖；ASR 模型通过 `MODELSCOPE_CACHE` 复用验收缓存。模型下载不计入安装 SLO。
- 安装后 `doctor --json` 全绿；结束后 `trove service uninstall`，未删除 `~/Trove`。

### 测试数据

- 真实视频：Bilibili `BV1MLqDYxEpN?p=1`，901.844667 s，标题 `2025年曾仕强道德经功成不居高清版 全100讲 p01 第1集 天地之始`，作者 `冉子学院`。
- 真实播客：NPR The Indicator `https://feeds.npr.org/510325/podcast.xml`，episode `Will AI take my job? Ask an economist!`，224.94 s。
- EPUB：本地 `tests/fixtures/aesop.epub`；URL 使用 GitHub 上公开的 IDPF `accessible_epub_3.epub`（4.05 MB）。
- 100 条容量：`aesop.epub` 的 100 个唯一变体（每个 3.3 KB，追加唯一 `META-INF` 文件改变 checksum）。
- 10k 搜索：`trove bench seed --count 10000`，最终 API `total=10,118` Items。

## 全新安装

### Docker Compose（干净卷）

命令（镜像已构建，模型缓存已预置）：

```bash
export TROVE_IMAGE_TAG=acceptance TROVE_HOST_PORT=18765 TROVE_PUBLISH_ADDRESS=127.0.0.1
docker compose -p trove-acceptance up -d
```

| 指标 | 结果 |
| --- | --- |
| 从 `up -d` 到 `/api/health` 200 | **18.52 s** |
| `init` | exit 0 |
| API health | `host`/`database`/`worker` 全 ok，migration `0010_stage_traceparent` |
| 非 root | 容器 uid/gid `10001(trove)`；config/state `0600` |

SLO ≤ 10 分钟，通过。镜像构建时间未计入（发布物为预构建镜像）。

### macOS launchd

```bash
uv run trove --home "$HOME/.cache/trove-acceptance/launchd-home" config init \
  --host 127.0.0.1 --port 18766
TROVE_AGENTS_DIR="$HOME/.cache/trove-acceptance/LaunchAgents" \
  ./scripts/install-launchd.sh --home "$HOME/.cache/trove-acceptance/launchd-home"
```

| 指标 | 结果 |
| --- | --- |
| 从 `install-launchd.sh` 到 `/api/health` 200 | **9.87 s** |
| `launchctl print gui/$(id -u)/com.trove.api` | running，active count 1 |
| `launchctl print gui/$(id -u)/com.trove.worker` | running，active count 1 |
| `doctor --json` | `ok=true`，11 项全 ok（worker 首次心跳后） |
| kill API（SIGKILL）到 health 恢复 | **13.72 s**，新 PID |
| kill worker（SIGKILL）后 heartbeat | 更新为新 PID，`worker status=ok` |
| uninstall | 两个 plist 删除，进程停止；`~/Trove` 未动 |

SLO ≤ 10 分钟，通过。

## 功能链路（Pass 3）

### 视频 URL → ASR → 摘要/tag → 搜索

- `POST /api/items` 201，0.053 s；下载池 3、ASR 1、LLM 2、index 1。
- 运行步骤：

| stage | 耗时 |
| --- | --- |
| downloading | 3.305 s |
| extracting_audio | 8.458 s |
| transcribing | 111.536 s |
| organizing | 0.050 s |
| indexing | 0.016 s |
| 端到端 | **124.523 s** |

- ASR RTF = 111.536 / 901.844667 = **0.1237**（≤ 0.15）。
- 标题/作者/时长正确；摘要和 tags 由 mock LLM 生成；搜索 `道德经`、`Acceptance` 命中。
- `/api/items/{id}/audio` Range 返回 `206`、`bytes 0-1023/7492450`、ETag=audio sha256。
- `trove package verify` 通过。

### EPUB 本地 / URL → 解析 → 摘要/tag → 阅读/搜索

- 本地 `aesop.epub`：201，**1.53 s** 完成；`has_book=true`；`GET /api/items/{id}/book/chapters/0` 返回 4 段正文；搜索 `Aesop` 命中；package verify 通过。
- URL `accessible_epub_3.epub`：201，**3.06 s** 完成；`source_type=epub_url`，`has_book=true`，摘要/tags 正常。

### 播客单集 → 下载 → ASR → 搜索

- NPR The Indicator，224.94 s 单集：201，**61.85 s** 完成。
- 步骤：download 7.73 s、extract 3.06 s、transcribe 48.66 s、organize 0.035 s、index 0.016 s。
- ASR RTF = 48.66 / 224.94 = **0.216**。短音频含固定模型加载开销，不作为 30 分钟音频 SLO 样本；900 s 视频样本为 0.1237。
- `has_audio=true`，transcript 73 段；搜索 `economist` 命中。
- 备注：第一次用本地 fake feed `acceptance-001` 时，mock server 把 `.m4a` 标成 `audio/mp4a-latm`，被下载白名单拒绝（`download.invalid_type`），已修复 mock 的 Content-Type 后改用真实公共 feed。该失败是测试夹具问题，不是产品缺陷。

### 合集 / 批量下载 / 重跑

Pass 2 已在 `deploy-acceptance`（`c3e4d65`）完成：Bilibili 前 10 集入库/分池下载/ASR/整理/索引，collection reprocess、导出和搜索均通过；具体数字见下方“Pass 1/2 细节”的 Pass 2 段，此处不重复。

Pass 3 未重复执行合集批量下载；`c3e4d65..59be2d0` 的差异是 observability/run 读取重构，不修改 collection 入队/下载路径。当前 commit 的单集重跑与取消见下。

### 重跑与取消

- 视频 `POST /reprocess {"from_stage":"organizing"}`：202，1.02 s 完成；run log 有 `ai cache bypassed: explicit reprocess`；`ai_results` 增加。
- 视频 `from_stage=transcribing`：显式重跑 ASR；用于 worker 崩溃注入（见下），attempt 2 完成后 run completed。
- 播客 `from_stage=transcribing` 后立即 `POST /cancel`：run 在 transcribing 阶段变为 `cancelled`，错误 `run.cancelled`；没有继续 organizing/indexing。

### 长 ASR 不阻塞下载/整理/索引

- 视频进入 `transcribing` 后（创建后 13.16 s），创建本地 EPUB。
- EPUB 在 **1.53 s** 内 completed；此时视频仍在 `transcribing`。
- 分池 health 同时列出 `download/asr/llm/index` 四个 pool；下载池并发 3、LLM 2、index 1。

## 故障注入

| 场景 | 注入方式 | 观测结果 | 结论 |
| --- | --- | --- | --- |
| worker 崩溃 / 租约过期 | ASR 运行中 `kill -9` worker PID | attempt 1 `run.lease_expired`；lease 在 **28.5 s** 后回收；退避 32.6 s 后 attempt 2 完成；容器 RestartCount=1 | 自动恢复，无丢任务 |
| API 崩溃 | `kill -9` API PID | **2.68 s** 后 health 恢复；新 PID；16 个既有 Item 保留；RestartCount=1 | 自动恢复 |
| LLM 429 | mock 返回 429 | organizing attempt 1 `llm.failed`，约 30 s 后 attempt 2 完成 | 可重试、退避 |
| LLM 5xx | mock 返回 500 | 同上；429/500 共 2 次失败、最终 0 失败 | 可重试 |
| 死信 | 临时 `organizing` max_attempts=1（重启 API+所有 worker），mock 500 | stage `dead`，run `failed`，错误 `run.dead`；Item 保持可查询 | 死信明确，无静默丢失 |
| 磁盘/权限写失败 | 处理中把 Item 目录 `chmod 500` | `storage.error`（EACCES）立即失败；恢复权限后 `POST /retry` 1.53 s 完成 | 不静默丢任务；EACCES 属永久错误，需人工重试 |
| SQLite busy | 另一连接 `BEGIN EXCLUSIVE` 8 s | `POST /api/items` 等待 **7.126 s** 后 201；Item 正常完成 | busy_timeout=15 s 内串行化，不失败 |
| ASR 超时 | 未注入（硬超时 4 h） | kill/lease 覆盖 ASR 挂起；`test_processing.py::test_command_timeout_is_marked_transient` 覆盖 subprocess timeout 归类 | 未实测，记录为缺口 |
| ENOSPC 磁盘满 | 未注入（Docker Desktop 命名卷无配额） | 用 EACCES 验证 `storage.error` 路径；`domain/retry.py` 将 ENOSPC 归为 transient，`test_retry.py` 覆盖 | 未实测，记录为缺口 |

## 容量

### 100 条批量入队

- 100 个唯一 EPUB 变体，批次入队 **3.37 s**（29.66 Item/s）。
- 从第一条创建到全部 completed：**4.67 s**；吞吐 **1,283.57 Item/min**。
- 100/100 completed，0 failed/cancelled。
- 队列峰值：download/extract 4、organizing 14、indexing 24；active 峰值 5。
- 峰值 RSS（采样 `docker stats`）：api 96.4 MiB、download 88.0、asr 79.0、llm 82.8、index 82.4；总计 **428.6 MiB**。
- LLM 调用 **100** 次，0 失败。
- 延迟：create p95 118 ms；列表轮询 p95 119 ms；health p95 20.7 ms；搜索 p95 58.4 ms。
- 说明：EPUB 仅 3.3 KB、LLM 为本地 mock；该结果衡量队列/索引吞吐，不代表真实 ASR 负载。100 条批次全为 EPUB，无 ASR 任务；ASR RTF 见视频/播客链路（0.1237 / 0.216）。

### 10k 搜索与 API 读

`trove bench seed --count 10000` 用时 60.36 s；最终 10,118 Items。

| 请求 | p50 | p95 | SLO | 结果 |
| --- | --- | --- | --- | --- |
| `GET /api/search?q=人工智能`（120 次） | 42.21 ms | **75.48 ms** | ≤ 300 ms | 通过 |
| `GET /api/health`（100 次） | 8.21 ms | **13.01 ms** | ≤ 200 ms | 通过 |
| `GET /api/items/{id}`（100 次） | 5.28 ms | **7.21 ms** | ≤ 200 ms | 通过 |
| `GET /api/items?limit=1`（3 次） | 3,615 ms | 3,641 ms | ≤ 200 ms | **未达标** |
| `GET /api/items?limit=50`（3 次） | 3,603 ms | 3,630 ms | ≤ 200 ms | **未达标** |

根因：`LibraryService.list_items()` 加载全部未删除 Item 并构建完整 bundle，handler 之后才切片；10k 时每次列表请求都是 O(N)。已创建后续 issue [22](issues/22-paginate-item-list.md)。列表 p95 仅由 3 次采样得出，用于量级判断；严格 p95 由 22 的 100 次复测补齐。

## 观测

- Prometheus 抓取 5 个 target（api + 4 个 pool）全部 `up`。
- Grafana 13.3.2；dashboard `Trove Host`（uid `trove-host`，14 panels）通过 provisioning 导入 `Trove` 文件夹。
- 四个黄金信号（Grafana `/api/ds/query` 实际返回）：
  - Traffic：`sum(rate(trove_http_request_duration_seconds_count[5m]))` ≈ 0.021 req/s。
  - Latency：HTTP p95 ≈ **9.75 ms**。
  - Errors：5xx ratio 查询为空（窗口内 0 个 5xx）；注入 500 后 `trove_stage_failures_total{code="llm.failed",stage="organizing"}=1`、`trove_stage_retries_total{stage="organizing"}=1`。
  - Saturation：`trove_queue_depth` 6 个 stage 均为 0（空闲），有数据。
- 其他指标：stage duration、ASR RTF、LLM tokens/cost、search latency/results、cache hit/miss 均有样本。
- Trace：单条 Item 的 trace id `7efc0b816443487eb2888bd30283357e` 串起
  `HTTP POST`（API）→ `queue.enqueue` → `stage extracting_text`（download worker）→
  `queue.enqueue` → `stage organizing` + `trove.llm.organize`（llm worker）→
  `queue.enqueue` → `stage indexing`（index worker）。
  同一 trace 的 `trove.run_id` / `trove.item_id` 属性一致。

## 升级 / 回滚

- 上一版本 DB：Pass 1/2 卷的 `trove-0009_external_call_cache-20261127T071557Z.db`（`0009`，75 行 items 含 tombstone、22 runs；API 可见 10 条）。
- 升级：当前代码 `trove db upgrade` 自动生成 `trove-0009...-20261127T081729Z.db`，迁移到 `0010_stage_traceparent`；items/runs 计数不变；容器内 `doctor --json` `ok=true`（worker 未启动为 warn）。
- 回滚演练：
  1. 停 API/worker，恢复 `0009` 备份，删除 `trove.db-wal`/`-shm`。
  2. 用 `git archive c3e4d65 src` 的上一版本源码（`PYTHONPATH`）启动旧代码。
  3. 旧代码 `doctor --json` `ok=true`，revision `0009`。
  4. 旧代码 `serve --no-worker`：`/api/health` 200，登录 200，`/api/items` 返回 `total=10`（tombstone 不计）。
  5. 数据未丢；回滚后再次升级路径已由 `db upgrade` 重复验证。

## Android

- `scripts/android/check.sh`：`BUILD SUCCESSFUL in 51s`；230 tasks（131 executed，99 from cache）。
- 覆盖 `:app:assembleProdDebug` + app/core/playback/reader 的 JVM/Compose 单测与 lint。
- 契约/同步/播放/搜索定向测试：`tests/test_contract_fixtures.py`、`test_sync.py`、`test_playback.py`、`test_search.py` 共 49 passed。
- 未连接真机；未做 Android 端手工播放/下载验收（Pass 1 记录同样限制）。

## 质量门禁

| 命令 | 结果 |
| --- | --- |
| `PLAYWRIGHT_BROWSERS_PATH=... ./scripts/check.sh --full` | exit 0；ruff、mypy（121 files）、lint-imports（6 kept/0 broken）、pytest 643 collected（含 29 browser，全部通过）、docs 131 files OK |
| `./scripts/android/check.sh` | exit 0，BUILD SUCCESSFUL |
| `uv run pytest -q tests/test_contract_fixtures.py tests/test_sync.py tests/test_playback.py tests/test_search.py` | 49 passed |
| `uv run pytest -q -n 0 -m browser` | 29 passed（设置 `PLAYWRIGHT_BROWSERS_PATH` 后） |

注：未设置 `PLAYWRIGHT_BROWSERS_PATH` 时，测试 fixture 使用 pytest 临时 HOME，找不到浏览器而 skip；设置后实际执行并通过。

## SLO 快照

| SLO | Target | 本次观测 | 结果 |
| --- | --- | --- | --- |
| 30 分钟音频入库到可搜索 p95 | ≤ 15 分钟 | 15 分钟视频 124.5 s；3.75 分钟播客 61.9 s；未按 30 分钟样本和 p95 定义实测 | 部分验证（样本不足，见例外） |
| ASR RTF（M1 Pro） | ≤ 0.15 | 900 s 视频 0.1237；225 s 播客 0.216（短音频固定开销）；30 分钟样本未测 | 部分验证（长音频通过，短音频超目标） |
| API 读请求 p95 | ≤ 200 ms | health 13.0 ms；单 Item 7.2 ms；10k 列表 3,615 ms | **列表未达标** |
| 搜索 p95（10k Item） | ≤ 300 ms | 75.48 ms | 通过 |
| worker 崩溃恢复 | ≤ 30 s | lease 回收 28.5 s；任务在 32.6 s 退避后开始 attempt 2（kill→恢复约 61.1 s）；API crash 2.68 s | lease 回收达标；按任务恢复超 30 s |
| 自动重试重复外部调用 | 0 | Pass 1 直接 stage 验证 ASR/AI cache hit 0 外部调用；Pass 3 显式重跑按设计绕过 cache | 通过（Pass 1 证据） |
| 全新安装（不含模型下载） | ≤ 10 分钟 | Docker 18.52 s；launchd 9.87 s | 通过 |
| 非源错误导致 Run 失败率 | < 2% | 100 条容量 0 失败；故障注入失败均可恢复或明确 dead | 通过 |

## 复现命令（摘要）

```bash
# 质量门禁
PLAYWRIGHT_BROWSERS_PATH="$HOME/Library/Caches/ms-playwright" ./scripts/check.sh --full
./scripts/android/check.sh

# Docker 全新安装
export TROVE_IMAGE_TAG=acceptance TROVE_HOST_PORT=18765 TROVE_PUBLISH_ADDRESS=127.0.0.1
docker compose -p trove-acceptance up -d
curl -fsS http://127.0.0.1:18765/api/health

# 功能链路（示例：视频）
curl -b cookies -H 'content-type: application/json' \
  -d '{"kind":"url","url":"https://www.bilibili.com/video/BV1MLqDYxEpN?p=1"}' \
  http://127.0.0.1:18765/api/items

# 容量 / 10k
docker compose -p trove-acceptance exec -T api \
  trove --home /home/trove/Trove bench seed --count 10000 --json

# 观测
curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:18765/metrics
curl http://127.0.0.1:8766/metrics   # 在 worker 容器内

# 故障注入示例
docker compose -p trove-acceptance exec -T worker-asr sh -c 'kill -9 <worker-pid>'
docker compose -p trove-acceptance exec -T api python -c \
  'import sqlite3,time; c=sqlite3.connect("/home/trove/Trove/trove.db"); c.execute("BEGIN EXCLUSIVE"); time.sleep(8)'
curl -X POST --data 429 http://127.0.0.1:18080/mock/mode   # 429 / 500 / ok
```

完整原始命令、JSON 结果和日志在本次验收的临时目录 `$TMPDIR/trove-acceptance/`
（本次实际为 `/private/var/folders/72/3hksb2217fb4mmb9__gzby_m0000gp/T/opencode/trove-acceptance/`；临时目录，不随仓库提交）。

## Issue 结果

只验收已实现的 issue：01–13、21。14–18、20 未实现或处于 gated / needs-triage；19 本次完成；22、23 为本次验收新增后续项。

| Issue | 结果 | 证据 |
| --- | --- | --- |
| 01 ADR/SLO | 通过 | `docs/adr/0014-...` 与 spec SLO 表存在；SLO 见本记录。 |
| 02 API v1 / 幂等 | 通过 | Pass 1：201/重放 201 `Idempotency-Replayed: true`/409/无 key 200 dedupe/401；重启后仍命中。 |
| 03 ProcessingService 拆分 | 通过 | 运行日志按 stage 记录；`RunCoordinator` / `services/stages/*` 结构测试全绿。 |
| 04 LLM organizer 拆分 | 通过 | Pass 1 本地 Ollama 生成摘要和 3 tags；Pass 3 mock LLM 100 次调用 0 失败。 |
| 05 分层门禁 | 通过 | `lint-imports`: 6 kept / 0 broken。 |
| 06 manifest / schema_version | 通过 | manifest schema_version=1；audio/transcript/ai sha256/size/mime；package verify 通过。 |
| 07 StageTask 队列 / 租约 | 通过 | 崩溃注入 attempt 1 `run.lease_expired`，attempt 2 完成；取消可用。 |
| 08 worker 池 / 并发 | 通过 | 四池分别领取；health 同时列出四池；heartbeat 文件跨容器独立。 |
| 09 重试 / 退避 / 死信 | 通过 | 429/500 退避重试；max_attempts=1 注入 `dead` + `run.dead`；失败 Item 可查询/重试。 |
| 10 外部调用缓存 | 通过 | Pass 1 ASR/AI cache hit 0 外部调用；Pass 3 显式 reprocess 日志 `ai cache bypassed`。 |
| 11 Docker Compose 打包 | 通过 | 全新卷 up/down/up 数据保留；非 root；doctor 通过；ASR/ slim 镜像构建可用。 |
| 12 指标 / tracing | 通过 | Prometheus 5 target up；Grafana 14 panels；OTel 单 trace 串起 API→4 阶段/adapter。 |
| 13 升级 / 回滚 / doctor | 通过 | 0009→0010 升级备份/计数一致；旧代码回滚 doctor/health/login/items 通过。 |
| 14–18 | 未实现 / gated | 研究或 Phase 4 服务抽取。 |
| 19 整体验收 | 完成 | 本记录。 |
| 20 | needs-triage | ASR warm pool。 |
| 21 Web DB baseline 清理 | 通过 | `lint-imports` 无 baseline；本次全量门禁通过。 |
| 22 | 新增后续 | 10k Item 列表 O(N)，见 [22](issues/22-paginate-item-list.md)。 |
| 23 | 新增后续 | 补齐 30 分钟 p95、ASR RTF 分桶、worker 恢复口径，见 [23](issues/23-slo-sample-gaps.md)。 |

## 处理时间线（Pass 1）

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

从创建到完成 321.7s（含故障注入和约 2 分钟人工等待）；纯处理时间约 2m30s。

## Pass 1/2 细节（保留）

### Pass 1：Docker 视频、分池、缓存、幂等

- 单集 15 分钟视频最终 5m22s 完成（含故障注入与人工等待），低于 15 分钟目标。
- 分池修复：heartbeat 文件名改为 `worker-<hostname>-<pid>.json`；lease `worker_id` 含 hostname；doctor/内置 worker 在 hostname 不同时信任 fresh heartbeat。回归测试覆盖同 PID 不同 hostname。
- 内容包：`audio.m4a` 7,492,450 B、`transcript.json` 34,121 B（263 段）、`ai.json`、`source.json`、`manifest.json`；package verify 通过；`/api/export` 7.3 MB zip。
- 缓存：用“会抛错的 transcriber/organizer”直接调用 stage：ASR `transcript cache hit ... saved_asr_seconds=901.844667 cost=0`；AI `ai cache hit ... cached=true cost=0 saved_input_tokens=2111 saved_output_tokens=112 saved_cost_usd=0.00063812`。
- 幂等：201/重放 201 + `Idempotency-Replayed: true`/同 key 异 body 409 `idempotency.key_reused`/无 key 重复创建 200 + `deduplicated: true`/未登录 401 `auth.required`；重启后重放仍命中。
- 运维：`docker compose down` 后 `up -d` Item/搜索/manifest 保留；`doctor --json ok=true`；在线备份 0600、544,768 B、revision 0009。

### Pass 2：合集前 10 集

- Collection ID `23fd8970-cde7-401e-bba3-cda6e84f7c0b`；标题 100 讲但 yt-dlp 只返回 75 part（上游可见范围）。
- 已有 p1 被识别为同源 Episode（`collection.episode_attach`）；`added=74`、`attached=1`、`run_count=74`。
- 为只取前 10 集：停 worker，创建合集后删除 `collection_index` 11–75，再启动分池；被删集数未下载/转写。
- 分池：download=3、asr=1、llm=2、index=1；05:12–05:25 约 13 分钟完成 10 集；`completed=10`、`failed=0`。
- 总音频 7,083.148503 s；单集 ASR 48.78–125.92 s，RTF 0.111–0.141；organizing 4.77–11.24 s。
- 下载池并发 3；05:12:03 时 3 active/6 queued；05:12:43 下载/抽取完成，ASR 继续串行，长 ASR 未阻塞下载。
- 首轮 tags 一致：`Tao Te Ching`、`Zeng Shiqiang`、`Taoism`。
- `collection reprocess --from-stage organizing --reset-ai-tags`：删除 30 条 AI tag link，排队 10 个 run，约 70 s；`ai_results` 12→22，总成本 $0.013218，input 43,769/output 2,293 tokens；显式重跑绕过 cache。
- 重跑后 tags 分叉（并发 LLM 后完成者看不到先完成者新增 tag），记录为观察项。
- 搜索：`道德经`/`老子` 10 集，`无为` 3 集，`上善若水` 仅 p8；导出 57,697,491 B zip，51 entries，10 个 manifest/index。
- 合集分集数与标题不一致（100 vs 75）为上游/yt-dlp 可见范围，不是 Trove 截断。

## 遗留问题与后续

1. **10k 列表 SLO 未达标**：`/api/items` 为 O(N)，10k 时 p50 3.6 s；后续 [22](issues/22-paginate-item-list.md)。这是本次唯一确认未达标的已测 SLO。
2. **SLO 取样/口径缺口**：30 分钟 p95 未按定义实测；短音频 ASR RTF 0.216 超过 0.15；worker 恢复按 lease 回收 28.5 s 达标、按任务恢复约 61.1 s 超 30 s。后续 [23](issues/23-slo-sample-gaps.md)。
3. **ASR 超时未真机注入**：硬超时 4 h；kill/lease 覆盖挂起恢复，subprocess timeout 归类由 `test_processing.py::test_command_timeout_is_marked_transient` 覆盖。
4. **真实 ENOSPC 未注入**：Docker Desktop 命名卷无磁盘配额；用 EACCES 验证 `storage.error` 路径，ENOSPC 归类由 `test_retry.py` 覆盖。若需要，可在 Linux + loop device/tmpfs 上补做。
5. **合集批量下载未在 Pass 3 重跑**：沿用 Pass 2 `c3e4d65` 证据；后续 diff 为 observability/run 读取重构，不触碰 collection 入队/下载。
6. **Android 无真机**：仅 JVM/Compose/契约/lint；Pass 1 同样限制。真机播放/下载/阅读需按 `docs/android.md` 另做。
7. **launchd 安装使用临时 home/agents，且未重新下载 ASR 模型**：安装时间不含模型下载（SLO 允许）；`doctor` 用共享 `MODELSCOPE_CACHE` 通过。正式机器首次安装仍需 `trove setup` 下载 1.25 GB。
8. **Docker 安装使用预构建镜像和预置模型缓存**：干净卷/网络已测；镜像构建时间和模型下载未计入。发布验收应按 `TROVE_BUILD_COMMIT/TIME` 重建镜像。
9. **LLM 使用 mock**：Pass 3 为了可重复和成本，使用确定性 mock；真实 Ollama/DeepSeek 链路见 Pass 1/2。生产 LLM 失败注入（429/5xx）用 mock 覆盖。
10. **Grafana/Prometheus 为临时容器**：dashboard 通过 provisioning 导入并用 `/api/ds/query` 验证四个黄金信号；未保存长期截图。生产部署按 `docs/observability.md` 配置 scrape token。
11. **10k 搜索为合成数据**：`trove bench seed` 生成，不代表真实语料 recall；搜索 p95 数据只验证延迟 SLO。
12. **Pass 1 旧 heartbeat 文件**：升级后旧 `worker-<pid>.json` 15 s 后 stale，7 天后 prune，不影响新逻辑。
13. **摘要语言**：中文音频可能得到中文或英文摘要（取决于 LLM 输出）；产品层未强制跟随内容语言。
14. **合集重跑 tag 分叉**：并发 LLM worker 下词表可能不一致；若要求强一致，先收敛词表再批量整理。
15. **`language` 为空**：Pass 1 的 transcript 有分段但 `language` 为 null（FunASR 未返回语言），不影响播放/搜索。
16. **`docker kill` 语义**：Compose 把 `docker kill` 视为手动停止，不一定触发 `restart: unless-stopped`；Pass 1 因此人工切换 worker。Pass 3 改用容器内 `kill -9` 真实进程，RestartCount 增加。
17. **回滚只验证升级前数据**：回滚恢复 0009 备份后未写入 0010 新数据，因此“0010 新内容包在 0009 下可读”未单独复测；manifest schema 仍为 1，旧包可读由 ADR-0008 与既有测试覆盖。
