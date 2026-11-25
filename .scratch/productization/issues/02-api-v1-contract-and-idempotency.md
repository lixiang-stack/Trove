# 02 — API v1 契约、版本与幂等策略

Status: resolved
Type: task
Milestone: P0
Blocked by: 01
Spec: [spec.md](../spec.md)
ADRs: [0009](../../../docs/adr/0009-native-android-client-app-managed-sync.md)

## Context

当前 API 有 OpenAPI、`contract/*.json` 和稳定错误码，但没有明确的版本策略、幂等约定和错误信封扩展规则。Android 客户端是第一方、可锁步，但产品化后还会有 CLI、脚本和未来的第三方集成；需要在不破坏现有客户端的前提下把契约固定下来。

## Scope

- 写 `docs/api-contract.md`（或扩展现有文档），定义：
  - `/api` 下 additive 变更规则；破坏性变更开 `/api/v2` 的流程和兼容窗口。
  - `api_version` 语义：什么时候 bump；`/api/health` 如何暴露。
  - 错误信封 `{code, message, details, request_id}`；`request_id` 的生成和回传。
  - 创建型 POST 的 `Idempotency-Key` 语义：重复键返回同一响应；至少覆盖 `POST /api/items`。
  - 分页/排序/过滤参数的稳定性；新增字段不得改变旧字段语义。
  - Run 进度 v1 继续轮询；SSE/webhook 只记录为后续选项，不实现。
- 在 API 中间件/依赖中加 `request_id`，写入响应头和结构化日志；不改变现有响应体字段。
- 为 `POST /api/items` 实现幂等键：内存/SQLite 持久化均可，TTL 至少 24 小时；重复请求返回原响应，不重复创建 Item/Run。
- 更新 OpenAPI 描述和合约 fixture；保证 Android 现有字段不变。

## Acceptance Criteria

- [x] `docs/api-contract.md` 覆盖版本、错误、幂等、分页、Run 进度和兼容规则。
- [x] 所有 API 响应带 `X-Request-ID`；日志包含同一个 `request_id`。
- [x] `POST /api/items` 带同一 `Idempotency-Key` 重放时返回相同 `item.id`/`deduplicated`，不新增 Run。
- [x] 不带幂等键的现有调用行为不变。
- [x] 错误响应体仍能被现有 Android/CLI 解析；新增字段可选。
- [x] OpenAPI 与 `contract/*.json` 的一致性测试通过。
- [x] 现有 auth/sync/items 测试保持绿。

## Testing

- API 测试：同一幂等键两次 POST；并发两次 POST；不同键两次 POST。
- 中间件测试：`X-Request-ID` 透传/生成；日志字段断言。
- 合约测试：OpenAPI 路径/字段与 fixtures 对齐。
- 回归：现有 Android 契约 fixtures 不变。

## Out of Scope

- 引入 OAuth/OIDC、API key 配额、计费。
- SSE/webhook 实现。
- 把现有所有路由迁到 `/api/v1`；本 issue 只定义策略，不强制路径迁移。
- 重写 `sync_mutations` 的现有幂等语义。

## Notes

- 幂等存储优先复用 SQLite，不引入 Redis；键值包含 method/path/body hash，响应保存状态码和 JSON。
- 如果 `POST /api/items` 的重复检测已经由 `source_key` 完成，幂等键只负责“同一请求重放返回同一响应”，不要改变去重语义。

## Implementation

- 新增 `docs/api-contract.md`，定义 v1 additive 规则、错误信封、请求 ID、幂等、分页、Run 进度和兼容清单。
- 新增 `web/request_id.py`：所有 HTTP 响应带 `X-Request-ID`；合法客户端值透传，否则生成；安全/错误响应和日志带同一 `request_id`。
- 新增 `services/idempotency.py`、`idempotency_keys` 表和 Alembic `0006_idempotency_keys`；支持重放、请求指纹冲突、in-progress 冲突、5 分钟租约、24 小时完成 TTL 和 token 防陈旧覆盖。
- `POST /api/items` 接受 `Idempotency-Key`；重放返回原状态码/响应并带 `Idempotency-Replayed: true`；失败释放 key；无 key 行为不变。
- `ErrorResponse` 增加可选 `request_id`；OpenAPI 增加 `X-Request-ID` 响应头；`contract/health.json` 更新迁移 head，`contract/error.json` 增加 request_id。
- 新增 `tests/test_idempotency.py`（服务级并发/过期/token、API 重放/冲突/并发/请求 ID/日志）；更新契约、schema、安全测试。
- `./scripts/check.sh` 全绿。
