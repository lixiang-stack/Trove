# 21 — V1 API 契约审计与 OpenAPI

Status: ready-for-agent
Type: task
Milestone: M3
Blocked by: 03, 04, 05, 06, 07, 08
Spec: [spec.md](../spec.md)
Tech: [tech-selection.md](../tech-selection.md)
Requirements: FR-73, NFR-08
ADRs: [0008](../../../docs/adr/0008-content-package-as-source-of-truth.md), [0009](../../../docs/adr/0009-native-android-client-app-managed-sync.md)

## Context

V1 的 Host API 是 Android 的唯一契约。需要一次审计：新端点/认证/错误/分页/文件 Range/ETag/同步 payload 与文档一致，Android DTO 与 Host fixture 不漂移，旧 MVP 路由不回归。

## Scope

- OpenAPI 覆盖 device token/devices、sync manifest/state、files、progress/tags 扩展、soft delete、health capabilities。
- Security scheme：Cookie 和 Bearer 并存；登录/health 公开；受保护端点声明认证。
- 错误形状 `{code,message,details?}`；稳定错误码；`applied:false` 不是 HTTP 错误。
- 分页/cursor/epoch/compact payload 字段与 spec/tech selection 一致。
- 文件响应 ETag/Range/If-Range/sha256；不泄漏路径/密钥/堆栈。
- 共享 contract fixture：Host 测试生成/校验；Android DTO/App 测试消费。
- 旧 MVP 端点/HTML 行为回归。

## Acceptance Criteria

- [ ] OpenAPI 包含全部 V1 端点，请求/响应 schema 与实现一致。
- [ ] Cookie 和 Bearer 认证标记正确；CSRF 只作用于 Cookie 写。
- [ ] 错误/分页/cursor/epoch/compact payload 与 fixture 一致。
- [ ] 文件 ETag/Range/If-Range/sha 契约通过；无路径/密钥泄漏。
- [ ] Android DTO 能解析 Host fixture；无两端字段漂移。
- [ ] 旧 MVP API/HTML 测试全绿。

## Testing

- Host seam：OpenAPI 关键路径/schema、认证、错误、分页、文件契约、脱敏。
- Android DTO/contract fixture 测试。
- 不做完整代码生成；手写 thin client + fixture。

## Out of Scope

- Android 功能实现；由 09–20 完成。
- API 版本前缀/迁移策略；V1 用 capabilities + additive 变更。
