# 01 — Host 合集领域、链接检测与 EPUB 直链入库

Status: ready-for-agent
Type: task
Milestone: collections-ebooks
Spec: [spec.md](../spec.md)
ADRs: [0010](../../../docs/adr/0010-video-collection-aggregate.md), [0011](../../../docs/adr/0011-epub-url-intake.md)

## Context

Host 目前拒绝 playlist/多 P，且 EPUB 只能走本地上传。需要新增 Collection 聚合、链接检测、合集展开/幂等/删除、EPUB_URL 下载管线。

## Scope

- `Collection` model + migration（`collections`, `items.collection_id/index`）。
- `SourceType.EPUB_URL` / `Platform.WEB` + stages。
- URL 分类：B 站多 P/合集/系列、YouTube playlist/watch、EPUB 直链、RSS。
- yt-dlp flat 检测适配器（不下载媒体）+ SafeHttpClient EPUB HEAD/下载。
- `POST /api/intake/inspect`、`POST /api/collections`、`GET /api/collections[/{id}]`、`DELETE /api/collections/{id}?mode=`、`POST /api/collections/{id}/retry-failed`。
- `POST /api/items kind=ebook_url`。
- Content Package `collection` 块、导出保留。
- sync item 字段 + collection 变更 bump 子 Item content_seq。
- 上限、错误码、测试。

## Acceptance Criteria

- [ ] 识别表按 spec 工作；检测不下载媒体；超时/失败可重试。
- [ ] 合集创建幂等；已有单集并入；其他合集冲突跳过；新集创建 Run。
- [ ] 重复添加追加新集；上游移除集保留并提示。
- [ ] 删除两模式正确；source.json/manifest 同步正确。
- [ ] EPUB 直链下载/校验/解析/阅读/搜索/导出可用；PDF/详情页拒绝。
- [ ] `./scripts/check.sh --fast` + 新增 Host seam 测试绿。

## Out of Scope

自动追更、合集级 AI 摘要/Tag、播放全部、PDF/站点解析、需要登录的 EPUB 直链。
