from __future__ import annotations

import posixpath
import re
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

import nh3
from lxml import etree, html

from trove.errors import ProcessingError, ValidationError
from trove.ports import BookChapterData, BookResult, StageContext

MAX_UNCOMPRESSED_BYTES = 500 * 1024 * 1024
MAX_ENTRY_BYTES = 64 * 1024 * 1024
FONT_SUFFIXES = {".ttf", ".otf", ".woff", ".woff2", ".ttc"}
ALLOWED_TAGS = {
    "p",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "blockquote",
    "ul",
    "ol",
    "li",
    "em",
    "strong",
    "i",
    "b",
    "br",
    "div",
    "section",
    "span",
}
ALLOWED_ATTRIBUTES: dict[str, set[str]] = {}


@dataclass(slots=True)
class EpubMetadata:
    title: str
    author: str | None
    language: str | None


def validate_epub(path: Path, *, error_type: type[Exception] = ValidationError) -> EpubMetadata:
    try:
        with zipfile.ZipFile(path) as archive:
            _check_zip_sizes(archive)
            metadata, _, _, _, _, _ = _inspect(archive)
            return metadata
    except zipfile.BadZipFile as exc:
        raise _error(error_type, "epub.invalid", "不是有效的 EPUB 文件") from exc
    except KeyError as exc:
        raise _error(error_type, "epub.invalid", "EPUB 缺少必要结构") from exc
    except (OSError, etree.XMLSyntaxError) as exc:
        raise _error(error_type, "epub.parse", "EPUB 解析失败") from exc


class EpubExtractor:
    def extract(self, book_path: Path, context: StageContext) -> BookResult:
        try:
            with zipfile.ZipFile(book_path) as archive:
                _check_zip_sizes(archive)
                metadata, manifest, spine, nav_titles, opf_path, _ = _inspect(archive)
                chapters: list[BookChapterData] = []
                for idref in spine:
                    context.check_cancelled()
                    item = manifest.get(idref)
                    if item is None:
                        continue
                    href, media_type, _ = item
                    if media_type not in {"application/xhtml+xml", "text/html"}:
                        continue
                    entry_name = _resolve_href(opf_path, href)
                    try:
                        raw = archive.read(entry_name)
                    except KeyError:
                        continue
                    chapter = _extract_chapter(
                        raw,
                        chapter_index=len(chapters),
                        title=nav_titles.get(entry_name),
                    )
                    if chapter is not None:
                        chapters.append(chapter)
                return BookResult(
                    title=metadata.title,
                    author=metadata.author,
                    language=metadata.language,
                    chapters=chapters,
                )
        except zipfile.BadZipFile as exc:
            raise ProcessingError("epub.invalid", "不是有效的 EPUB 文件") from exc
        except ValidationError as exc:
            code = (exc.details or {}).get("code", "epub.parse")
            raise ProcessingError(str(code), exc.message) from exc
        except KeyError as exc:
            raise ProcessingError("epub.invalid", "EPUB 缺少必要结构") from exc
        except (OSError, etree.XMLSyntaxError) as exc:
            raise ProcessingError("epub.parse", "EPUB 解析失败") from exc


def _check_zip_sizes(archive: zipfile.ZipFile) -> None:
    total = 0
    for info in archive.infolist():
        if info.file_size > MAX_ENTRY_BYTES:
            raise ValidationError("EPUB 内单个文件过大", details={"code": "epub.invalid"})
        total += info.file_size
        if total > MAX_UNCOMPRESSED_BYTES:
            raise ValidationError("EPUB 解压后体积过大", details={"code": "epub.invalid"})


