# 内容包是便携事实源，数据库是可重建索引

Trove 要求本地拥有、可迁移、可重建，并为 V1 Android 的 manifest/可续传下载留接口。因此每个 Item 一个普通文件夹（`source.json`、音频、`transcript.json`、`book.epub`/`book.json`、`ai.json`、封面），SQLite 只存元数据、处理状态、消费进度和 FTS 索引；文件写入先临时文件再原子 rename，artifact 记录 sha256/size/mime，媒体响应带 ETag/Range。

**Status**: Accepted · 2026-11-08

## Considered Options

- 只存数据库/对象存储：不便携、不可直接导出/迁移，违背本地拥有。
- MVP 就做同步/tombstone：V1 需求，当前不做；只预留文件元数据和 HTTP 语义。
- 每次导出临时生成全部内容：内容包本身就是库，导出只是打包，不需要二次生成。

## Consequences

- 文本/章节在文件和数据库中有派生重复；用 `trove index rebuild` 从内容包重建索引。
- 删除 Item 只删派生文件和索引，不删除用户原始文件；视频只保留 source.json + 音频。
- V1 迁移再加 `version`/`deleted_at` 和 manifest/cursor，不改变当前文件布局。
- 见 [技术选型](../ideas/trove-tech-selection.md) 第 4、5.1 节；需求 FR-22/64/66/73、NFR-03/08。
