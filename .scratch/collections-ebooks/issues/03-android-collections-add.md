# 03 — Android 添加页自动识别、Library 合集卡片与合集详情

Status: ready-for-agent
Type: task
Milestone: collections-ebooks
Spec: [spec.md](../spec.md)
Depends on: 01

## Context

Android 添加页目前只有单视频 URL + 播客 feed；Library 是扁平队列。需要统一链接检测、合集卡片/详情、EPUB 直链入库，并保持单内容流同步。

## Scope

- `Inspect` / `Collection` DTO + `TroveApi`。
- `ItemCreateRequestDto kind=ebook_url`；`SyncItemDto`/`ItemEntity` collection 字段 + Room migration。
- Add：单链接框、600ms 防抖检测、预览卡（单集/合集/电子书/feed）、确认提交、结果进度、错误映射。
- Library：从 Item 派生 `CollectionCard`；合集只占一行；筛选/排序把合集当整体；合集算 1 条。
- 合集详情新路由/页面：头部状态、单集列表、播放/阅读、单集重试、更多 → 删除两模式。
- 共享 contract fixture、Host seam fake、Compose/Robolectric 测试。
- 不新增 Collection Room 表/同步流。

## Acceptance Criteria

- [ ] Add 自动识别/预览/提交/错误提示可用；播客 feed 选集保持。
- [ ] EPUB 直链入库成功；重复 URL 打开已有 Item。
- [ ] Library 合集卡片、筛选/排序、详情、单集重试、删除两模式可用。
- [ ] 合集子集不进入主列表；Search/Continue 仍按单集。
- [ ] Room migration 与 `scripts/android/check.sh` 绿；真机验收截图/记录。
