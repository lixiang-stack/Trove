# 17 — 抽取整理服务（gated，Python）

Status: needs-triage
Type: task
Milestone: P4
Blocked by: 04, 08, 09, 10
Spec: [spec.md](../spec.md)

## Context

整理阶段是外部 LLM 调用，天然适合独立服务：无状态、IO 密集、需要配额/成本/密钥控制。L1 的 llm pool 已能隔离并发；只有在需要独立限流、成本核算、provider 切换或多机部署时，才抽成服务。实现继续用 Python；本 issue 不是 Go 试点。

## Scope

- 定义契约（HTTP）：
  - 输入：文本/标题/现有 tags/collection 上下文、prompt_version、模型、幂等键。
  - 输出：`OrganizationResult`（summary/tags/model/prompt_version/tokens/cost）或稳定错误码。
  - 健康、指标、版本、超时/取消。
- Python 服务：复用 `OrganizationWorkflow` + `ChatClient`；按部署配置密钥/模型；限流、重试、成本计量；不落 Item 内容日志。
- 调用侧：新增 `RemoteOrganizer` 适配器，实现 `Organizer` 端口；feature flag；保留 in-process fallback。
- 部署：Compose service / launchd agent；网络出口；密钥通过环境/secret 注入。
- 缓存：复用 10 的幂等 key；服务端和调用侧至少一侧生效，避免重复计费。

## Acceptance Criteria

- [ ] 契约文档和 contract fixtures 存在；错误码与现有 `llm.*` 对齐。
- [ ] `RemoteOrganizer` 通过 `Organizer` 合同测试；输出 schema 与 in-process 一致。
- [ ] 服务可独立限流/重启，不影响 API/ASR/下载。
- [ ] 密钥不出现在日志、响应、镜像；成本指标可读。
- [ ] feature flag 可一键切回 in-process；切换不丢任务。
- [ ] 现有组织测试和 host seam 在 remote 模式下通过。
- [ ] 部署文档更新。

## Testing

- 契约：同一输入，in-process vs remote 输出结构和 token/cost 字段一致。
- 故障：429/5xx/timeout、无效 JSON、服务重启。
- 幂等：同一 key 重放不重复调用/计费。
- 端到端：transcript/book → organizer service → ai.json → index。

## Out of Scope

- Go/Rust 重写。
- 多租户计费/配额。
- 多 provider 路由/A-B（可在后续 issue）。
- 把 ASR/下载也拆成服务（15/16）。

## Notes

- 整理服务是最适合做“无状态服务”的模块；如果未来要做语言试点，这里是第一站（但本 effort 明确不做）。
- 不要把 prompt 文案复制到服务端和调用侧两份；以 Python 包内的 prompt catalog 为准，服务端版本化。
- 如果服务端和客户端都缓存，确保 key 一致，避免双重 miss。
