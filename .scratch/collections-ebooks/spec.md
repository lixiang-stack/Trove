# 视频合集与电子书直链 — Feature Spec

Status: ready-for-agent
Feature: collections-ebooks
Date: 2026-11-17
Scope: Host 合集识别/入库、EPUB 直链入库、Host Console 合集管理、Android 添加页自动识别 + Library 合集卡片 + 合集详情
Sources: [原型](prototype/index.html)、[GLOSSARY](../../GLOSSARY.md)、[V1 spec](../trove-v1/spec.md)、[ADR-0010](../../docs/adr/0010-video-collection-aggregate.md)、[ADR-0011](../../docs/adr/0011-epub-url-intake.md)

## Problem Statement

当前添加页只接受 B 站/YouTube **单条视频** URL：Host 的 URL 规范化主动拒绝 playlist/多 P，yt-dlp 也强制 `--no-playlist`；EPUB 只能从 Host Console 上传，App 不能粘贴电子书链接。用户手里经常是合集链接（B 站多 P/合集/系列、YouTube playlist）或 EPUB 直链，必须手工拆成单集/先下载到 Mac 再上传，成本高且容易漏集。

需要让用户只粘贴一条链接，由 Host 自动识别「单集视频 / 视频合集 / EPUB 直链 / 播客 feed」，预览确认后入库；合集在 Library 中聚合，电子书直链走现有 EPUB 管线。

## Solution

- 添加页保留一个统一「链接」输入框；粘贴后调用 Host 检测接口，展示识别预览，确认后创建。
- Host 新增 `Collection` 聚合与链接检测：B 站多 P/合集/系列、YouTube playlist 识别为合集；`watch?v=&list=` 识别为单集；EPUB 直链识别为电子书；RSS/Atom 识别为播客 feed。
- 合集按单集 `source_key` 幂等展开成多个 Item；每集完整处理，单集失败隔离；已有单集无合集归属时并入，已属于其他合集时跳过并提示。
- 电子书直链新增 `EPUB_URL` SourceType：下载 → EPUB 校验/解析 → 整理 → 索引。
- Library 中合集只显示一张卡片，子集不进入主列表；新增合集详情页。
- Host Console 添加页统一链接面板；Library 增加合集入口；新增 `/collections` 列表和只读详情（重试/删除）。
- Android 不新增独立 Collection 同步实体：Host 在 Item 上携带 `collection_id/index/title/platform`，Android 从 Item 派生合集卡片和详情；删除/解散合集通过 Item 的 content_seq 变化同步。Host 的 Collection 表仍是合集元数据与 Host Console 的事实源。

## User Stories

1. 作为内容收藏者，我想粘贴 B 站/YouTube 链接后看到「识别为单集/合集」，以便知道会添加什么。
2. 作为内容收藏者，我想在合集预览里看到集数、总时长、已有单集和上游移除提示，以便判断规模与影响。
3. 作为内容收藏者，我想确认后一次性创建合集内所有单集，并让 Host 按顺序处理，以便不用逐集粘贴。
4. 作为内容收藏者，我想重复添加同一个合集时只追加新集、保留已有进度，以便追更。
5. 作为内容收藏者，我想合集在 Library 中只占一张卡片，点进去看单集，以便不淹没队列。
6. 作为内容收藏者，我想在合集详情里单独重试失败单集，以便一集失败不影响其他集。
7. 作为内容收藏者，我想删除合集时选择「删除全部单集」或「仅移除分组」，以便按意图清理。
8. 作为读者，我想粘贴可直接下载的 EPUB 直链并入库，以便不用先下载到 Mac 再上传。
9. 作为读者，我想 EPUB 直链在下载后显示真实书名/作者/封面，并走现有阅读/搜索，以便与上传的 EPUB 一致。
10. 作为 Host 所有者，我想在 Host Console 看到合集列表和只读详情，以便管理失败项和删除合集。
11. 作为手机用户，我想继续按单集手动下载离线文件，以便合集不会自动撑爆手机存储。

## Scope

### 链接识别

| 输入 | 识别 |
| --- | --- |
| YouTube `playlist?list=...` | 合集 |
| YouTube `watch?v=...&list=...` | 单集；忽略 list，并提示 |
| B 站 `/video/BV...` 无 `?p=` 且实际多 P | 合集 |
| B 站 `/video/BV...?p=N` | 单集（第 N P） |
| B 站 `/video/BV...` 实际单 P | 单集 |
| B 站 `space.bilibili.com/.../channel/collectiondetail?sid=...` | 合集 |
| B 站 `space.bilibili.com/.../channel/seriesdetail?sid=...` | 合集 |
| 直接 `.epub` / `application/epub+zip` | 电子书 |
| RSS/Atom feed | 播客 feed |
| 其他 | 明确拒绝，说明支持范围 |

