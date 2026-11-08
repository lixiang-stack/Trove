# 15 — 搜索页面、过滤与结果定位

Status: ready-for-agent  
Type: task  
Milestone: M1  
Blocked by: 12, 14  
Spec: [spec.md](../spec.md)  
Requirements: FR-47, FR-48, FR-49, FR-50, FR-51, FR-52, FR-81

## Context

搜索 API 有了之后，用户需要一个统一入口：输入关键词，看到按 Item 聚合的结果、匹配段落、来源/类型/作者/日期，并能组合过滤、点击定位到相关段落。

## Scope

- Search 页面：统一搜索框、结果列表/空状态、加载/错误状态。
- 结果按 Item 聚合；显示最佳匹配段落（最多 3 条）、来源/类型/作者/日期、Tag 摘要。
- 过滤：类型、Consumption State、Tag、来源；可组合；Library 和 Search 共用过滤语义。
- 点击结果打开 Item：默认从 C 列表进入 B Now Playing，并滚动到 transcript 分段或书章节/段落锚点（P1）；不做音频跳转。
- 在 B 内搜索时，结果关闭抽屉并留在 B；返回 C 后保持播放/进度。
- 手机布局；HTMX GET 表单 + 服务端渲染；不使用前端路由状态机。
- 搜索关键词高亮（服务端 snippet 或少量 JS）。

## Acceptance Criteria

- [ ] 输入两字中文/英文/标题/摘要/Tag/书文本均能看到相关 Item 和证据。
- [ ] 过滤可组合，结果与 Library 的过滤语义一致；清空过滤可恢复。
- [ ] 点击结果从 C 进入 B 并定位到匹配段落；位置准确（P1）。
- [ ] 在 B 搜索关闭抽屉后留在 B；从 B 返回 C 后播放/进度保持。
- [ ] 无结果/空查询/非法长查询有清晰状态。
- [ ] 手机宽度可操作；搜索提交不破坏持久播放器。
- [ ] 搜索耗时在验收数据上 <1 秒。

## Testing

- Host seam：查询/过滤/分组/定位 URL/锚点；无结果/长查询。
- Playwright：搜索、过滤、C→B 点击定位、B 内搜索、手机布局、播放器不中断。
- 与 14 的 API 测试共用 seed 数据；不重复测试 FTS 内部。

## Out of Scope

- 语义搜索、相关推荐、跨媒介模式；不做。
- 独立 Tag 页面；P3。
