# DeepSeek 整理按 token/调用数限额，不按金额止损

MVP 用 DeepSeek `deepseek-flash` 生成 1–2 句摘要和 3–5 个 Tag；长文本按 20k 字符分块 map-reduce，JSON 模式输出。预算不按美元金额阻断，而是限制单次输出 tokens、单条调用数和单条输入 token 总量；实际 token 和估算成本只记录，避免价格波动/估算误差误伤正常内容。

**Status**: Accepted · 2026-11-08

## Considered Options

- 按金额预算（如 $0.02/条）：价格和 token 估算变化会让同一内容时好时坏；用户明确选择 token/调用数限额。
- 本地 LLM：未来可换，但 MVP 不引入模型部署/显存运维。
- 其他云 API：DeepSeek 中文摘要/Tag 成本低、OpenAI 兼容；适配器可替换。

## Consequences

- 默认 `max_output_tokens_per_call=1024`、`max_calls_per_item=16`、`max_input_tokens_per_item=200000`、`chunk_chars=20000`；超限标记 `llm.limit_exceeded`，不静默截断。
- 1 小时转写约 1–2 次调用；10 万字符书约 5–6 次；异常长文本会被明确拒绝。
- 转写/书文本会分块发送给 DeepSeek；Add 页提示，不做 per-item 开关（NFR-02）。
- 见 [技术选型](../ideas/trove-tech-selection.md) 第 3.4 节；需求 FR-25/26/29/30、NFR-02/09。
