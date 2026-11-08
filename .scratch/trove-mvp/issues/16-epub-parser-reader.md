# 16 — EPUB 解析与薄阅读器

Status: ready-for-agent  
Type: task  
Milestone: M2  
Blocked by: 05, 08  
Spec: [spec.md](../spec.md)  
Requirements: FR-03, FR-20, FR-22, FR-38, FR-39, NFR-03, NFR-10  
ADRs: [0005](../../../docs/adr/0005-direct-epub-extraction.md)

## Context

电子书在 MVP 只要求提取章节和文本、用薄阅读器翻章阅读，不要求完整排版渲染。需要直接解析 EPUB2/3，拒绝 DRM/固定版式，并把章节文本接入阅读、搜索和导出。

## Scope

- 直接解析 `container.xml` → OPF → spine；EPUB3 nav、EPUB2 NCX，缺失时 spine + 标题兜底。
- 元数据、章节顺序、正文段落、封面提取；`book.json` 与 `book.epub` 入库。
- DRM 检测：内容加密（ADEPT/LCP）拒绝；仅字体混淆放行；固定版式拒绝。
- `nh3` 白名单净化章节 HTML；MVP 不渲染图片/脚注弹窗/书内搜索。
- 薄阅读器：章节导航、正文滚动、阅读进度（章节/位置）；手机可读。
- 章节/段落写入数据库供 14 搜索；阅读进度写入 Item。

## Acceptance Criteria

- [ ] EPUB2/EPUB3 golden fixture 均能提取正确章节顺序、标题、正文。
- [ ] DRM、固定版式、损坏 zip、缺失 spine 给出明确错误，不产生半成品。
- [ ] 章节 HTML 只含白名单标签，脚本/远程资源被移除；CSP 生效。
- [ ] 阅读器可翻章/读正文；刷新后回到上次章节/位置（P1）。
- [ ] 章节/段落可被搜索索引使用；搜索结果可定位到章节/段落。
- [ ] 手动验收 10 本真实 EPUB 通过 10/10。

## Testing

- Golden EPUB2/3：章节/元数据/净化/封面。
- Host seam：入库 → 提取阶段 → 阅读页 → 进度保存/恢复。
- Playwright：翻章、滚动、手机布局、进度恢复。
- 恶意 HTML/DRM/fixed-layout 拒绝测试。
- 真实 10 本书手动验收，记录失败类型。

## Out of Scope

- 完整 EPUB 渲染（图片版式、脚注弹窗、书内搜索）；V1/native。
- PDF、TTS；不做。
