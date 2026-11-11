from __future__ import annotations

import base64
import json
import zipfile
from pathlib import Path

import pytest

from .fakes import FIXTURES


def _add_epub(host, path: Path) -> str:
    host.login()
    response = host.client.post("/api/items", json={"kind": "path", "path": str(path)})
    assert response.status_code == 201, response.text
    item_id = response.json()["item"]["id"]
    host.wait_for_item(item_id)
    return item_id


def _rewrite_epub(
    source: Path,
    destination: Path,
    *,
    chapter: bytes | None = None,
    opf_replace: tuple[str, str] | None = None,
    opf_transform=None,
    extra: dict[str, bytes] | None = None,
) -> None:
    with zipfile.ZipFile(source) as reader, zipfile.ZipFile(destination, "w") as writer:
        for info in reader.infolist():
            data = reader.read(info.filename)
            if info.filename == "OEBPS/chapter1.xhtml" and chapter is not None:
                data = chapter
            if info.filename == "OEBPS/content.opf":
                text = data.decode("utf-8")
                if opf_replace:
                    text = text.replace(opf_replace[0], opf_replace[1])
                if opf_transform is not None:
                    text = opf_transform(text)
                data = text.encode("utf-8")
            writer.writestr(info, data)
        for name, data in (extra or {}).items():
            writer.writestr(name, data)


@pytest.mark.parametrize(
    ("fixture", "title", "author", "chapters"),
    [
        (
            "aesop.epub",
            "Aesop Fables",
            "Aesop",
            ["The North Wind and the Sun", "The Tortoise and the Hare"],
        ),
        ("oedipus.epub", "Oedipus Rex", "Sophocles", ["Prologue", "Parodos"]),
    ],
)
def test_epub2_and_epub3_golden_books_extract_metadata_and_chapters(
    host, fixture, title, author, chapters
):
    item_id = _add_epub(host, FIXTURES / fixture)
    book = json.loads(
        (host.config.library_dir / item_id / "book.json").read_text(encoding="utf-8")
    )
    assert book["title"] == title
    assert book["author"] == author
    assert [chapter["title"] for chapter in book["chapters"]] == chapters
    assert len(book["chapters"][0]["paragraphs"]) >= 2

    chapter = host.client.get(f"/api/items/{item_id}/book/chapters/0")
    assert chapter.status_code == 200, chapter.text
    payload = chapter.json()
    assert payload["title"] == chapters[0]
    assert payload["text"] == book["chapters"][0]["text"]
    assert payload["paragraphs"] == book["chapters"][0]["paragraphs"]
    assert "<p>" in payload["html"]


def test_reader_paginates_by_chapter_and_links_the_toc(host):
    item_id = _add_epub(host, FIXTURES / "aesop.epub")
    first = host.client.get(f"/items/{item_id}/read")
    assert first.status_code == 200
    assert "The North Wind and the Sun" in first.text
    assert "A Hare one day ridiculed" not in first.text
    assert f'/items/{item_id}/read?chapter=1' in first.text

    second = host.client.get(f"/items/{item_id}/read", params={"chapter": 1})
    assert second.status_code == 200
    assert "A Hare one day ridiculed" in second.text
    assert "wrapped in a cloak" not in second.text
    assert f'/items/{item_id}/read?chapter=0' in second.text


