# 14 — Android EPUB Reader（Readium）

Status: resolved
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
- [x] 阅读位置保存/恢复；与 Web legacy locator 可互相回退。
- [x] 书内搜索命中并定位/高亮；离线可用。
- [x] 恶意 EPUB 不执行远程脚本/请求；不打开外部导航。
- [x] 阅读页与播放器/导航互不干扰；返回不丢位置。
- [x] 不实现标注/PDF/TTS/分页模式切换。

## Testing

- Unit：locator schema 2 解析/映射、spine/chapter 映射、legacy fallback。
- Instrumented：Readium 打开 golden EPUB、翻章、搜索；恶意 EPUB 冒烟。
- 真实 Android：离线阅读、图片/脚注、位置恢复。

## Out of Scope

- 标注/笔记、PDF、TTS、书内购买/DRM。
- 完整 EPUB 渲染的 Web 版本；Web 仍用薄阅读器。

## Implementation

- `:reader` now hosts `ReaderActivity` around Readium 3.4 classic `EpubNavigatorFragment`; Library/Player/Search open downloaded `book.epub` files, with chapter TOC, in-book search + highlight, font/line-height/light-sepia-dark settings, and a finished toggle.
- `BookRepository` parses `book.json` into Room chapter/paragraph tables; `BookLocator` schema 2 keeps legacy chapter/paragraph/scroll plus `epub_href`/`epub_progression`/`epub_total_progression`. Host accepts/validates schema 2 and still serializes legacy-only writes for the Web Shell.
- Reader progress is saved locally and queued as a `book_progress` mutation; offline reads and restores from the last EPUB locator.
- Security: external navigation is disabled, WebViews get `blockNetworkLoads`, mixed-content/window/popup settings are locked down. Automated coverage: `ReaderLocatorMappingTest`, `BookLocatorTest`, Host `test_reading` schema-2 test.
- Pending device acceptance: Readium golden EPUB flip/search with images/footnotes, malicious EPUB smoke, Android offline reader/locator restore. No instrumented reader test was added in this pass.

### Android real-device acceptance (2026-11-16 / Android 16, API 36)

- Opened the real Host EPUB `老子-道德经` and the golden `aesop.epub`; both rendered reflowable text, chapter TOC, and page/chapter navigation (Aesop: 1/2 → 2/2; Real book: 1/1 because its EPUB has a single XHTML chapter).
- In-book search for `Tortoise` returned matches, jumped to the chapter/paragraph and rendered the Readium highlight; font size and the sepia theme applied immediately and survived page changes.
- Closed and reopened the reader: restored chapter 2 at 50%; with Host unreachable, `adb reverse` removed, and airplane mode on, the downloaded EPUB still opened and restored the same position.
- Security smoke: added a modified `aesop.epub` with a remote image (`http://127.0.0.1:8765/leak-image`), a remote `fetch` script, and an external link. The image rendered as a broken placeholder, the Host log recorded no `leak-image`/`leak-script` request, and tapping the external link left the reader on `ReaderActivity` instead of opening a browser.
- Not covered by the available fixtures/device run: local images, footnote links, and an instrumented Readium golden-EPUB test (no image/footnote fixtures in this set).
- **2026-11-17 follow-up:** with `illustrated.epub` downloaded to the device, chapter 1 rendered the local `dot.png` image placeholder and footnote text; the `Jump to footnote` anchor was visible/clickable. Chapter navigation moved to 2/2 and offline reopen restored 50% · 第 2/2 章. The fixture image is a 1×1 dot, so this verifies local-image loading rather than image layout. An instrumented Readium golden-EPUB test remains a follow-up.
