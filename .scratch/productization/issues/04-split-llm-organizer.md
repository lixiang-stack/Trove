# 04 — 拆分 LLMOrganizer 为 OrganizationWorkflow、ChatClient 与 PromptCatalog

Status: resolved
Type: task
Milestone: P1
Blocked by: none
Spec: [spec.md](../spec.md)

## Context

`src/trove/adapters/llm.py` 约 415 行，把 prompt、分块、map-reduce、token/调用限额、成本估算、HTTP 请求、JSON 重试都放在一个类里。它既难用 fake 测，也难以换 provider 或加幂等缓存。需要把“整理工作流”和“OpenAI 兼容传输”分开，同时保持 `Organizer` 端口和现有输出不变。

## Scope

- 新增 `services/organization.py`：`OrganizationWorkflow`，负责单块/多块 map-reduce、限额检查、tag 选择、成本估算；不 import `httpx`。
- 在 `ports.py` 增加 `ChatClient` 协议（或等价的最小接口）：接收 messages/参数，返回内容、usage、finish_reason。
- 新增 `adapters/openai_chat.py`：`OpenAICompatibleChatClient`，负责 URL、headers、超时、HTTP 错误分类、`Retry-After`。
- `adapters/llm.py` 变成薄适配器：`LLMOrganizer` 组装 workflow + client，保持 `organize()` 签名和 `OrganizationResult` 不变。
- 新增 prompt catalog（`adapters/llm_prompts.py` 或 `domain/organization_prompts.py`）：SYSTEM/MAP/SINGLE/REDUCE 文案和 `PROMPT_VERSION` 集中管理。
- 明确重试边界：HTTP 429/5xx/timeout 在 client 层分类为可重试错误并抛稳定 code；stage 级自动重试由 09 负责。JSON 解析重试保留在 workflow。
- 如果 prompt 文案不变，`PROMPT_VERSION` 保持 `organize-2`；任何影响输出的改动必须 bump 并记录。

## Acceptance Criteria

- [x] `adapters/openai_chat.py` 降到 250 行以内（`adapters/llm.py` 已删除）；workflow 文件不出现 `httpx`。
- [x] `LLMOrganizer.organize()` 签名、`OrganizationResult` 字段、错误码不变。
- [x] fake `ChatClient` 能覆盖：单块、多块 map-reduce、空文本、无效 JSON、缺 summary/tags、超 token/调用上限、429/5xx。
- [x] 现有 `test_organization.py`、`test_organizer_real.py`（如可运行）保持绿。
- [x] `PROMPT_VERSION` 和 prompt 文案有单一来源；不再散落在函数参数里。
- [x] `ruff`、`mypy` 通过；`test_complexity.py` 不因拆分出现新告警。

## Testing

- 单元：workflow + fake client，不触网；断言调用次数、输入分块、tag 选择、成本。
- 传输：`httpx.MockTransport` 覆盖 401/403/429/500、超时、非 JSON、缺 usage。
- 回归：现有组织测试和 host seam 的 organizing 阶段。
- 手动：用真实 LLM 跑一条短文本，确认 summary/tags 格式不变（可选，标记 network）。

## Out of Scope

- 多 provider 适配（Anthropic/Gemini 等）；本 issue 只抽 OpenAI 兼容边界。
- 幂等缓存（10）。
- 修改 prompt 语义或 tag 策略。
- 把 LLM 调用移到独立进程/服务（17）。

## Notes

- `ChatClient` 不要设计成通用 SDK；只覆盖 workflow 需要的 chat completion + JSON 模式。
- 如果 `reasoning_effort`/`response_format` 是 provider 特性，放到 client 的请求构造里，workflow 只传业务参数。

## Implementation

- `services/organization.py` 新增 `OrganizationWorkflow`：chunking、map-reduce、限额、tag 选择、成本估算都在这里；只依赖 `LLMConfig`、domain、`ChatClient`，不出现 `httpx`。
- `ports.py` 新增 `ChatClient.complete(messages, *, max_tokens) -> ChatResult`；`ChatResult` 携带 content、input/output tokens 和 finish_reason。
- `adapters/openai_chat.py` 新增 `OpenAICompatibleChatClient`：构造 OpenAI 兼容请求（`response_format`、`reasoning_effort`、temperature、URL、headers、timeout）；401/403 → `llm.not_configured`，429/5xx/timeout → `llm.failed`（429 带 `retry_after` details），非 JSON → `llm.invalid_output`。
- `domain/organization_prompts.py` 集中 `PROMPT_VERSION`（仍为 `organize-2`）和 SYSTEM/MAP/SINGLE/REDUCE 文案；与 `origin/main` 逐字比对一致。
- `composition.py` 组装 `OrganizationWorkflow(config.llm, OpenAICompatibleChatClient(config.llm, llm_http))`；`llm_http` 是组合根持有的单个 `httpx.Client(timeout=...)`，map-reduce 之间复用连接，所有权明确。
- 偏差：`LLMOrganizer` 不再保留为 adapter facade。05 引入的 import-linter 契约禁止 `trove.adapters -> trove.services`，adapter 组装 workflow 会破坏门禁；`OrganizationWorkflow` 成为 `Organizer` 实现，`organize()` 签名、`OrganizationResult` 字段和错误码保持不变。`adapters/llm.py` 删除，传输实现为 84 行的 `adapters/openai_chat.py`。
- 测试：`test_organization.py` / `test_organizer_real.py` 改为组装 workflow + client；新增 `tests/test_organization_workflow.py`（fake `ChatClient`：单块、map-reduce、空文本、无效 JSON、缺 summary/tags、调用/token 上限、tag 选择、成本、client 失败不触发 JSON 重试）和 `tests/test_openai_chat.py`（MockTransport：401/403/429/5xx/timeout/非 JSON/缺 usage）。
- 验证：`./scripts/check.sh --fast` / `./scripts/check.sh` 全绿；`uv run lint-imports` 6 kept / 0 broken；`test_complexity.py` 通过；新旧实现差分（单块、合集复用、map-reduce、无效 JSON、禁用、限额、length finish）结果与请求体一致。

## Comments

- 2026-11-25：完成拆分；为保持 05 的分层门禁，移除 `LLMOrganizer`，由 `OrganizationWorkflow` 直接实现 `Organizer`，组合根注入 `OpenAICompatibleChatClient`。
