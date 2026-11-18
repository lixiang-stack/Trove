# Collections / EPUB 直链 — 真机验收记录

- Date: 2026-11-18
- Device: Xiaomi 13 (`2211133C`), Android 16 / API 36
- Build: `prodDebug` (`dev.trove.app`), debug localhost + `adb reverse`
- Host: throwaway acceptance Host，`TROVE_HOME=/var/folders/.../trove-acceptance.wqSz9i`，端口 8766
  （8765 已被真实 Host 占用；手机 `tcp:8765` 反向映射到 Mac `tcp:8766`）
- Spec: [spec.md](spec.md)
- Related: `.scratch/trove-v1/issues/23-v1-release-device-acceptance.md`
- Decision: **PASS with exceptions** — 功能主链路可用；发现并修复会导致升级后启动崩溃的 room 迁移缺陷，以及两项预览偏差；剩余例外为外部 LLM 配额与上游元数据质量。

## 自动化门禁

| Gate | Command | Result |
| ---- | ------- | ------ |
| Device baseline + bundled SQLite/FTS5 | `scripts/android/device-check.sh` | PASS（含新增迁移回归测试） |
| Android build/JVM/Compose/lint | `scripts/android/check.sh` | PASS |
| Host full tests + browser + docs | `./scripts/check.sh --full` | PASS |

## 阻断缺陷（已修复）

**升级后冷启动崩溃**：`TroveDatabase` 的 `MIGRATION_1_2/2_3/3_4` 只实现了
`migrate(SupportSQLiteDatabase)`；生产使用 `BundledSQLiteDriver`，Room 要求实现
`migrate(SQLiteConnection)`。已有 v3 数据库的安装升级到本分支后，启动即抛
`kotlin.NotImplementedError: Migration functionality with a provided SQLiteDriver
requires overriding the migrate(SQLiteConnection) function.`（logcat 证据：13:37–13:41）。

- 修复：三条迁移同时实现 framework 与 driver 两个入口，共用同一组 SQL。
- 回归测试：新增 `android/core/src/androidTest/.../TroveDatabaseMigrationDeviceTest.kt`，
  用导出 schema 构造真实 v3 数据库，再通过生产 `TroveDatabase.create` 打开；
  修复前该测试在真机复现同一异常，修复后通过。
- 影响：所有从 v3 升级的现有安装；新安装不受影响。

## 验收结果

### Add / detection

| 项目 | 结果 | 证据 |
| ---- | ---- | ---- |
| Bilibili 单集（`?p=2`） | PASS — 预览单集、创建、处理完成 | `/tmp/trove-bili-single-preview.png`, `/tmp/trove-bili-single-created.png` |
| YouTube 单集 | PASS — 预览、创建、完成、打开 Now Playing | `/tmp/trove-youtube-single-preview.png`, `/tmp/trove-youtube-created2.png` |
| YouTube `watch?v=&list=` | PASS — 识别为单集；“播放列表已忽略”提示只显示一次 | `/tmp/trove-watchlist-fixed.png` |
| Bilibili 裸多 P | PASS — 10 集、“时长未知”；“1 集已在库中，将并入”；创建结果 10 集/新增 9/并入 1 | `/tmp/trove-multip-fixed.png`, `/tmp/trove-bili-multip-preview.png`, `/tmp/trove-bili-collection-result2.png` |
| Bilibili 合集页 | PASS — `合集·百万支票`，5 集 | `/tmp/trove-bili-collection-preview.png` |
| 重复 URL | PASS — 打开已有 Item，Host `runs` 计数仍为 1 | `/tmp/trove-youtube-duplicate.png` |
| 播客 feed | PASS — 预览 2 集；添加其中一集并完成播放 | `/tmp/trove-podcast-preview.png`, `/tmp/trove-podcast-created.png`, `/tmp/trove-podcast-player.png` |
| EPUB 直链 | PARTIAL — 预览 `moby-dick`/1.6 MB、下载/解析成功、书名作者更新为 Moby-Dick / Herman Melville；LLM 阶段因外部配额失败（见偏差 4） | `/tmp/trove-epub-preview.png`, `/tmp/trove-epub-created.png`, `/tmp/trove-epub-item.png` |
| PDF / 直播等不支持链接 | PASS — 明确错误，未创建 Item（DB 计数 0） | `/tmp/trove-unsupported-pdf2.png`, `/tmp/trove-unsupported-live.png` |

