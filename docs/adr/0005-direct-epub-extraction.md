# EPUB 直接解析，不引入 EbookLib/Audiobookshelf

MVP 的 EPUB 只要求 DRM-free、可重排 EPUB 2/3 的元数据、章节和可读文本；完整渲染（图片版式、脚注、书内搜索）留给 V1/native。为避免 AGPL 核心依赖和两套事实源，使用 Python 标准库 `zipfile` + `lxml` + `nh3` 直接解析 container/OPF/spine/nav/NCX，拒绝内容加密和固定版式，章节 HTML 白名单净化后供薄阅读器使用。

**Status**: Accepted · 2026-11-08

## Considered Options

- EbookLib：AGPL-3.0，不适合未来可能闭源的核心依赖。
- Audiobookshelf：GPL-3.0，且库/阅读/标签会与 Host Console 形成两套事实源。
- foliate-js/Readium：完整 EPUB 渲染是 V1/native 的事，MVP 不需要；保留为后续备选。

## Consequences

- 需要自己覆盖 EPUB2/3、缺失 nav、字体混淆、DRM、固定版式等边界；验收 10/10。
- MVP 不渲染图片/脚注弹窗/书内搜索；原 EPUB 保留，`book.json` 保存章节文本。
- 见 [技术选型](../ideas/trove-tech-selection.md) 第 3.4、8、11.4 节；需求 FR-03/20/38、NFR-10。
