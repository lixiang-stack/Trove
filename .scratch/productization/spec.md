# Trove 产品化与后端演进 — Feature Spec

Status: ready-for-agent
Feature: productization
Date: 2026-11-25
Scope: 单租户自托管 Host 的工程化、标准化、模块化与按阶段服务化；不包含多租户与 Go 重写
Sources: [ADR-0001](../../docs/adr/0001-python-monolith-sqlite-worker.md), [ADR-0008](../../docs/adr/0008-content-package-as-source-of-truth.md), [deployment](../../docs/deployment.md), [code map](../../docs/agents/code-map.md), [requirements](../../docs/ideas/trove-requirements.md)

## Problem Statement

Trove Host 已经是一个分层清晰的模块化单体：`domain / services / ports / adapters` 边界存在，处理管线有持久化 `Run` / `RunStep` 状态机，内容包是事实源，搜索通过 `SearchIndex` 端口使用 FTS5，API 与 Android 客户端有契约测试。它现在的主要问题不是“代码写得像脚本”，而是产品化与运行形态：

1. 没有可安装的交付物：依赖 git checkout、`uv`、Homebrew FFmpeg、1.25GB 模型和 launchd，用户无法一条命令启动。
2. 处理按整条 Run 串行执行：一次长 ASR 会阻塞下载、摘要和索引；单 worker 无法按资源类型扩缩。
3. `ProcessingService` 混合了队列、状态机、阶段执行、产物安装和标签词表，新增阶段或抽服务都要改同一个千行文件。
4. 失败恢复靠人工：没有自动重试、退避、最大次数和死信；LLM/ASR 重跑会重复调用。
5. 缺运行指标：有 JSON 日志和健康检查，但没有队列深度、阶段耗时、失败率、ASR RTF、LLM 成本和搜索延迟的聚合指标。
6. 内容包没有 `schema_version`，长期升级、导入导出和跨版本迁移缺版本协商。
7. 对外 API 没有明确的版本、幂等和兼容策略，第三方或未来客户端集成缺约束。

同时需要把技术路线固定下来：本产品是**单租户自托管**，不按多租户 SaaS 设计；核心继续使用 **Python**，不做 Go 重写；服务化按处理阶段和资源类型推进，不按 CRUD 领域拆微服务。

## Solution

保持 Python 模块化单体作为核心，先把内部边界、可靠性和交付补齐，再按阶段引入 worker 池；只有出现明确指标或部署需求时才抽取独立服务。

目标形态是 **L1：单机、单租户、按阶段分池的处理架构**：

```text
            ┌──────────┐
Client ───▶ │   API    │──┐
            └──────────┘  │
                          ▼
                   ┌─────────────┐
                   │ SQLite/PG   │
                   │ StageTask   │
                   └──────┬──────┘
        ┌─────────────┬───┴────┬──────────────┐
        ▼             ▼        ▼              ▼
   download pool  asr pool  llm pool    index pool
        │             │        │              │
        └─────── ContentPackage / 对象存储 ────┘
```

- API 只负责 HTTP、鉴权、同步和入队；worker 按 stage 领取任务。
- `Run` 仍是 API/UI 的聚合根；`RunStep` 升级为可领取的 `StageTask`，带租约、尝试次数和可用时间。
- 下载、ASR、整理、索引各自有并发上限；ASR 默认并发 1，索引默认单写者。
- 单机继续用 SQLite WAL；只有多机或多租户才换 Postgres 和外部队列。
- 内容包仍是事实源；新增 `manifest.json` 和 `schema_version`，不改变现有文件布局。

## Decisions