### Collection / Library

| 项目 | 结果 | 证据 |
| ---- | ---- | ---- |
| 预览创建合集结果卡 | PASS — `10 集 · 新增 9 · 并入 1` | `/tmp/trove-bili-collection-result2.png` |
| Library 单卡片/头部计数 | PASS — `8 条内容 · 1 个合集`，子集不进入主列表 | `/tmp/trove-library-collection.png` |
| 卡片集数/状态/失败/消费进度 | PASS — `11 集`, `1 集失败`, `10/11 完成`, `已听 0/11`（含注入的失败单集） | `/tmp/trove-library-failed2.png`, `/tmp/trove-library-top2.png` |
| 筛选包含合集 | PASS — `处理中`、`进行中` 均显示合集；无子集完成时 `已完成` 不显示合集（符合语义） | `/tmp/trove-filter-processing.png`, `/tmp/trove-filter-in-progress.png` |
| 排序 | 未单独切换验证（列表顺序正常；Host/Android 测试覆盖排序） | — |
| 详情顺序与状态/播放 | PASS — 按上游顺序；完成项可播放，排队/处理中可见 | `/tmp/trove-collection-detail.png` |
| 单集失败重试 | PASS — 单集 `重试` 触发 `POST /api/items/{id}/retry` | `/tmp/trove-collection-failed-bottom2.png` |
| 重试失败项 | PASS — 触发 `POST /api/collections/{id}/retry-failed` | `/tmp/trove-collection-retry-all.png` |
| 重复添加合集 | PASS — `10 集 · 新增 0 · 并入 10`；上游移除/其他合集冲突未在真机构造 | `/tmp/trove-readd-result.png` |
| 删除：仅移除分组 | PASS — 合集消失，17 个单集保留，进度/文件不变 | `/tmp/trove-after-ungroup.png` |
| 删除：删除全部单集 | PASS — 合集与 10 集删除；剩余 7 个 Item | `/tmp/trove-delete-items-dialog.png`, `/tmp/trove-after-delete-items.png` |
| 删除对话框计数/取消 | PASS — 注入失败项后显示 11 集；取消无删除；重加后显示 10 集 | `/tmp/trove-collection-delete-dialog.png`, `/tmp/trove-delete-items-dialog.png` |

说明：为验证失败 UI，把 seed 的 `失败的 Item` 通过临时 Host DB 挂到测试合集（`collection_index=11`）并 bump `content_seq`；清理时已随合集删除。上游移除/冲突场景由 Host 测试覆盖。

### EPUB 阅读

| 项目 | 结果 | 证据 |
| ---- | ---- | ---- |
| 阅读器/章节 | PASS — 142 章，`第 1/142 章` → `第 6/142 章` | `/tmp/trove-epub-reader.png`, `/tmp/trove-epub-toc.png`, `/tmp/trove-epub-chapter2.png` |
| 图片/脚注 | 未单独验证（Moby-Dick 本轮无可复现脚注；既有 Aesop 验收已覆盖图片/脚注） | — |
| 下载 + 飞行模式 + 重开位置 | PASS — 飞行模式 force-stop 后重开仍为 `2% · 第 6/142 章` | `/tmp/trove-offline-library.png`, `/tmp/trove-offline-reader.png` |
| 书内搜索 | PASS — `whale` 返回章节结果 | `/tmp/trove-epub-search-results.png` |

