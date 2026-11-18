# EPUB 直链作为一等电子书来源

电子书目前只能从 Host Console 上传本地文件；用户手里经常只有可直接下载的 EPUB URL。新增 `SourceType.EPUB_URL`：检测阶段只做 HEAD/类型/大小判断，确认后由 Host 在 `downloading` 阶段用 SafeHttpClient 下载到 Content Package，再走现有 `extracting_text → organizing → indexing` 管线。这样阅读器、搜索、导出和同步都不需要第二套电子书模型。

只支持可直接下载、DRM-free、可重排的 EPUB 2/3；PDF、电子书详情页、需要登录/Cookie 的链接明确拒绝。按最终 canonical URL 去重；同 URL 再次添加返回已有 Item。检测不下载整本，避免用户取消时浪费带宽。

**Status**: Accepted · 2026-11-17

## Considered Options

- 检测阶段直接下载并解析：预览能显示真实书名/作者/封面，但检测慢、取消浪费带宽；确认后反正要下载一次。
- 新增独立的 Ebook/Book 表或下载任务：与现有 EPUB Item/Content Package 重复，阅读器和同步都要分叉。
- 支持 PDF/站点解析：需要新的文本抽取、阅读器和反爬/版权边界，超出本次范围。

## Consequences

- `SourceType.EPUB_URL` / `Platform.WEB`；下载阶段失败显示 `download.*`；EPUB 校验失败显示 `epub.*`。
- `source_key` = 最终 canonical URL；`source_url_canonical` 保存最终 URL；标题先用文件名，解析后用书元数据覆盖。
- 下载文件进入 `book.epub` artifact；现有 EPUB 解析、阅读、搜索、导出、Android 同步全部复用。
- 认证/Cookie/DRM 绕过不做；需要登录的直链返回明确错误。
- 大小限制沿用 `max_epub_bytes`（默认 100 MB）；SSRF/重定向/私网校验由 SafeHttpClient 统一执行。

## Related

- [Feature spec](../../.scratch/collections-ebooks/spec.md)
- [ADR-0005: Direct EPUB extraction](0005-direct-epub-extraction.md)
- [ADR-0008: Content Package as source of truth](0008-content-package-as-source-of-truth.md)