| ID | Decision | Rationale |
|---|---|---|
| D1 | 产品形态：单租户自托管 Host | 一个 Host = 一个 Library = 一个所有者；多设备通过 device token 支持 |
| D2 | 核心语言保持 Python | yt-dlp、FunASR、EPUB/LLM 生态都在 Python；瓶颈是网络、模型和运维，不是编排层 |
| D3 | 不按 CRUD 拆微服务，按处理阶段分池 | 下载/ASR/整理/索引的资源特征和故障模式不同，阶段是正确边界 |
| D4 | 服务抽取顺序：ASR → 下载 → 整理 → 搜索 | ASR 资源隔离收益最大；搜索数据耦合最深，最后拆 |
| D5 | 本 effort 不做 Go 重写 | Go 不能去掉 yt-dlp/FunASR；单用户规模收益不抵双工具链成本 |
| D6 | 内容包是事实源，数据库是可重建索引 | 延续 ADR-0008；新增 manifest 只做版本和校验，不改变布局 |
| D7 | 单机继续 SQLite，不预引入 Redis/Celery/Postgres | 当前并发和规模不需要；StageTask + lease 已足够 |
| D8 | API 采用 additive v1；破坏性变更才开 v2 | 第一方 Android 客户端可锁步，但契约测试必须保留 |
| D9 | Docker 作为一等交付，launchd 保留为 macOS 原生路径 | 自托管用户需要可复现安装；现有 Mac 部署不能回归 |
| D10 | 未来服务化只在契约后替换实现 | 端口是语言/进程边界；禁止重写核心事务和内容包 |

### 语言决策

Python 继续用于 API、领域、服务、适配器和 worker。Go 重写明确不在本 effort 范围。原因：

- 下载依赖 yt-dlp（Python），ASR 依赖 FunASR/PyTorch（Python）；Go 只能包一层，仍要带 Python 运行时。
- 下载是网络/磁盘密集型，整理是外部 API 密集型，ASR 计算在原生内核；Python 编排开销不是瓶颈。
- 当前规模是单用户、低并发；Go 的静态二进制和 goroutine 优势不构成产品收益。
- 产品化的真正缺口是打包、升级、观测、重试和契约，这些与语言无关。

只有满足以下任一触发条件，才重新评估某个**独立服务**的实现语言，而不是重写核心：

- 压测后 API p95 或并发量仍达不到 SLO，且 profiling 证明瓶颈在 Python 运行时；
- 必须支持 Windows/Linux 且不能依赖 Docker/Python 运行时；
- ASR 需要迁移到更轻的运行时（如 sherpa-onnx/ONNX），且新运行时提供 Go/C++ 绑定；
- 团队长期以 Go 为主，维护成本成为主要约束。

即使触发，也按 `Organizer → API 边缘 → 搜索 → ASR` 的顺序试点，不做全量重写。

## Goals

- 新用户用 Docker Compose 在 10 分钟内启动（不含模型下载），数据持久化在命名卷。
- 长 ASR 不再阻塞下载、整理和索引；各池并发可配置。
- worker 崩溃或任务超时后自动恢复，不需要人工重启；失败任务有明确状态和可读原因。
- LLM/ASR 自动重试不重复计费；显式重跑可以强制绕过缓存。
- 提供 Prometheus 指标和 OpenTelemetry trace，能看到队列深度、阶段耗时、失败率、ASR RTF、LLM 成本和搜索延迟。
- 内容包带 `manifest.json` 和 `schema_version`，旧包仍可读，导出包含 manifest。
- 现有测试、API 契约和 Android 客户端不回归。

## Non-Goals

- 多租户、账号体系、计费、配额、SaaS 控制面。
- Go/Rust 重写；把核心迁出 Python。
- Kubernetes、Kafka、Redis、Celery、外部消息队列。
- 立即替换 FTS5 或引入向量数据库。
- 改变 Content Package 文件布局、Item/Collection/Run 事务边界。
- 移动端功能变更；只保证现有 Android 契约兼容。
- 云端托管、Windows 原生安装包、自动更新服务。

## Current State

- 分层与端口：`src/trove/ports.py` 定义 9 个协议；`composition.py` 是组合根；`web/` 是 HTTP 适配器。
- 处理管线：`services/processing.py` 约 1000 行；`Run` 状态机支持重试、取消、心跳和启动时回收。
- 适配器：`adapters/downloader.py`（yt-dlp/HTTP）、`adapters/asr.py`（FunASR 子进程）、`adapters/openai_chat.py`（OpenAI 兼容）；整理工作流在 `services/organization.py`、`adapters/search.py`（FTS5）。
- 内容包：`content_package.py` 负责固定文件名、原子写入、sha256、`manifest.json` 与 `schema_version`；旧包无 manifest 仍可读。
- 运维：`deploy.py` 只支持 macOS launchd；`web/api/health.py` 覆盖 API/DB/FTS5/worker 心跳。
- 质量：ruff、mypy、pytest、契约 fixtures、复杂度门禁、CI；40+ 测试文件。
- 观测：JSON 日志已带 `run_id`/`item_id`/`duration_ms`；无指标和 trace。