- 检测只读元数据，不下载媒体。
- 检测超时约 20 秒；失败可重试，不静默降级成单集。
- 合集中超过 100 集或总时长超过 100 小时时，在预览阶段拒绝（config 可调）。
- 上游无法给出总时长时仍执行集数上限，预览显示「时长未知」。

### 合集

- 全量处理：每集 `downloading → extracting_audio → transcribing → organizing → indexing`，worker 串行；单集失败不影响其他集。
- 去重：按单集 canonical URL / `source_key`；已存在且无合集归属的 Item 并入并保留 artifacts/进度；已属于其他合集的跳过并提示。
- 重加：刷新合集元数据、追加新集；上游已移除的集本地保留，预览提示数量。
- 删除：`delete_items` 软删除合集和全部子 Item，并清空子 Item 的 Consumption State、播放/阅读位置和 last_consumed_at；`ungroup` 软删除合集、子 Item 保留为独立内容，进度不变。
- 不自动追更、不做合集级摘要/Tag、不做播放全部/Up Next、不自动下载到手机。

### 电子书

- 只支持可直接下载、DRM-free、可重排的 EPUB 2/3。
- 下载沿用 `max_epub_bytes`（默认 100 MB）、SafeHttpClient SSRF/重定向/大小校验。
- 按最终 canonical URL 去重；同 URL 再次添加返回已有 Item。
- PDF、电子书详情页、需要登录/Cookie 的链接不支持，返回明确错误。

## Data Model

### `collections`

- `id`, `source_key` (unique), `source_url_raw`, `source_url_canonical`
- `platform`, `title`, `author`
- `episode_count` (已入库单集数), `total_duration_sec`
- `deleted_at`, `created_at`, `updated_at`

### `items` 新增

- `collection_id` nullable FK → `collections.id` (ON DELETE SET NULL)
- `collection_index` nullable int
- unique `(collection_id, collection_index)`

### Content Package

每个合集子 Item 的 `source.json` 增加：

```json
{
  "collection": {
    "source_key": "https://...",
    "title": "从零开始做个人知识库",
    "author": "老周",
    "platform": "bilibili",
    "source_url": "https://...",
    "index": 3
  }
}
```

- 导出后分组信息不丢。
- 「仅移除分组」时从每个子 Item 的 `source.json` 移除该块。
- 合集封面取第一个有 cover 的子 Item；没有则用占位图。

### 同步

- `SyncItemSchema` / Android `SyncItemDto` 增加：`collection_id`, `collection_index`, `collection_title`, `collection_platform`, `collection_source_url`.
- Host 的 collection 变更（创建/元数据/删除/解散）通过 bump 子 Item 的 content_seq 同步到 Android。
- Android 不新增 Collection Room 表；`LibraryRepository` 从 Item 派生 `CollectionCard`。
- 删除全部：子 Item tombstone；仅移除分组：子 Item `collection_id=null`，content_seq bump。

## API

### `POST /api/intake/inspect`

请求：`{"url": "..."}`

响应（按 kind 分支）：

```json
{
  "kind": "video | collection | ebook | podcast_feed",
  "raw_url": "...",
  "canonical_url": "...",
  "title": "...",
  "author": "...",
  "platform": "bilibili | youtube | web | podcast",
  "duration_sec": 0,
  "episode_count": 12,
  "total_duration_sec": 22800,
  "file_size": null,
  "content_type": null,
  "episodes": [{"title": "...", "url": "...", "duration_sec": 1694}],
  "collection": {"id": "...", "existing_episode_count": 1, "upstream_removed_count": 1},
  "feed": {"title": "...", "author": "...", "episodes": [...]},
  "warnings": [{"code": "collection.upstream_removed", "message": "...", "count": 1}]
}
```

- `kind=video` 时 `episodes` 为空。
- `kind=collection` 时 `episodes` 返回前 10 集预览，`episode_count` 为上游总数。
- `kind=ebook` 时 `file_size`/`content_type` 有值，`title` 为文件名。
- `kind=podcast_feed` 时 `feed` 复用现有 FeedPreview 结构。

### `POST /api/collections`

请求：`{"url": "..."}`（Host 重新检测，不信任客户端预览）

响应：

```json
{
  "collection": { ... },
  "added_count": 10,
  "attached_count": 1,
  "skipped_count": 1,
  "run_count": 10,
  "warnings": [...]
}
```

- 重复添加幂等；已存在集不重复创建。
- 超过上限返回 `collection.too_large`。

### `GET /api/collections` / `GET /api/collections/{id}`

