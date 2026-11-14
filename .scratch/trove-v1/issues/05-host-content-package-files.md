# 05 — Host Content Package 文件下载

Status: ready-for-agent
Type: task
Milestone: M0
Blocked by: 02, 03
Spec: [spec.md](../spec.md)
Tech: [tech-selection.md](../tech-selection.md)
Requirements: FR-73, NFR-08
ADRs: [0008](../../../docs/adr/0008-content-package-as-source-of-truth.md), [0009](../../../docs/adr/0009-native-android-client-app-managed-sync.md)

## Context

Android 要镜像 Content Package 的音频/transcript/book/book_json/ai/cover，并支持断点续传和校验。现有 `/audio` 只覆盖音频；需要一个受控的通用文件端点。

## Scope

- `GET /api/items/{item_id}/files/{kind}`，kind 白名单：`audio`、`transcript`、`book`、`book_json`、`ai`、`cover`。
- 只返回数据库 Artifact 记录的 Content Package 路径；拒绝任意路径/路径穿越。
- 响应 `ETag: "<sha256>"`、`Accept-Ranges: bytes`、`Cache-Control: private`、`X-Content-Type-Options: nosniff`。
- 使用 Starlette 1.10 `FileResponse` 的 Range/If-Range；ETag 不匹配时返回完整 200。
- 正确 MIME：JSON、EPUB、音频、封面。
- 现有 `/api/items/{id}/audio`、`/transcript`、`/book/chapters/{n}` 保持兼容。

## Acceptance Criteria

- [ ] 六种 kind 均可下载；缺失 artifact 返回 404/`file.artifact_missing`。
- [ ] 普通请求 200 + ETag；Range 请求 206 + Content-Range；If-Range 匹配续传，不匹配全量。
- [ ] sha256 与 Artifact 元数据一致；路径穿越/任意文件请求被拒绝。
- [ ] 未认证请求 401；Bearer 和 Cookie 都可访问。
- [ ] 现有 Web 音频/transcript/book 行为不回归。

## Testing

- Host seam：六种 kind、Range/If-Range、ETag、sha256、404、路径穿越、认证。
- 用真实小音频/JSON/EPUB fixture；不访问网络。
- 现有媒体/阅读测试回归。

## Out of Scope

- Android 下载队列/断点续传；由 12 实现。
- 修改 Content Package 布局或既有媒体响应语义。
