# 19 — 产品化验收：端到端、故障恢复与容量基准

Status: ready-for-agent
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

- [ ] Docker 和 launchd 两条安装路径都完成一次全新安装；时间记录。
- [ ] 视频/EPUB/播客三条链路完成并可搜索；重跑/取消可用。
- [ ] 长 ASR 期间下载/整理不被阻塞（或记录实际并发行为）。
- [ ] 故障注入场景全部有预期结果；无静默丢任务。
- [ ] 100 条批量测试完成；记录 SLO 达标情况。
- [ ] Android 契约测试通过；无 P0/P1 回归。
- [ ] 升级/回滚演练通过；数据不丢。
- [ ] `acceptance.md` 完成，例外和后续 issue 明确。
- [ ] `./scripts/check.sh` 全绿（含文档检查）。

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

## Comments

- 2026-11-27: Docker 视频验收 pass 1。覆盖视频链路、Docker 持久化、分池、lease 恢复、ASR/AI 缓存、幂等、manifest/export/search、doctor/备份；未覆盖 EPUB/播客、Android、100 条容量、观测、launchd、完整 rollback。详细结果与 SLO 见 [acceptance.md](../acceptance.md)。
- 2026-11-27: 合集验收 pass 2（前 10 集）。作为合集入库并通过 download/asr/llm/index 分池完成 10 集（118 分钟音频，9 集新处理约 13 分钟，0 失败）；验证了合集创建/已有 Item 附着、批量并发、collection tag、collection reprocess、10 集导出和搜索。当前 collection API 不支持只导入前 N 集，本次先创建再删除 11–75；Bilibili 标题 100 讲但 yt-dlp 只返回 75 part。详见 [acceptance.md](../acceptance.md)。
