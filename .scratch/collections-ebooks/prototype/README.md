# 合集与电子书 · 原型

**状态：已确认（2026-11-18）**
这是 throwaway 原型，不接后端、不持久化，不是生产 UI。原型已按用户确认进入实现。

## 怎么查看

直接用浏览器打开：

- `index.html` — 入口与确认清单
- `android.html` — Android 全部状态（390 × 844）
- `host-console.html` — Host Console 全部状态（1280 × 900）

截图在 `screenshots/`，按下方清单命名。

## 重新生成截图

需要 Playwright Chromium：

```bash
uv run playwright install chromium
uv run python scripts/prototype-capture.py \
  .scratch/collections-ebooks/prototype \
  --out .scratch/collections-ebooks/prototype/screenshots
```

脚本会截取所有带 `data-shot` 的 frame，并生成每个 HTML 的 overview。

## 已落实到原型里的共识

1. **一个链接框**：视频单集、视频合集、EPUB 直链、播客 feed 自动识别。
2. **先预览后入库**：识别卡展示类型、标题、集数/时长或文件大小；合集/电子书确认后才创建。
3. **合集**：
   - B 站多 P / 合集 / 系列，YouTube playlist 识别为合集；
   - `watch?v=&list=` 识别为单集并提示忽略列表参数；
   - 单合集默认上限 100 集 / 100 小时；
   - 全量处理，单集失败隔离；
   - 已有单集无合集归属则并入，有归属则跳过并提示；
   - 上游移除的单集本地保留，预览提示。
4. **Library**：合集只占一张卡片，子集不混入主列表；筛选/排序把合集当整体；合集算 1 条。
5. **合集详情**：头部整体状态 + 单集列表；单集播放/阅读、单独重试、下载状态；不做播放全部/自动下一集。
6. **删除合集**：两个选项——删除合集及全部单集 / 仅移除分组保留单集；两端一致。
7. **电子书**：只支持 EPUB 直链；检测只做 HEAD，预览文件名+大小；下载后更新书名/作者/封面；PDF、详情页、需登录链接不支持。
8. **Host Console**：添加页统一链接面板；Library 头部“合集 N”入口；独立 `/collections` 列表；只读详情 + 重试失败项 + 删除合集；现有单集列表/筛选/搜索/计数不变。
9. **手机离线下载**：仍按单集手动；合集不自动下载到手机。

## 截图清单

Android：

- `android-add-empty.png`
- `android-add-detecting.png`
- `android-add-single.png`
- `android-add-collection.png`
- `android-add-ebook.png`
- `android-add-feed.png`
- `android-add-error.png`
- `android-add-result.png`
- `android-library-all.png`
- `android-library-processing.png`
- `android-collection-processing.png`
- `android-collection-complete.png`
- `android-collection-partial.png`
- `android-collection-menu.png`
- `android-collection-delete.png`

Host Console：

- `host-add-empty.png`
- `host-add-collection.png`
- `host-add-ebook.png`
- `host-library.png`
- `host-collections.png`
- `host-collection-detail.png`
- `host-collection-delete.png`

## 明确不在本轮原型范围

- 合集播放全部 / 自动下一集 / Up Next
- 合集级 AI 摘要、Tag、封面编辑
- 自动追更 / 定时检查
- 合集自动下载到手机
- 合集内选集入库
- PDF、电子书站点解析、需登录的 EPUB 直链
- Host Console 合集重命名 / Tag 编辑

## 实现状态

原型已于 2026-11-18 确认并进入实现：

- Host：`Collection` 聚合、链接检测、合集展开/幂等/删除、EPUB 直链入库、API/contract。
- Host Console：统一链接面板、`/collections` 列表/只读详情/重试/删除。
- Android：Add 自动检测/预览、Library 合集卡片/筛选、合集详情/重试/删除。
- 文档：`GLOSSARY.md`、V1 spec/requirements、ADR-0010/0011、contract fixtures。
