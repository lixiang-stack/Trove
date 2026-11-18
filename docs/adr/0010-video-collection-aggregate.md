# 视频合集作为 Collection 聚合，Android 从 Item 派生卡片

合集（B 站多 P/合集/系列、YouTube playlist）需要作为一个可识别的整体存在于 Library，但合集本身不可播放/不可读；可消费单位仍然是单集 Item。Host 新增 `Collection` 聚合表，Item 通过 `collection_id` + `collection_index` 归属合集；合集元数据（标题、作者、平台、来源 URL）同时写入每个子 Item 的 `source.json` 的 `collection` 块，保证 Content Package 可移植、可重建。合集没有自己的 Processing Run，处理状态由子 Item 的 Run 派生。

Android 不新增独立的 Collection Room 表/同步流：manifest 的每个 Item 携带 `collection_id/index/title/platform/source_url`，客户端从 Item 派生合集卡片和合集详情；合集删除/解散通过 bump 子 Item 的 `content_seq` 同步。这样保持 V1 的单内容流、单游标和 tombstone 语义，避免为合集再造一条分页/冲突/离线同步链路。Host 的 `Collection` 表仍是 Host Console 与合集元数据的事实源。

**Status**: Accepted · 2026-11-17

## Considered Options

- 单独一条 Collection 同步流：语义更纯，但需要第二个游标、跨流分页、合集 tombstone、Android Room 实体与迁移，增加 V1 同步复杂度；当前 UI 只需要卡片元数据，Item 已能携带。
- 复用 Item 作为父条目：会破坏「Item 是可消费内容单位」的领域含义，播放/阅读/下载都要处理一个不可消费的父 Item。
- 展开成 N 个无归属 Item：实现最省，但 Library 无法聚合、无法看整体进度，等于没有真正支持合集。

## Consequences

- `collections` 表 + `items.collection_id/index`；`source.json` 增加 `collection` 块。
- 合集元数据/成员变化必须 bump 受影响子 Item 的 `content_seq`；否则 Android 卡片不会更新。
- 合集删除两种语义在 Host 落地：删除全部（子 Item tombstone）或仅移除分组（子 Item `collection_id=null` 并 bump）。
- 合集状态（处理/消费计数）由子 Item 派生，不落库；Host Console/Android 各自计算。
- 合集上限（默认 100 集 / 100 小时）在检测/创建阶段统一执行。
- 未来如果出现合集级摘要、订阅、播放队列，再评估是否升级为独立同步流；当前不预付这个复杂度。

## Related

- [Feature spec](../../.scratch/collections-ebooks/spec.md)
- [ADR-0008: Content Package as source of truth](0008-content-package-as-source-of-truth.md)
- [ADR-0009: Native Android client + app-managed sync](0009-native-android-client-app-managed-sync.md)