### Host Console

| 项目 | 结果 | 证据 |
| ---- | ---- | ---- |
| `/add` 统一链接面板 | PASS — 单集/合集/EPUB/feed 四类预览 | curl 输出（`/add/link/preview`） |
| `/collections` 列表/详情 | PASS — 卡片、5 集详情、排队/处理中/失败状态 | `/tmp/trove-console-detail.html`（HTML） |
| 详情重试失败项 | PASS — `POST /collections/{id}/retry-failed` 返回 303，失败 run 重置为 queued | server.log |
| 删除（delete_items） | PASS — 303；App 同步后合集与子集消失（9 条内容） | `/tmp/trove-after-console-delete.png` |
| App 同步 Console 结果 | PASS — Console 创建的合集出现在 App；删除后同步移除 | `/tmp/trove-app-console-collection3.png` |

首次失败：在手工注入“失败 run”时误插了第二条 `runs` 记录，触发 `UNIQUE constraint failed: runs.item_id` 的 500；该约束是产品设计（每个 Item 单 run 复用），改为标记原 run 后重试即 303，非产品缺陷。

### Regression

| 项目 | 结果 |
| ---- | ---- |
| 单集视频 / 播客 / 本地音频上传 | PASS — YouTube、公开 feed、`/add/upload`（`short.m4a`） |
| Library / Player / transcript / EPUB / downloads / search / Continue | PASS — 播放 MediaSession `PLAYING`；transcript 6 段 + 时间戳；EPUB 下载/离线；本地搜索命中 Moby-Dick 书文本；Continue 展示当前进度 |
| Add 页 DeepSeek 提示 | PASS — 提示可见 |
| 日志无新增密钥 | PASS — app/Host 日志无 token；logcat 仅 `adbd` 回显了自动化输入的密码（非 App 日志） |

## 偏差与后续

1. **已修复**：v3→v4 Room 迁移在 `BundledSQLiteDriver` 下启动崩溃；见上。
2. **已修复**：`watch?v=&list=` 的“播放列表参数已忽略”提示曾渲染两次。现在只在 warning 缺失时渲染 Boolean 提示；测试 `ignoredPlaylistWarningIsShownOnce`，真机 `/tmp/trove-watchlist-fixed.png`（仅 1 处）。
3. **已修复**：合集预览在 `total_duration_sec=null` 时现在显示“时长未知”；测试 `collectionPreviewShowsUnknownDurationWhenUpstreamOmitsIt`，真机 `/tmp/trove-multip-fixed.png`。
4. **外部限制**：EPUB/播客的 LLM 摘要阶段失败 `llm.limit_exceeded`（“Organization needs 63 calls; limit is 16”）。这是 Host 的 DeepSeek 账户配额，不是代码缺陷；下载/解析/阅读/搜索不受影响。恢复配额后需补一次摘要/Tag 证据。
5. **数据质量**：Bilibili 多 P 的 flat 预览标题为 `Episode N`、时长为 `—`；处理完成后真实标题回填。属上游/flat 元数据限制，预览仍按顺序展示。
6. **未在真机构造**：上游移除集、跨合集冲突、排序切换；由 Host/Android 测试覆盖。

## 复现命令

```bash
cd /Users/haoli/github/Trove/.worktree/collections-ebooks
scripts/android/acceptance-host.sh --port 8766
scripts/android/adb.sh reverse tcp:8765 tcp:8766   # app 默认 Host URL
scripts/android/device-check.sh
scripts/android/ui-dump.py --screenshot /tmp/trove.png
```

## 结论

- 功能真机验收：主链路 PASS；阻断的迁移崩溃与两项预览偏差已修复，并有真机/单元回归测试。
- 唯一未闭环项：DeepSeek 配额导致的 EPUB/播客摘要/Tag 失败；恢复配额后补一次即可。
- 已按用户确认提交并 push 到 PR 分支，不合并；等待 review。
