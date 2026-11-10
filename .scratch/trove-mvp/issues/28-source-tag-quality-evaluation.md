# 28 — 来源成功率与 Tag/摘要质量评估

Status: ready-for-human  
Type: task  
Milestone: M3  
Blocked by: 07, 08, 09, 16, 17  
Spec: [spec.md](../spec.md)  
Requirements: FR-01, FR-03, FR-04, FR-25, FR-26, FR-27

## Context

管线可靠性不能只看单元测试：需要真实 B 站/YouTube/播客/EPUB/本地文件各 10 条，记录成功率和失败分类；同时用 20 条真实内容人工判断 Tag 可用率和摘要质量。

## Scope

- 来源矩阵：10 B 站 + 10 YouTube + 10 播客 + 10 EPUB + 10 本地文件。
- 记录成功/失败、失败原因（网络/登录/地区/DRM/解析/不支持）、耗时。
- 目标：B 站/YouTube/播客 8/10；EPUB/本地 10/10。
- 20 条真实内容：1–2 句摘要是否能概括、事实错误；3–5 个 Tag 人工判定可用率 ≥70%。
- Tag 归一化检查：大小写/单复数/同义词不重复。
- 失败/不达标行动：cookies、错误提示、解析修复、prompt/模型调整；不绕过 DRM/地区限制。

## Acceptance Criteria

- [ ] 五类来源各 10 条真实内容跑完，结果表包含成功/失败/原因/耗时。
- [ ] 来源成功率达标；未达标项有明确限制说明和用户可操作提示。
- [ ] 20 条内容摘要/Tag 人工评估记录；Tag 可用率 ≥70%。
- [ ] 失败原因分类与 UI 提示一致；无静默失败。
- [ ] 结果可供 29 验收引用；不达标进入改进 issue。

## Testing

- 手动真实来源测试；网络测试可分批执行。
- Tag/摘要由用户判分；LLM 只辅助。
- 失败案例保留 URL/错误码/日志 tail；不保存受版权保护内容到仓库。

## Out of Scope

- 绕过 DRM/地区限制；不做。
- 大众市场来源覆盖/合规；不做。

## Comments

2026-11-10 — Added the source matrix and Tag/summary review template at
`.scratch/trove-mvp/source-quality.md`. Real Bilibili/YouTube/podcast/EPUB/local
samples and human Tag judgments are still required; no copyrighted content is
stored in the repository.