- 列表：合集摘要 + 状态计数。
- 详情：合集 + 单集摘要（id/title/index/duration/processing_state/has_audio/has_book）。

### `DELETE /api/collections/{id}?mode=delete_items|ungroup`

- `delete_items`：软删除合集 + 子 Item，并重置子 Item 的 Consumption State、播放/阅读位置和 last_consumed_at；重新添加时不恢复旧进度。
- `ungroup`：软删除合集；子 Item 保留，`collection_id/index=null`，进度不变。

### `POST /api/collections/{id}/retry-failed`

- 对合集内所有 failed 子 Item 创建新 Run。

### `POST /api/items` 新增 `kind: "ebook_url"`

- `url` 必填；创建 `EPUB_URL` Item + Run；重复 URL 返回已有 Item。

### Host Console

- `POST /add/link/preview`（HTMX）→ 预览 partial
- `POST /add/link` → 按检测类型分派：单集/电子书重定向 Item 详情；合集重定向 `/collections/{id}`；feed 显示选集
- `GET /collections`、`GET /collections/{id}`
- `POST /collections/{id}/delete`（mode）
- `POST /collections/{id}/retry-failed`

## Android UI

- Add：统一链接框；600ms 防抖检测；状态 `idle/detecting/preview/error/result`；预览卡按类型展示；播客 feed 展开选集；提交后显示结果/进度。
- Library：`LibraryEntry` = CollectionCard | Item；合集卡片只占一行；子集不进入主列表；筛选把合集当整体（任一子集命中）；合集算 1 条；排序按合集最近添加/最近消费。
- Collection detail：头部（封面/标题/平台/集数/处理与消费进度/失败计数）+ 单集列表；单集播放/阅读、单独重试、下载状态；右上角更多 → 删除合集；删除对话框两种语义。
- 不新增 Collection Room 表；从 `ItemEntity.collection*` 字段派生。
- Search/Continue 仍以单集 Item 为单位。
- 手机离线下载仍按单集手动。

## Error Codes

- `link.empty`, `link.scheme`, `link.credentials`, `link.unsupported`
- `link.live_not_supported`
- `inspect.timeout`, `inspect.failed`
- `collection.too_large`, `collection.empty`, `collection.not_found`
- `collection.episode_invalid`
- `ebook.invalid_type`, `ebook.too_large`, `ebook.not_found`
- 复用 `download.*`, `epub.*`, `feed.*`, `auth.*`

## Acceptance Criteria

- [ ] Host 能识别 B 站多 P/合集/系列、YouTube playlist、EPUB 直链、RSS；`watch?v=&list=` 识别为单集并提示。
- [ ] 合集预览显示集数/总时长/已有单集/上游移除；超过上限拒绝。
- [ ] 创建合集按单集幂等；已有单集并入；其他合集冲突跳过；新集创建 Run。
- [ ] 重复添加只追加新集；上游移除集本地保留。
- [ ] 合集子 Item 完整处理；单集失败可单独重试。
- [ ] 删除合集两种语义正确；Content Package / manifest 同步正确。
- [ ] EPUB 直链下载、校验、解析、书名/作者/封面、阅读/搜索可用；PDF/详情页明确拒绝。
- [ ] Host Console `/add` 统一链接面板、`/collections` 列表/详情/重试/删除可用。
- [ ] Android Add 自动检测/预览/提交/错误映射；合集结果与进度可见。
- [ ] Android Library 合集卡片、筛选/排序、合集详情、重试、删除两种语义可用。
- [ ] Host seam、Android seam、contract fixture、browser 测试绿；真机验收完成。

## Non-Goals

- 自动追更/定时轮询、合集级 AI 摘要/Tag、合集封面编辑、合集重命名。
- 播放全部/自动下一集/Up Next。
- 合集自动下载到手机、合集内选集入库。
- PDF、电子书站点解析、需要登录/Cookie 的 EPUB 直链。
- Host Console 合集重命名/Tag 编辑。
- 视频播放。

## Testing

- Host seam：真实 FastAPI/SQLite/FTS5/ContentPackage；fake yt-dlp/HTTP/feed；覆盖识别分类、limits、合集幂等/并入/冲突/移除、删除两模式、EPUB 直链、manifest、API contract、Host Console 浏览器。
- Android seam：fake `TroveApi` + 真实 Room/ Robolectric；覆盖 inspect 预览、合集提交、Library 派生卡片/筛选、合集详情/删除、契约 DTO、Room migration。
- Golden：真实公开领域 EPUB、合集元数据 JSON、podcast RSS；不伪造版权内容。
- 真机：添加 B 站多 P + YouTube playlist + EPUB 直链；Library 合集卡片/详情/重试/删除；离线单集下载；阅读 EPUB。
