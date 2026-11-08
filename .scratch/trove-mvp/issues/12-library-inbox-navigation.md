# 12 — Library、Inbox 与导航骨架

Status: ready-for-agent  
Type: task  
Milestone: M0  
Blocked by: 05, 06, 11  
Spec: [spec.md](../spec.md)  
Requirements: FR-56, FR-57, FR-58, FR-81

## Context

用户需要一眼看到库里的 Item、哪些还在处理/失败，以及从 Library 快速进入播放/详情。默认 Library 采用原型选定的 C 队列列表：点 Item 主体进入 B Now Playing，行内播放按钮用于快速播放。Inbox 不单独占导航位，而是 Library 的“处理中/失败”过滤 + 状态徽标。

## Scope

- Library 列表：C 队列式列表；全部 Item、最近添加/最近消费排序、类型/来源/状态摘要。
- 行内播放按钮：快速播放并在当前列表就地展开；点击 Item 主体进入 B Now Playing。
- B 顶部返回 C 列表；返回后保持播放/进度。
- 导航骨架：Library + Search + Add；Continue 入口在 P1 由 19 补上。
- Inbox 过滤：Processing State 为处理中/失败；状态徽标；失败原因入口。
- 状态轮询：仅在存在活动 Run 时轮询，终态后停止。
- 响应式布局、空状态、加载/错误状态。
- Item 行显示标题、作者、类型、Tag 摘要、进度/状态。

## Acceptance Criteria

- [ ] Library 能浏览全部 Item，按最近添加/最近消费排序。
- [ ] Inbox 过滤只显示处理中/失败 Item，并显示状态徽标；普通 Library 不被过滤。
- [ ] 活动 Run 的状态自动更新，完成后停止轮询；失败显示原因入口。
- [ ] 导航在桌面/手机布局可用；空 Library 有引导到 Add 的状态。
- [ ] 点击 Item 主体进入 B Now Playing；B 返回 C 列表时播放/进度保持。
- [ ] 行内播放按钮快速播放并在 C 列表就地展开，不先进入 B。

## Testing

- Host seam：seed 多种状态 Item；排序/过滤/徽标/轮询停止；C→B→C。
- Playwright：列表 → B → 返回 C、行内快速播放、手机布局、空状态、状态更新；返回后播放器不中断。
- 不测试具体轮询间隔；断言终态后不再变化。

## Out of Scope

- Search 页面（15）、Continue（19）、Tag 页面（P3）。
- 每日 feed/streak；不做。