def test_reading_progress_is_saved_and_restored(host):
    item_id = _add_epub(host, FIXTURES / "aesop.epub")
    host.login()
    response = host.client.put(
        f"/api/items/{item_id}/progress",
        json={
            "book_locator": {
                "chapter_index": 1,
                "paragraph_index": 2,
                "scroll_ratio": 0.4,
            }
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()["item"]
    assert payload["consumption_state"] == "in_progress"
    assert json.loads(payload["book_locator"]) == {
        "chapter_index": 1,
        "paragraph_index": 2,
        "scroll_ratio": 0.4,
    }

    page = host.client.get(f"/items/{item_id}/read")
    assert page.status_code == 200
    assert 'data-reader-chapter="1"' in page.text
    assert 'data-reader-scroll="0.4"' in page.text
    assert "A Hare one day ridiculed" in page.text


def test_reading_progress_rejects_unknown_chapter(host):
    item_id = _add_epub(host, FIXTURES / "aesop.epub")
    host.login()
    response = host.client.put(
        f"/api/items/{item_id}/progress",
        json={"book_locator": {"chapter_index": 9}},
    )
    assert response.status_code == 422
    assert response.json()["details"]["code"] == "book.chapter_not_found"


def test_reading_at_the_start_does_not_mark_the_book_in_progress(host):
    item_id = _add_epub(host, FIXTURES / "aesop.epub")
    host.login()
    response = host.client.put(
        f"/api/items/{item_id}/progress",
        json={
            "book_locator": {
                "chapter_index": 0,
                "paragraph_index": 0,
                "scroll_ratio": 0.0,
            }
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["item"]["consumption_state"] == "unstarted"

    scrolled = host.client.put(
        f"/api/items/{item_id}/progress",
        json={
            "book_locator": {
                "chapter_index": 0,
                "paragraph_index": 2,
                "scroll_ratio": 0.2,
            }
        },
    )
    assert scrolled.json()["item"]["consumption_state"] == "in_progress"


def test_reading_progress_does_not_reset_a_finished_book(host):
    item_id = _add_epub(host, FIXTURES / "aesop.epub")
    host.login()
    host.client.post(f"/items/{item_id}/state", data={"state": "finished"})
    response = host.client.put(
        f"/api/items/{item_id}/progress",
        json={"book_locator": {"chapter_index": 1, "scroll_ratio": 0.2}},
    )
    assert response.status_code == 200, response.text
    assert response.json()["item"]["consumption_state"] == "finished"


def test_reading_progress_requires_a_position(host):
    item_id = _add_epub(host, FIXTURES / "aesop.epub")
    host.login()
    response = host.client.put(f"/api/items/{item_id}/progress", json={})
    assert response.status_code == 422
    assert response.json()["details"]["code"] == "progress.missing"


def test_book_chapter_api_handles_missing_items_and_chapters(host):
    item_id = _add_epub(host, FIXTURES / "aesop.epub")
    host.login()
    missing_chapter = host.client.get(f"/api/items/{item_id}/book/chapters/9")
    assert missing_chapter.status_code == 404
    assert missing_chapter.json()["details"]["code"] == "book.chapter_not_found"
    missing_item = host.client.get("/api/items/missing/book/chapters/0")
    assert missing_item.status_code == 404


def test_reader_pages_send_a_restrictive_csp(host):
    item_id = _add_epub(host, FIXTURES / "aesop.epub")
    for path in ("/library", f"/items/{item_id}/read", f"/items/{item_id}"):
        response = host.client.get(path)
        policy = response.headers.get("content-security-policy")
        assert policy is not None
        assert "default-src 'self'" in policy
        assert "script-src 'self'" in policy
        assert "object-src 'none'" in policy
    detail = host.client.get(f"/items/{item_id}").text
    assert "onsubmit=" not in detail


def test_chapter_html_is_sanitized_and_remote_resources_are_removed(host, tmp_path):
    malicious = b"""<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Bad</title>
<script>alert('x')</script></head>
<body onload="alert('body')">
<h1>Bad chapter</h1>
<p onclick="alert('p')">Safe <strong>text</strong></p>
<img src="https://evil.example/tracker.png" onerror="alert('img')">
<a href="javascript:alert('link')">link</a>
<script src="https://evil.example/x.js"></script>
</body></html>"""
    book = tmp_path / "malicious.epub"
    _rewrite_epub(FIXTURES / "aesop.epub", book, chapter=malicious)
    item_id = _add_epub(host, book)
    stored = json.loads(
        (host.config.library_dir / item_id / "book.json").read_text(encoding="utf-8")
    )
    chapter_html = stored["chapters"][0]["html"]
    assert "Safe" in chapter_html
    assert "<script" not in chapter_html
    assert "<img" not in chapter_html
    assert "onclick" not in chapter_html
    assert "javascript:" not in chapter_html
    assert "evil.example" not in chapter_html

    page = host.client.get(f"/items/{item_id}/read")
    assert "alert(" not in page.text
    assert "evil.example" not in page.text


def test_br_separated_text_becomes_readable_paragraphs(host, tmp_path):
    chapter = b"""<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"><head><title>line one</title></head>
<body><p>line one<br/>line two<br/>line three</p></body></html>"""
    book = tmp_path / "line-breaks.epub"
    _rewrite_epub(FIXTURES / "aesop.epub", book, chapter=chapter)
    item_id = _add_epub(host, book)
    stored = json.loads(
        (host.config.library_dir / item_id / "book.json").read_text(encoding="utf-8")
    )
    parsed = stored["chapters"][0]
    assert parsed["paragraphs"] == ["line one", "line two", "line three"]
    assert parsed["title"] == "The North Wind and the Sun"
    assert parsed["text"] == "line one\nline two\nline three"
    page = host.client.get(f"/items/{item_id}/read")
    assert page.text.count('class="paragraph"') == 3


def test_hash_like_metadata_title_falls_back_to_the_source_filename(host, tmp_path):
    book = tmp_path / "道德经.epub"
    _rewrite_epub(
        FIXTURES / "aesop.epub",
        book,
        opf_transform=lambda text: text.replace(
            "Aesop Fables", "522eef450ff7ad80555d52b3c78fe447"
        ),
    )
    item_id = _add_epub(host, book)
    item = host.item(item_id)
    assert item["title"] == "道德经"
    stored = json.loads(
        (host.config.library_dir / item_id / "book.json").read_text(encoding="utf-8")
    )
    assert stored["title"] == "道德经"


def test_missing_spine_is_rejected_without_creating_an_item(host, tmp_path):
    import re

    book = tmp_path / "missing-spine.epub"
    _rewrite_epub(
        FIXTURES / "aesop.epub",
        book,
        opf_transform=lambda text: re.sub(r"<spine.*?</spine>", "", text, flags=re.S),
    )
    host.login()
    response = host.client.post("/api/items", json={"kind": "path", "path": str(book)})
    assert response.status_code == 422
    assert response.json()["details"]["code"] == "epub.invalid"
    assert list(host.config.library_dir.iterdir()) == []


def test_font_only_encryption_is_not_treated_as_drm(host, tmp_path):
    book = tmp_path / "font-obfuscation.epub"
    encryption = b"""<?xml version="1.0"?>
<encryption xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <EncryptedData xmlns="http://www.w3.org/2001/04/xmlenc#">
    <CipherData><CipherReference URI="OEBPS/fonts/body.otf"/></CipherData>
  </EncryptedData>
</encryption>"""
    _rewrite_epub(
        FIXTURES / "aesop.epub",
        book,
        extra={"META-INF/encryption.xml": encryption},
    )
    item_id = _add_epub(host, book)
    assert host.item(item_id)["status_category"] == "ready"


def test_cover_is_extracted_and_served(host, tmp_path):
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+ip1sAAAAASUVORK5CYII="
    )
    book = tmp_path / "with-cover.epub"
    _rewrite_epub(
        FIXTURES / "aesop.epub",
        book,
        opf_transform=lambda text: text.replace(
            "</metadata>", '<meta name="cover" content="cover-img"/></metadata>'
        ).replace(
            "</manifest>",
            '<item id="cover-img" href="cover.png" '
            'media-type="image/png" properties="cover-image"/></manifest>',
        ),
        extra={"OEBPS/cover.png": png},
    )
    item_id = _add_epub(host, book)
    item = host.client.get(f"/api/items/{item_id}").json()
    assert item["has_cover"] is True
    cover = host.client.get(item["cover_url"])
    assert cover.status_code == 200
    assert cover.headers["content-type"] == "image/png"
    assert cover.headers["etag"]
    assert (host.config.library_dir / item_id / "cover.png").is_file()
