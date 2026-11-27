# 19 — 产品化验收：端到端、故障恢复与容量基准

Status: resolved
Type: task
Milestone: P3
Blocked by: 07, 08, 09, 10, 11, 12, 13
Spec: [spec.md](../spec.md)

## Context

Phase 1–3 的改动需要一次整体验收，证明“单租户自托管产品”真的可安装、可恢复、可观测，而不是只通过了单元测试。验收结果写入 `.scratch/productization/acceptance.md`，作为发布依据。

## Scope

- 全新安装：
  - Docker Compose 干净环境；macOS launchd 路径各跑一次。
  - 记录从零到 `/api/health` 200 的时间（不含模型下载）。
- 功能链路：
  - 视频 URL（可用 fake/本地 server）→ 下载 → 音频 → ASR → 摘要/tag → 搜索。
  - EPUB 本地/URL → 解析 → 摘要/tag → 阅读/搜索。
  - 播客单集 → 下载 → ASR → 搜索。
  - 合集入库、批量下载、重跑 ASR/整理。
- Android 兼容：现有契约 fixtures、同步、播放、搜索不回归。
- 故障注入：
  - kill worker/API；租约过期；LLM 429/5xx；ASR 超时；磁盘满；SQLite busy。
  - 断言自动恢复/重试/死信行为符合 09/07。
- 容量：
  - 100 条合成 Item 批量入队；记录吞吐、队列深度、峰值 RSS、ASR RTF、LLM 调用数。
  - 对比 spec SLO；未达标项记录原因和后续 issue。
- 观测：Grafana dashboard 能看到四个黄金信号；trace 能串起一条 Item。
- 升级/回滚：上一版本 DB → 升级 → doctor → 回滚演练。
- 输出：`acceptance.md` 包含环境、版本、命令、结果、例外、遗留问题。

## Acceptance Criteria

- [x] Docker 和 launchd 两条安装路径都完成一次全新安装；时间记录。
- [x] 视频/EPUB/播客三条链路完成并可搜索；重跑/取消可用。
- [x] 长 ASR 期间下载/整理不被阻塞（或记录实际并发行为）。
- [x] 故障注入场景全部有预期结果；无静默丢任务（ASR 超时/真实 ENOSPC 未真机注入，见 acceptance.md 例外）。
- [x] 100 条批量测试完成；记录 SLO 达标情况。
- [x] Android 契约测试通过；无 P0/P1 回归。
- [x] 升级/回滚演练通过；数据不丢（回滚恢复升级前备份；未写入 0010 新数据，见例外）。
- [x] `acceptance.md` 完成，例外和后续 issue 明确。
- [x] `./scripts/check.sh` 全绿（含文档检查）。

## Testing

- 按 acceptance 清单逐项执行；命令和输出记录在案。
- 使用真实 golden 音频/EPUB；网络测试可用 fake server，避免平台波动。
- 故障注入用 kill/信号/临时权限/磁盘配额，不修改生产数据。
- 批量测试用独立 `TROVE_HOME`，结束后清理。

## Out of Scope

- Phase 4 服务抽取（15–18）。
- 多租户/云端压测。
- 移动端 UI 验收；只做契约和关键路径回归。

## Notes

- 验收不是“再跑一遍测试”；要记录可复现的命令、环境、版本和数据规模。
- SLO 未达标不阻塞发布，但必须写明原因、影响和后续 issue；不允许静默忽略。
- 如果 Docker 与 launchd 行为不一致，先记录差异，再决定是否阻塞发布。

## Implementation

- 交付物：[acceptance.md](../acceptance.md) 合并 Pass 1/2/3，包含环境、版本、命令、结果、SLO、例外和后续 issue。
- Pass 3 在 `59be2d0` 上完成 Docker/launchd 安装、视频/EPUB/播客链路、100 条容量、10k 搜索、Prometheus/Grafana/OTel、升级/回滚、Android 门禁。
- 未达标/未实测项已在 acceptance.md 明确：10k `/api/items` 列表（22）、30 分钟 p95 / ASR RTF / worker 恢复口径（23）、ASR 超时/ENOSPC、合集 Pass 2 沿用、Android 无真机、launchd 模型下载。
- 验证：`PLAYWRIGHT_BROWSERS_PATH=... ./scripts/check.sh --full` 通过；`scripts/android/check.sh` 通过；`scripts/check-docs.py` 133 files OK。

## Comments

- 2026-11-27: Docker 视频验收 pass 1。覆盖视频链路、Docker 持久化、分池、lease 恢复、ASR/AI 缓存、幂等、manifest/export/search、doctor/备份；未覆盖 EPUB/播客、Android、100 条容量、观测、launchd、完整 rollback。详细结果与 SLO 见 [acceptance.md](../acceptance.md)。
- 2026-11-27: 合集验收 pass 2（前 10 集）。作为合集入库并通过 download/asr/llm/index 分池完成 10 集（118 分钟音频，9 集新处理约 13 分钟，0 失败）；验证了合集创建/已有 Item 附着、批量并发、collection tag、collection reprocess、10 集导出和搜索。当前 collection API 不支持只导入前 N 集，本次先创建再删除 11–75；Bilibili 标题 100 讲但 yt-dlp 只返回 75 part。详见 [acceptance.md](../acceptance.md)。
- 2026-11-27: Pass 3 完成并关闭。当前 `59be2d0` 上完成 Docker 全新安装 18.52s、launchd 9.87s；视频/EPUB（本地+URL）/播客三链路；100 条容量（4.67s，0 失败）；10k 搜索 p95 75.5ms；worker crash lease 28.5s、API crash 2.7s、LLM 429/500 退避、死信、SQLite busy、权限写失败恢复；Prometheus 5 targets + Grafana 14 panels + OTel 单 trace 串起 API/4 阶段；0009→0010 升级与旧代码回滚；Android 全量 JVM/Compose/lint 通过。唯一确认未达标的已测 SLO：10k 时 `GET /api/items` 为 O(N)，p50 3.6s，已开 [22](22-paginate-item-list.md)；30 分钟 p95、短音频 RTF、worker 恢复口径为取样/定义缺口，已开 [23](23-slo-sample-gaps.md)。详见 [acceptance.md](../acceptance.md)。
- 2026-11-27: 同步 `main` 到 `ea64b89`（Docker 分层构建、Android SDK 自动配置）；rebase 无冲突。复跑 `check.sh --full`、`scripts/android/check.sh`、`docker-smoke.sh` 全部通过；端到端/SLO 数据仍以 `59be2d0` 的 Pass 3 为准，未重跑完整验收。同步说明已写入 [acceptance.md](../acceptance.md)。
- 2026-11-27: Android 真机补测完成。设备 Android 16 / API 36，真实 Docker Host + USB adb reverse；按用户要求不测飞行模式和锁屏。覆盖 Library 同步、播放/后台/通知、下载、Transcript、EPUB 阅读/书内搜索、搜索、Tag/进度同步、Add、合集、设置/设备；`scripts/android/device-check.sh` 通过。未执行：密码登录/退出、Inbox 失败重试（真实库无 failed Item）、中文 IME、批量下载、60 分钟后台、HTTPS/release。清理了测试 EPUB、Tag 和进度。详见 [acceptance.md](../acceptance.md)。