def _inspect(archive: zipfile.ZipFile):
    names = set(archive.namelist())
    if "META-INF/container.xml" not in names:
        raise KeyError("META-INF/container.xml")
    if "mimetype" in names:
        mimetype = archive.read("mimetype").decode("ascii", "ignore").strip()
        if mimetype != "application/epub+zip":
            raise ValidationError("EPUB mimetype 无效", details={"code": "epub.invalid"})
    container = etree.fromstring(archive.read("META-INF/container.xml"))
    rootfiles = container.xpath(".//*[local-name()='rootfile']")
    if not rootfiles:
        raise KeyError("rootfile")
    rootfile = rootfiles[0]
    opf_path = rootfile.get("full-path")
    if not opf_path or opf_path not in names:
        raise KeyError("opf")
    opf = etree.fromstring(archive.read(opf_path))
    _check_drm(archive, names)
    metadata = _metadata(opf)
    _check_fixed_layout(opf)
    manifest = _manifest(opf)
    spine, toc_id = _spine(opf)
    nav_titles = _nav_titles(archive, manifest, toc_id, opf_path)
    return metadata, manifest, spine, nav_titles, opf_path, toc_id


def _check_drm(archive: zipfile.ZipFile, names: set[str]) -> None:
    if "META-INF/encryption.xml" not in names:
        return
    document = etree.fromstring(archive.read("META-INF/encryption.xml"))
    references = document.xpath(".//*[local-name()='CipherReference']")
    for reference in references:
        uri = reference.get("URI") or ""
        if Path(uri).suffix.lower() not in FONT_SUFFIXES:
            raise ValidationError(
                "EPUB 受 DRM 保护，无法导入", details={"code": "epub.drm"}
            )
    if not references:
        raise ValidationError("EPUB 受 DRM 保护，无法导入", details={"code": "epub.drm"})


def _metadata(opf) -> EpubMetadata:
    metadata = _first(opf, ".//*[local-name()='metadata']")
    title = _first_text(metadata, "title") or "未命名书"
    author = _first_text(metadata, "creator")
    language = _first_text(metadata, "language")
    return EpubMetadata(title=title, author=author, language=language)


def _first(parent, expression: str):
    matches = parent.xpath(expression)
    return matches[0] if matches else None


def _first_text(parent, name: str) -> str | None:
    if parent is None:
        return None
    element = _first(parent, f".//*[local-name()='{name}']")
    if element is None or not element.text:
        return None
    return _clean_text(element.text)


def _check_fixed_layout(opf) -> None:
    metadata = _first(opf, ".//*[local-name()='metadata']")
    if metadata is None:
        return
    for meta in metadata.xpath(".//*[local-name()='meta']"):
        name = (meta.get("name") or "").lower()
        prop = (meta.get("property") or "").lower()
        content = (meta.get("content") or meta.text or "").strip().lower()
        if (name == "fixed-layout" and content == "true") or (
            prop == "rendition:layout" and content == "pre-paginated"
        ):
            raise ValidationError(
                "仅支持可重排 EPUB，固定版式书无法导入",
                details={"code": "epub.fixed_layout"},
            )


def _manifest(opf) -> dict[str, tuple[str, str, str]]:
    manifest: dict[str, tuple[str, str, str]] = {}
    for element in opf.xpath(".//*[local-name()='manifest']/*[local-name()='item']"):
        item_id = element.get("id")
        href = element.get("href")
        if not item_id or not href:
            continue
        manifest[item_id] = (
            href,
            element.get("media-type") or "",
            element.get("properties") or "",
        )
    return manifest


def _spine(opf) -> tuple[list[str], str | None]:
    spine_element = _first(opf, ".//*[local-name()='spine']")
    if spine_element is None:
        raise KeyError("spine")
    return (
        [
            element.get("idref")
            for element in spine_element.xpath("*[local-name()='itemref']")
            if element.get("idref")
        ],
        spine_element.get("toc"),
    )


def _nav_titles(
    archive: zipfile.ZipFile,
    manifest: dict[str, tuple[str, str, str]],
    toc_id: str | None,
    opf_path: str,
) -> dict[str, str]:
    titles = _epub3_nav_titles(archive, manifest, opf_path)
    if toc_id and toc_id in manifest:
        for target, label in _ncx_titles(archive, manifest[toc_id][0], opf_path).items():
            titles.setdefault(target, label)
    return titles