## Target Architecture

### L1 组件

| 组件 | 职责 | 默认并发 |
|---|---|---|
| API | HTTP、认证、同步、入队、健康检查、指标端点 | Uvicorn 默认 |
| RunCoordinator | 创建 Run、维护阶段依赖、汇总状态 | 1 |
| download pool | 下载 video/podcast/EPUB，调用 yt-dlp/HTTP | 3 |
| asr pool | 音频提取后的转写；调用 FunASR 子进程 | 1 |
| llm pool | 摘要/标签；调用外部 LLM | 2 |
| index pool | FTS5 索引写入与重建 | 1 |
| ContentPackage | 事实源文件、manifest、导出 | 共享卷 |
| SQLite | 元数据、Run/StageTask、设备、同步、FTS5 | WAL |

### StageTask 语义

- 状态：`queued → running → completed | failed | dead | cancelled`。
- `lease_until` + `worker_id`：worker 领取后获得租约，定期续租；过期由 reaper 重新入队。
- `attempt` / `max_attempts` / `available_at`：自动重试使用指数退避 + jitter；超过上限进入 `dead`。
- 阶段依赖：一个 stage 完成后由 coordinator 入队下一个 stage；`Run` 在所有 stage 终态后汇总。
- 取消：`cancel_requested_at` 在 stage 边界和长循环检查点生效；已领取任务释放租约。
- 幂等：同一 Item 同时最多一个 active Run；stage 重试必须复用已有产物，不重复下载/转写/计费。

### 服务抽取条件

L1 先不拆独立服务。满足以下条件才启动 Phase 4 issue：

- ASR：单机 ASR 队列持续积压，或需要 GPU/多机/独立扩容。
- 下载：需要独立代理、cookies 池、出口 IP 或平台限流隔离。
- 整理：需要独立配额、成本控制或 provider 切换。
- 搜索：FTS5 的 recall/latency 在 10k Item 规模不达标，或需要语义搜索。

## Work Breakdown

| Phase | Outcome | Issues | Estimate |
|---|---|---|---|
| P0 | 固化产品形态、SLO 与 API 契约 | 01, 02 | 3–5 天 |
| P1 | 拆分上帝类、建立分层门禁、内容包版本 | 03, 04, 05, 06 | 2–3 周 |
| P2 | StageTask 队列、阶段池、重试、幂等 | 07, 08, 09, 10, 20 | 2–4 周 |
| P3 | Docker 交付、观测、升级回滚、整体验收 | 11, 12, 13, 19 | 2–3 周 |
| P4 | 有数据门槛的服务抽取与搜索/ASR 评估 | 14, 15, 16, 17, 18 | 按需 |

## SLOs

初始目标，Phase 3 验收时用真实数据校准。

| SLO | Target | Measurement |
|---|---|---|
| 30 分钟音频入库到可搜索 p95 | ≤ 15 分钟 | stage 时间戳 |
| ASR RTF（M1 Pro 参考机） | ≤ 0.15 | benchmark |
| API 读请求 p95 | ≤ 200 ms | HTTP metrics |
| 搜索 p95（10k Item） | ≤ 300 ms | 搜索 metrics |
| worker 崩溃恢复 | ≤ 30 秒 | 故障注入 |
| 自动重试的重复外部调用 | 0 | cache/metrics |
| 全新安装（不含模型下载） | ≤ 10 分钟 | acceptance |
| 非源错误导致的 Run 失败率 | < 2% | metrics |

## API and Data Contracts

- API 版本：`/api` 下保持 additive；破坏性变更开 `/api/v2`，旧版本至少保留一个 minor 周期。
- `GET /api/health` 继续返回 `api_version` 和 `capabilities`；新增 build/commit 信息时保持向后兼容。
- 幂等：所有创建型 POST 接受 `Idempotency-Key`；重复键返回同一响应，不重复创建/入队。第一版至少覆盖 `POST /api/items`。
- 错误信封：`{code, message, details, request_id}`；`code` 使用现有稳定错误码。
- Run 进度：v1 继续轮询；SSE/webhook 作为后续增强，不在本 effort 实现。
- 内容包 manifest：`manifest.json` 含 `schema_version`、`item_id`、`created_at`、`updated_at`、artifacts（kind/path/sha256/size/mime）。
- 旧内容包没有 manifest 时仍可读；新写入和导出必须带 manifest；版本不兼容返回明确 `storage.package_version`。

