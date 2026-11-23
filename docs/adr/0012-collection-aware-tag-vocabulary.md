# Tag 保持 Item 级存储，生成时使用合集级词汇表

一个 75 集的课程合集产生了 83 个 Tag、380 条关联，其中 46 个 Tag 只被 1 个 Item 使用；筛选弹窗平铺全部 Tag 后不可用。根因是 organizer 逐集生成自由 Tag，没有共享词汇约束，且合集上下文没有进入 prompt。

**Status**: Accepted · 2026-11-23

## Decision

- Tag 仍然存储在 Item 上，不新增 `Collection.tags`；合集级 AI 摘要/Tag 仍是 V1 非目标。来自合集的 Tag 随 Item 独立同步、搜索、下载和编辑。
- 合集作为生成上下文：organizer 接收合集标题和集数；同一合集一旦有 AI Tag，后续 episode 只复用该合集的 AI 词汇表，不再新增 Tag，并补齐到最多 3 个共享 Tag。用户手动 Tag 不参与该词汇表，也不会被自动传播。
- 非合集 Item 最多 3 个 Tag；词汇表非空时最多新增 1 个广义 Tag。空词汇表允许一次建立最多 3 个 Tag。
- 传给模型的词汇表从最多 100 个降到 30 个，减少 prompt 噪音并强化复用。
- 筛选 UI 默认只显示使用次数最高的 12 个 Tag，其余通过“更多”展开；长尾 Tag 仍可被全文搜索命中。
- 存量合集用 `trove collection reprocess <collection_id> --reset-ai-tags` 清理旧 AI Tag 并重新整理；用户手动 Tag 保留。

## Considered Options

- **Collection.tags 独立实体**：语义最直接，但需要 DB migration、API contract、Android Room、同步和 UI 全链路改动；episode 移出合集后还会丢失主题分类。V1 不采用。
- **只清理历史 Tag，不改生成**：能解决当前库，但下一次入库会重新产生长尾。不采用。
- **删除 Tag 功能**：搜索已覆盖全文，但 Tag 是唯一的跨 Item 主题维度和按 Tag 下载/同步的基础；删除是破坏性契约变更。不采用。

## Consequences

- 一个合集的 episode 共享同一组核心 Tag；单集差异由标题、摘要和 transcript 搜索承担。
- 重跑合集的 organizing 会调用 LLM；`--reset-ai-tags` 会先删除 AI Tag，运行完成前该合集的 AI Tag 为空。
- organizer prompt version 升级到 `organize-2`；输出 Tag 上限从 5 降为 3。
- 筛选 UI 的 Tag 数量有上限，但搜索结果和 Item 详情仍能看到完整 Tag。