def _epub3_nav_titles(
    archive: zipfile.ZipFile,
    manifest: dict[str, tuple[str, str, str]],
    opf_path: str,
) -> dict[str, str]:
    titles: dict[str, str] = {}
    for _item_id, (href, media_type, properties) in manifest.items():
        if "nav" not in properties.split() or media_type not in {
            "application/xhtml+xml",
            "text/html",
        }:
            continue
        entry_name = _resolve_href(opf_path, href)
        try:
            document = html.fromstring(archive.read(entry_name))
        except (KeyError, etree.ParserError):
            return titles
        selected = _select_toc_nav(document)
        if selected is None:
            return titles
        for anchor in selected.xpath(".//a[@href]"):
            target = _resolve_href(entry_name, anchor.get("href", ""))
            label = _clean_text(anchor.text_content())
            if label:
                titles.setdefault(target, label)
        return titles
    return titles


def _select_toc_nav(document):
    navs = document.xpath("//*[local-name()='nav']")
    for nav in navs:
        if "toc" in " ".join(nav.attrib.values()):
            return nav
    return navs[0] if navs else None


def _ncx_titles(
    archive: zipfile.ZipFile, href: str, opf_path: str
) -> dict[str, str]:
    entry_name = _resolve_href(opf_path, href)
    try:
        document = etree.fromstring(archive.read(entry_name))
    except (KeyError, etree.XMLSyntaxError):
        return {}
    titles: dict[str, str] = {}
    for nav_point in document.xpath(".//*[local-name()='navPoint']"):
        label_element = _first(
            nav_point, ".//*[local-name()='navLabel']/*[local-name()='text']"
        )
        content = _first(nav_point, ".//*[local-name()='content']")
        if label_element is None or content is None:
            continue
        label = _clean_text(label_element.text or "")
        target = _resolve_href(entry_name, content.get("src") or "")
        if label:
            titles.setdefault(target, label)
    return titles

def _extract_chapter(
    raw: bytes, *, chapter_index: int, title: str | None
) -> BookChapterData | None:
    try:
        document = html.fromstring(raw)
    except (etree.ParserError, ValueError):
        return None
    for element in document.xpath(
        "//script | //style | //nav | //*[local-name()='script'] | //*[local-name()='style']"
    ):
        element.getparent().remove(element)
    body = document.find("body")
    if body is None:
        body = document
    paragraph_nodes = body.xpath(
        ".//p | .//h1 | .//h2 | .//h3 | .//h4 | .//h5 | .//h6 | .//blockquote | .//li"
    )
    paragraphs = [_clean_text(element.text_content()) for element in paragraph_nodes]
    paragraphs = [paragraph for paragraph in paragraphs if paragraph]
    if not paragraphs:
        text = _clean_text(body.text_content())
        if not text:
            return None
        paragraphs = [line for line in text.splitlines() if line.strip()]
    text = "\n".join(paragraphs)
    if not text:
        return None
    heading = title
    if not heading:
        for tag in ("h1", "h2", "h3"):
            elements = body.xpath(f".//{tag}")
            if elements:
                heading = _clean_text(elements[0].text_content())
                break
    heading = heading or f"第 {chapter_index + 1} 章"
    cleaned = nh3.clean(
        html.tostring(body, encoding="unicode", method="html"),
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
    )
    return BookChapterData(
        chapter_index=chapter_index,
        title=heading,
        html=cleaned,
        text=text,
        paragraphs=paragraphs,
    )


def _resolve_href(base_path: str, href: str) -> str:
    href = unquote(href.split("#", 1)[0])
    if not href:
        return base_path
    base_dir = posixpath.dirname(base_path)
    return posixpath.normpath(posixpath.join(base_dir, href))


def _clean_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "")
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _error(error_type: type[Exception], code: str, message: str):
    if error_type is ValidationError:
        return ValidationError(message, details={"code": code})
    return ProcessingError(code, message)
