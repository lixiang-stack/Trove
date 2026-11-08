# 17 — DeepSeek 摘要、Tag 与整理阶段

Status: ready-for-agent  
Type: task  
Milestone: M2  
Blocked by: 06, 13, 16  
Spec: [spec.md](../spec.md)  
Requirements: FR-25, FR-26, FR-27, FR-29, FR-30, NFR-02, NFR-09  
ADRs: [0007](../../../docs/adr/0007-deepseek-organization-limits.md)

## Context

入库后需要自动生成 1–2 句摘要和 3–5 个 Tag，避免用户手动整理。DeepSeek 接收分块转写/书文本；必须记录模型/prompt 版本和 token 用量，并按 token/调用数限额而不是金额止损。

## Scope

- DeepSeek `deepseek-flash` 客户端（OpenAI 兼容），JSON 模式；prompt 版本化。
- 短文本单次；长文本 20k 字符分块 map-reduce；输出摘要 + 候选 Tag。
- Tag 归一化：NFKC/小写/去 `#`/英文单数化；把现有 Tag 词表传给模型，优先复用；MVP 不做全局合并。
- `ai.json` 与 `ai_results`：summary、tags、model、prompt_version、input/output tokens、cost_usd、generated_at。
- 限额：`chunk_chars=20000`、`max_calls_per_item=16`、`max_output_tokens_per_call=1024`、`max_input_tokens_per_item=200000`；超限 `llm.limit_exceeded`；空白 JSON 重试一次。
- Organizing 阶段接入 Run；失败/超限不阻塞音频/文本消费；支持只重跑整理/索引。
- Add 页隐私提示：转写/书文本会发送给 DeepSeek；测试可关闭 LLM。

## Acceptance Criteria

- [ ] 用 fake LLM 可生成摘要和 3–5 个 Tag；Tag 经过归一化，重复/同义不重复出现。
- [ ] 长文本按块 map-reduce，摘要覆盖全文；不静默截断。
- [ ] 记录模型/prompt 版本/token/成本；可在详情/API 追溯。
- [ ] 超过任一限额时 Run 标记 `llm.limit_exceeded`，音频/transcript 仍可播放/阅读。
- [ ] 真实 DeepSeek 手动测试 20 条内容，Tag 可用率 ≥70%（与 28 一起记录）。
- [ ] 重新整理只重跑 organizing/indexing，不重新下载/转写。

## Testing

- Host seam + fake Organizer：短文本、长文本分块、Tag 归一化、限额、空白 JSON、失败。
- 纯函数：Tag 归一化、chunk 切分、usage/cost 计算。
- 真实 DeepSeek 测试标记为 `network`/手动；不默认跑。
- 隐私提示的页面断言。

## Out of Scope

- 实体抽取、Topic、embedding、语义检索；P2/Later。
- 全局 Tag 重命名/合并；P2。
