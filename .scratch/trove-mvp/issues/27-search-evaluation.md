# 27 — 50+ 条内容搜索评估

Status: ready-for-human  
Type: task  
Milestone: M3  
Blocked by: 14, 15  
Spec: [spec.md](../spec.md)  
Requirements: FR-51, FR-52, NFR-05

## Context

搜索是 MVP 的核心价值，不能只用几个好搜的例子验证。需要用 50+ 条真实内容、30 个预注册 query，按 Item 判分，记录漏召回和首个相关结果排名。

## Scope

- 准备 50+ 条真实内容（可与 20 条管线集重叠，但不能只挑好搜的），覆盖视频/播客/书/不同来源/语言。
- 30 个预注册 query：10 个已知条目、10 个探索式、10 个两字中文词。
- 按 Item 判分：相关 = 该 Item 有段落提到/回答 query；段落作为证据；记录漏召回。
- 指标：recall@10、首个相关结果排名、按内容类型分列；用户判分，LLM 只辅助。
- 结果和未达标行动（调权重/分段/索引）记录。

## Acceptance Criteria

- [ ] 50+ 条内容入库并完成转写/整理/索引。
- [ ] 30 个 query 预注册，未在看到结果后修改。
- [ ] 记录每个 query 的命中 Item、排名、证据段落、漏召回。
- [ ] 汇总 recall@10、首个相关排名、按类型分列。
- [ ] 两字中文 query 全部可被搜索接口处理；漏召回有解释。
- [ ] 结果可供 29 验收引用；不达标进入改进 issue。

## Testing

- 手动判分；可用 LLM 辅助生成候选但最终由用户判断。
- 评估脚本/表格可重复运行；query/corpus 清单保留。
- 不做语义检索评估（P2）。

## Out of Scope

- 向量/语义检索、推荐；P2。
- 大规模众包评估；个人验证即可。

## Comments

2026-11-10 — Added `scripts/evaluate-search.py` plus pure scoring helpers in
`src/trove/evaluation.py` (recall@10, first relevant rank, misses, result types,
and per-content-type recall).
The pre-registration and result template is `.scratch/trove-mvp/search-evaluation.md`.
The 30 real queries and manual Item judgments remain human work.
