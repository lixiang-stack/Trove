# 17 — Android Add、分享与播客入库

Status: ready-for-agent
Type: task
Milestone: M2
Blocked by: 09, 10
Spec: [spec.md](../spec.md)
Tech: [tech-selection.md](../tech-selection.md)
Requirements: FR-69
ADRs: [0009](../../../docs/adr/0009-native-android-client-app-managed-sync.md)

## Context

手机是主要入库入口之一。需要从其他 App 分享 URL、粘贴视频 URL、预览播客 feed 并选集；所有 URL/平台/SSRF/大小校验由 Host 执行，Android 只负责预填、提交和展示状态。

## Scope

- `ACTION_SEND` `text/plain`：提取第一个 URL，预填 Add。
- 手动粘贴 B 站/YouTube 单视频 URL；playlist/多 P 拒绝由 Host 返回。
- 播客 feed URL → `/api/feeds/preview` → 选集 → `POST /api/items`。
- 重复添加返回已有 Item 并打开详情。
- Add 页持续显示 DeepSeek 数据流提示。
- 提交后显示 Processing State；前台轮询/退避；失败原因中文映射；支持重试失败 Run。
- 不支持手机上传本地音频/EPUB。

## Acceptance Criteria

- [ ] 从其他 App 分享 URL 能打开预填的 Add 页并提交。
- [ ] 单视频入库成功；playlist/多 P 显示明确拒绝。
- [ ] 播客 feed 预览/选集/入库可用；重复 URL 打开已有 Item。
- [ ] DeepSeek 提示可见；处理中/失败/重试状态正确。
- [ ] 内网/不支持平台/超大文件错误来自 Host 且可读。
- [ ] 关闭 App 后 Host 继续处理；下次同步更新状态。

## Testing

- App seam：分享 intent 解析、Add 表单、播客预览、重复/拒绝/错误状态、处理轮询。
- Host API 用 fake；URL 校验真实逻辑由 Host seam 覆盖。
- 真实 Host：分享/粘贴一条视频 + 一个播客 feed。

## Out of Scope

- 手机上传本地文件；继续走 Host Console 浏览器。
- RSS 自动轮询/订阅、批量导入。
