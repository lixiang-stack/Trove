# 22 — JSON API、OpenAPI 与 Range/ETag 契约

Status: ready-for-agent  
Type: task  
Milestone: M3  
Blocked by: 05, 06, 11, 13, 14, 16, 17, 20  
Spec: [spec.md](../spec.md)  
Requirements: FR-82, FR-73, NFR-08  
ADRs: [0008](../../../docs/adr/0008-content-package-as-source-of-truth.md)

## Context

未来 Android 必须复用同一套 API/数据，不能另建库。功能完成后需要一次 API 契约审计：所有页面能力都有 JSON API、OpenAPI 完整、错误一致、媒体 Range/ETag 可用于 V1 可续传下载。

## Scope

- 审计 spec 第 5 节的端点是否全部实现；HTML 独有的数据不得只存在于模板。
- OpenAPI 文档完整：请求/响应 schema、错误形状、认证要求。
- 统一错误 `{code, message, details?}`；稳定错误码；404/401/409/422/429 语义。
- 认证：Cookie 会话可用于 API；Android 可复用 cookie jar；不新增 bearer（V1 再加）。
- 媒体：`GET audio` 支持 Range/ETag/Accept-Ranges；artifact 元数据 sha256/size/mime 可查询。
- 分页/过滤/排序参数一致性；不要泄漏内部路径。
- API 契约测试与文档示例。

## Acceptance Criteria

- [ ] OpenAPI 包含 spec 列出的全部 MVP 端点，schema 与实现一致。
- [ ] 未认证、未知 Item、重复添加、校验失败、限速返回稳定状态码/错误形状。
- [ ] 音频/文件响应带 ETag/Accept-Ranges，Range 请求返回 206；V1 manifest 所需元数据可通过 API 获取。
- [ ] HTML 页面所需数据均可通过 API 获取；没有 web-only 的数据模型。
- [ ] API 不返回服务器绝对路径/密钥/内部堆栈。
- [ ] 契约测试在 Host seam 上通过。

## Testing

- Host seam：端点覆盖/错误/认证/Range/ETag/分页/过滤。
- OpenAPI schema 快照或关键字段断言；不追求全量快照。
- 与 11/20 的媒体/导出测试共用 fixture。
- 不做 Android 客户端或代码生成。

## Out of Scope

- Android 客户端、代码生成、API 版本前缀/迁移策略；V1 再定。
- 同步 manifest/cursor/tombstone；V1。

## Comments

2026-11-10 — Completed the API contract audit: typed response schemas and OpenAPI
error/auth components, `GET /api/continue`, Item pagination (`limit`/`offset`),
artifact metadata without server paths, run-error/log path redaction, stable
`run.not_found`, and contract tests in `tests/test_api_contract.py`. Range/ETag
behavior is covered together with ticket 11 playback tests.
