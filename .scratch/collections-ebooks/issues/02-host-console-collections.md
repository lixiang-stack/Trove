# 02 — Host Console 添加页与合集管理

Status: ready-for-agent
Type: task
Milestone: collections-ebooks
Spec: [spec.md](../spec.md)
Depends on: 01

## Context

Host Console 是入库和管理端。需要把视频/播客/电子书 URL 收口到一个链接面板，并提供合集列表/只读详情/重试/删除。

## Scope

- `/add` 统一链接面板 + HTMX 检测预览；保留本地路径/上传文件面板。
- `POST /add/link/preview`、`POST /add/link`（按类型分派）。
- Library 头部「合集 N」入口。
- `GET /collections` 卡片列表；`GET /collections/{id}` 只读详情。
- 重试失败项、删除合集（两种 mode）。
- 现有 Library/搜索/筛选/计数不变。
- 浏览器测试。

## Acceptance Criteria

- [ ] 添加页可识别单集/合集/EPUB/播客 feed 并预览；确认后正确跳转。
- [ ] `/collections` 列表状态/进度正确；详情可查看单集、跳 Item、重试、删除。
- [ ] Library 入口可达；现有单集列表/筛选/搜索不回归。
- [ ] `tests/test_browser.py` 相关用例绿。