## Testing Strategy

- 单元：stage handlers、OrganizationWorkflow、retry/backoff、cache key 用 fake port 测试，不触网。
- 集成：临时 `TROVE_HOME` + SQLite + fake adapters，覆盖 Run/StageTask 全链路。
- 契约：OpenAPI/`contract/*.json` 不变；新增 API 响应做 fixture 断言。
- 故障注入：worker kill、租约过期、LLM 429/5xx、ASR 超时、磁盘写失败。
- 迁移：旧 DB → head；无 manifest 的旧内容包 → 可读/可导出。
- 负载：100 条合成 Item 批量入队，记录吞吐、队列深度、内存。
- Docker：干净环境 `docker compose up`，用本地 audio/EPUB fixture 完成一条链路。
- 现有 `scripts/check.sh --fast` 和完整测试保持绿；Android 契约 fixtures 不回归。

## Rollout

1. Phase 1 只做内部拆分，行为不变，随正常版本发布。
2. Phase 2 默认 `TROVE_WORKER_POOLS=all`，保持单 worker 兼容；阶段池先 opt-in，验收后成为默认。
3. Phase 3 Docker 作为可选交付；launchd 文档和脚本保留。
4. Phase 4 独立服务通过 remote adapter + feature flag 接入；保留 in-process fallback，可一键回滚。
5. 每个阶段都更新 `docs/deployment.md`、`README.md` 和验收记录。

## Risks

| Risk | Mitigation |
|---|---|
| 重构引入回归 | 行为不变，先补 stage 单测，再拆文件；host seam 覆盖全链路 |
| SQLite 多 worker 写冲突 | WAL + busy_timeout + 短事务；index pool 并发 1 |
| ASR 并发导致内存暴涨 | 默认并发 1；容器/进程内存限制；按机器配置 |
| Docker 镜像过大 | ASR 作为可选构建 arg/独立镜像；模型放卷 |
| yt-dlp 平台失效 | 锁定版本、canary 测试、稳定错误码、可快速升级 |
| 范围蔓延 | 非目标清单 + Phase 4 触发条件；未达标不拆服务 |
| 两套部署路径漂移 | 共用 CLI/config/health；Docker 与 launchd 都跑同一入口 |

## Alternatives Considered

- **Go 全量重写**：不能去掉 yt-dlp/FunASR；单用户收益低；双工具链成本高。拒绝。
- **现在拆微服务**：网络、一致性、部署和观测成本超出单机收益；先做阶段池。拒绝。
- **多租户 SaaS**：会改 schema、认证、存储、计费和运维；当前产品形态不需要。拒绝。
- **Postgres + Redis + Celery**：多两个常驻服务；SQLite + StageTask 足够单机。推迟。
- **向量数据库/语义搜索**：先用 eval 证明 FTS5 不达标；没有数据不引入。推迟。
- **重写内容包/DB 事务核心**：违背 ADR-0008 和现有可恢复性；拒绝。

## Open Questions

- ASR 运行时是否从 FunASR 迁到 sherpa-onnx/ONNX：由 issue 14 的基准数据决定，不在本 spec 预设。
- Docker 是否同时发布 linux/amd64 与 linux/arm64：由 issue 11 在构建成本可接受时决定。
- API 是否需要在 v1 内加 SSE：由真实客户端需求决定；当前保持轮询。

## Out of Scope

- 多租户、账号、计费、配额、管理后台。
- Go/Rust 重写、把核心迁出 Python。
- Kubernetes、Kafka、Redis、Celery、外部消息队列。
- 替换 FTS5、引入向量数据库、重做搜索排序。
- 改变 Content Package 文件布局或 Item/Collection/Run 事务边界。
- 移动端 UI/功能变更；只保证契约兼容。
- 云端托管、Windows 原生安装包、自动更新服务。
