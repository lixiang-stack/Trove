# 0014 — 单租户自托管、Python 核心与按阶段分池

Trove 的产品形态确定为单租户自托管 Host：一个 Host 服务一个 Library、一个所有者；多设备通过 device token 访问，不做多租户 SaaS、账号体系、计费或配额。核心继续使用 Python；处理架构从“单 worker 顺序跑完整 Run”演进为按阶段分池（download / asr / llm / index），但暂不拆微服务。服务抽取只在有指标或部署需求时按 ASR → 下载 → 整理 → 搜索的顺序进行。Go 重写不在本阶段范围。

**Status**: Accepted · 2026-11-25

## Context

Trove 已经是一个模块化单体：`domain / services / ports / adapters` 分层，处理管线有持久化 `Run` / `RunStep` 状态机，内容包是事实源，搜索通过 `SearchIndex` 端口使用 SQLite FTS5，Android 客户端与 Host 有契约测试。当前问题不是“Python 只适合做 PoC”，而是产品化与运行形态：

- 安装依赖 git checkout、`uv`、Homebrew FFmpeg、1.25GB ASR 模型和 launchd，普通用户难以启动。
- 一次长 ASR 会阻塞下载、整理和索引；单 worker 无法按资源类型扩缩。
- `ProcessingService` 混合队列、状态机、阶段执行和产物安装，难以独立测试和抽服务。
- 没有自动重试、租约回收、外部调用幂等、聚合指标和内容包版本。
- 下载依赖 yt-dlp、ASR 依赖 FunASR/PyTorch；两者都是 Python 生态，且真正的耗时在外部进程或原生内核，不在 Python 编排层。

## Decision

### 产品与语言

- 产品是**单租户自托管 Host**，不是多租户 SaaS。一个 Host = 一个 Library = 一个所有者；多设备是同一所有者的不同客户端。
- 核心语言保持 **Python**。API、领域、服务、适配器、worker 都用 Python。
- **不做 Go 重写**。Go 不能去掉 yt-dlp/FunASR 的 Python 依赖；单用户规模下，静态二进制和 goroutine 的收益不抵双工具链、双构建、双部署和双排查成本。
- 产品化的重点是打包、升级、观测、重试、契约和阶段隔离；这些与语言无关。

### 运行形态

- 保持模块化单体，演进到 **L1：单机、按阶段分池**。
- `Run` 仍是 API/UI 的聚合根；`RunStep` 升级为可领取的 `StageTask`，带租约、`attempt`、`max_attempts`、`available_at`。
- 默认并发：download 3、ASR 1、LLM 2、index 1；ASR 内存上限靠并发数控制，index 保持单写者。
- 单机继续 SQLite WAL；只有多机或多租户才考虑 Postgres 和外部队列。
- 不引入 Redis、Celery、Kafka、Kubernetes；StageTask + lease 足够当前规模。

### 服务抽取

按资源特征和故障域拆分，不按 CRUD 领域拆微服务：

1. ASR：CPU/内存密集、模型大、可独立扩容。
2. 下载：网络出口、cookies/代理、平台限流。
3. 整理：外部 LLM 配额、成本、provider 切换。
4. 搜索：数据耦合最深，最后拆。

L1 先做阶段池；只有满足触发条件才抽独立服务。独立服务通过现有端口（`Transcriber`、`Downloader`、`Organizer`、`SearchIndex`）替换实现，保留 in-process fallback。

### 数据与交付

- 内容包仍是事实源；新增 `manifest.json` 和 `schema_version`，不改变现有文件布局。
- Docker Compose 作为一等自托管交付；macOS launchd 保留为原生路径。两者共用同一 CLI、config、health 和迁移。
- API 采用 additive v1；破坏性变更才开 `/api/v2`。创建型请求支持 `Idempotency-Key`。
- 新增 Prometheus 指标和 OpenTelemetry trace；指标标签不使用 `item_id`/`run_id` 等高基数值。

### 语言重评触发条件

只有满足以下任一条件，才重新评估**某个独立服务**的实现语言，而不是重写核心：

- 压测后 API p95 或并发量仍达不到 SLO，且 profiling 证明瓶颈在 Python 运行时；
- 必须支持 Windows/Linux 且不能依赖 Docker/Python 运行时；
- ASR 迁移到更轻的运行时（如 sherpa-onnx/ONNX），且新运行时提供 Go/C++ 绑定；
- 团队长期以 Go 为主，维护成本成为主要约束。

即使触发，也按 `Organizer → API 边缘 → 搜索 → ASR` 的顺序试点，不做全量重写。

## SLO

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

## Consequences

- 单机单写者、SQLite 迁移和备份仍是运维重点；多 worker 必须遵守 WAL、短事务和索引单写者约束。
- ASR/下载仍是 Python 生态依赖；镜像会包含 FFmpeg、yt-dlp，ASR 可选镜像会更大。
- 不追求“单文件二进制”；交付以 Docker 镜像和卷为主，macOS 用户可用 launchd。
- 服务抽取被推迟到有指标之后，避免提前承担网络、一致性和观测成本。
- Android 客户端契约保持兼容；API 只做 additive 变更。

## Non-Goals

- 多租户、账号体系、计费、配额、SaaS 控制面。
- Go/Rust 重写；把核心迁出 Python。
- Kubernetes、Kafka、Redis、Celery、外部消息队列。
- 立即替换 FTS5 或引入向量数据库。
- 改变 Content Package 文件布局或 Item/Collection/Run 事务边界。
- 移动端功能变更；只保证现有 Android 契约兼容。
- 云端托管、Windows 原生安装包、自动更新服务。

## Alternatives Considered

- **Go 全量重写**：不能去掉 yt-dlp/FunASR；单用户收益低；双工具链成本高。拒绝。
- **现在拆微服务**：网络、一致性、部署和观测成本超出单机收益；先做阶段池。拒绝。
- **多租户 SaaS**：会改 schema、认证、存储、计费和运维；当前产品形态不需要。拒绝。
- **Postgres + Redis + Celery**：多两个常驻服务；SQLite + StageTask 足够单机。推迟。
- **向量数据库/语义搜索**：先用 eval 证明 FTS5 不达标；没有数据不引入。推迟。
- **重写内容包/DB 事务核心**：违背 ADR-0008 和现有可恢复性；拒绝。

## References

- [产品化 spec](../../.scratch/productization/spec.md)
- [ADR-0001](0001-python-monolith-sqlite-worker.md)
- [ADR-0008](0008-content-package-as-source-of-truth.md)
- [部署文档](../deployment.md)
