# 18 — Item Tag 编辑与 Tag 过滤

Status: ready-for-agent  
Type: task  
Milestone: M2  
Blocked by: 05, 15, 17  
Spec: [spec.md](../spec.md)  
Requirements: FR-27, FR-28, FR-50  
ADRs: [0003](../../../docs/adr/0003-sqlite-fts5-cjk-search.md)

## Context

自动 Tag 需要可修正。MVP 只做 Item 上的增删 Tag 和按 Tag 过滤，不做全局重命名/合并/孤儿清理。

## Scope

- Item 详情/列表上的 Tag 编辑：添加、删除；区分 AI 生成与用户编辑。
- Tag 归一化复用 17 的规则；重复 Tag 不重复关联。
- Tag 变更立即更新搜索索引和 Library/Search 过滤结果。
- Tag 列表/计数 API；不做独立 Tag 页面。
- 用户编辑不触发 LLM 重跑；仅更新当前 Item。

## Acceptance Criteria

- [ ] 用户可添加/删除 Item Tag，重复/空/超长输入被规范化或拒绝。
- [ ] Tag 修改后 Library/Search 过滤和关键词搜索立即反映，无需重建索引。
- [ ] AI Tag 与用户 Tag 来源可区分；用户删除 AI Tag 后不会被自动加回（除非重跑整理）。
- [ ] Tag 列表/计数正确；组合过滤与 15 一致。
- [ ] 未认证不可编辑；错误 Item/Tag 返回稳定错误。

## Testing

- Host seam：编辑/删除/重复/规范化/索引同步/过滤。
- Playwright：Item 上编辑 Tag，Library/Search 立即更新。
- 不测试全局 Tag 合并（未实现）。

## Out of Scope

- 全局 Tag 重命名/合并/孤儿清理（P2）。
- 独立 Tag 页面（P3）。
