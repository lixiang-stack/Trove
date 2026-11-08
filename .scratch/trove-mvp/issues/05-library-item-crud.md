# 05 — Library / Item CRUD 与来源元数据

Status: ready-for-agent  
Type: task  
Milestone: M0  
Blocked by: 02, 03, 04  
Spec: [spec.md](../spec.md)  
Requirements: FR-06, FR-07, FR-16, FR-17, FR-57, FR-58, NFR-03  
ADRs: [0008](../../../docs/adr/0008-content-package-as-source-of-truth.md)

## Context

入库、播放、搜索都围绕 Item。先建立 Library 的读取与编辑闭环：列表、详情、来源元数据、标题/作者编辑和删除；入库与处理由后续 issue 接入。

## Scope

- Item 列表（按最近添加/最近消费）与详情页；JSON API 与 HTML 页面共用 application service。
- 详情展示原始/规范化 URL、平台、类型、标题、作者、发布日期、抓取时间、Processing State/Consumption State 摘要。
- 编辑标题/作者；删除 Item（删除内容包派生文件、索引、数据库记录，不删除用户原始文件）。
- 空 Library、未知 Item、无权限等错误状态。
- 不实现来源解析、下载、转写、播放。

## Acceptance Criteria

- [ ] 通过测试 seed 创建 Item 后，Library 和详情可见；字段与内容包 `source.json` 一致。
- [ ] 修改标题/作者后，列表、详情和 API 同步；不改变原始来源 URL。
- [ ] 删除 Item 后，内容包派生文件、数据库行和 FTS 行消失，原始路径仍存在。
- [ ] 未认证访问被拒绝；不存在的 Item 返回稳定的 404 错误。
- [ ] HTML 页面在桌面和手机宽度下可读。

## Testing

- Host seam：seed Item → 列表/详情 → PATCH → DELETE → 断言文件/数据库/原始文件。
- 错误路径：未认证、404、空 Library。
- Playwright：列表/详情在移动视口的可见性。

## Out of Scope

- URL/文件/EPUB/播客入库；由 07–09 实现。
- Processing Run、播放、搜索；由后续 issue 实现。
