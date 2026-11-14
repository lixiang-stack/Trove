# 14 — Android EPUB Reader（Readium）

Status: ready-for-agent
Type: task
Milestone: M2
Blocked by: 10, 12
Spec: [spec.md](../spec.md)
Tech: [tech-selection.md](../tech-selection.md)
Requirements: FR-71, FR-72
ADRs: [0005](../../../docs/adr/0005-direct-epub-extraction.md), [0009](../../../docs/adr/0009-native-android-client-app-managed-sync.md)

## Context

V1 阅读要覆盖完整可重排 EPUB（图片、脚注/内部链接、书内搜索），并让阅读位置在 Android/Web 之间可继续。使用 Readium classic EPUB navigator；`book.epub` 渲染，`book.json` 用于文本搜索/legacy locator。

## Scope

- Readium 3.4.0 `readium-shared`/`streamer`/`navigator`；不引入 LCP。
- `EpubNavigatorFragment` 通过 `FragmentContainerView`/`AndroidView` 嵌入 Compose；Reader 可隔离为独立 Fragment/Activity 壳。
- 打开已下载 `book.epub`；`book.json` 章节/段落用于搜索和 locator 映射。
- 阅读位置 `book_locator` schema 2：legacy chapter/paragraph/scroll + EPUB href/progression/totalProgression。
- 章节导航、字号/行高/浅色/深色/护眼主题；书内搜索高亮。
- EPUB 安全：WebViewClient 阻断非本地请求/外部导航；CSP 禁止内容脚本/远程资源；Readium 本地脚本保留；恶意 EPUB fixture 测试。
- 离线阅读；DRM/固定版式/解析失败显示明确原因（Host 已拒绝的书不应出现）。

## Acceptance Criteria

- [ ] EPUB2/EPUB3 golden fixture 可打开、翻章、显示正文/图片/脚注链接。
- [ ] 阅读位置保存/恢复；与 Web legacy locator 可互相回退。
- [ ] 书内搜索命中并定位/高亮；离线可用。
- [ ] 恶意 EPUB 不执行远程脚本/请求；不打开外部导航。
- [ ] 阅读页与播放器/导航互不干扰；返回不丢位置。
- [ ] 不实现标注/PDF/TTS/分页模式切换。

## Testing

- Unit：locator schema 2 解析/映射、spine/chapter 映射、legacy fallback。
- Instrumented：Readium 打开 golden EPUB、翻章、搜索；恶意 EPUB 冒烟。
- 真实 Xiaomi 13：离线阅读、图片/脚注、位置恢复。

## Out of Scope

- 标注/笔记、PDF、TTS、书内购买/DRM。
- 完整 EPUB 渲染的 Web 版本；Web 仍用薄阅读器。
