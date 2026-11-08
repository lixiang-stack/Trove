# Web 客户端采用服务端渲染 + HTMX，不引入 React SPA

Host Console 是长期管理界面，Consumer Web Shell 是 Q10 gated、预期被 Android 替代的验证壳；MVP 的交互是列表、表单、搜索和单页音频播放，不需要 SPA 状态机。因此采用 Jinja2 + HTMX 2 + 原生 ES modules + Pico CSS，播放器放在持久布局区域，HTMX 只替换主内容；不引入 React/Node 构建链。

**Status**: Accepted · 2026-11-08

## Considered Options

- React + Vite SPA：音频连续性和复杂交互更可控，但多一个 Node 工具链；若 Q10 发现 HTMX 导航中断音频，再替换表现层，API/数据模型不变。
- Next.js：无 SSR/SEO 需求，增加服务端复杂度。
- Alpine.js：CSP 需要放宽（eval），不采用。

## Consequences

- 需要小心处理 HTMX history、滚动位置和播放器持久化；Q10 第一周 spike 验证。
- 前端 JS 保持少量原生模块，由 Playwright 覆盖，不引入 TypeScript/构建链。
- Consumer Shell 的 listen/read 路由独立，Q10 失败可收缩/移除而不影响 Host Console。
- 见 [技术选型](../ideas/trove-tech-selection.md) 第 3.2 节；Q10 定义见 [trove-requirements.md](../ideas/trove-requirements.md#q10)。
