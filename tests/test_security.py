from __future__ import annotations

import json
import socket
import zipfile
from importlib.metadata import version
from pathlib import Path

import pytest

from trove.adapters import safe_http
from trove.adapters.epub import EpubExtractor
from trove.adapters.ffmpeg import FfmpegAudioExtractor
from trove.adapters.safe_http import SafeHttpClient, SafeHttpError, validate_public_url
from trove.errors import ValidationError
from trove.ports import StageContext

from .conftest import seed_item
from .fakes import FIXTURES


def _resolve_to(*addresses: str):
    def fake_getaddrinfo(host, port, *args, **kwargs):
        return [
            (
                socket.AF_INET6 if ":" in address else socket.AF_INET,
                socket.SOCK_STREAM,
                6,
                "",
                (address, port),
            )
            for address in addresses
        ]

    return fake_getaddrinfo


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/feed.xml",
        "file:///etc/passwd",
        "http://",
        "http://user:secret@example.com/feed.xml",
    ],
)
def test_public_url_rejects_bad_schemes_or_credentials(monkeypatch, url):
    with pytest.raises(SafeHttpError):
        validate_public_url(url)


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.1.2.3",
        "172.16.0.1",
        "192.168.1.1",
        "169.254.169.254",
        "100.64.0.1",
        "0.0.0.0",
        "::1",
        "fe80::1",
        "::ffff:127.0.0.1",
        "2001:db8::1",
    ],
)
def test_public_url_rejects_private_and_special_addresses(monkeypatch, address):
    monkeypatch.setattr(safe_http.socket, "getaddrinfo", _resolve_to(address))
    with pytest.raises(SafeHttpError) as caught:
        validate_public_url("https://feed.example.com/rss")
    assert caught.value.code == "feed.private_address"


def test_public_url_allows_public_addresses(monkeypatch):
    monkeypatch.setattr(safe_http.socket, "getaddrinfo", _resolve_to("93.184.216.34"))
    assert validate_public_url("https://feed.example.com/rss") == "https://feed.example.com/rss"


def test_public_url_rejects_localhost_without_resolving():
    with pytest.raises(SafeHttpError):
        validate_public_url("http://localhost:8000/feed.xml")


def _fake_stream(status_code, *, headers=None, body=b"", url="https://feed.example.com/rss"):
    class Response:
        def __init__(self):
            self.status_code = status_code
            self.headers = headers or {}
            self.url = url

        def iter_bytes(self, size):
            yield body

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    return Response()


def test_redirect_to_private_address_is_rejected(monkeypatch):
    real_getaddrinfo = socket.getaddrinfo

    def resolve(host, port, *args, **kwargs):
        if host == "feed.example.com":
            return _resolve_to("93.184.216.34")(host, port, *args, **kwargs)
        return real_getaddrinfo(host, port, *args, **kwargs)

    monkeypatch.setattr(safe_http.socket, "getaddrinfo", resolve)

    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def stream(self, method, url):
            return _fake_stream(
                302,
                headers={"location": "http://169.254.169.254/latest/meta-data"},
            )

    monkeypatch.setattr(safe_http.httpx, "Client", Client)
    with pytest.raises(SafeHttpError) as caught:
        SafeHttpClient().get_bytes("https://feed.example.com/rss", max_bytes=1024)
    assert caught.value.code == "feed.private_address"


def test_download_limit_removes_partial_file(monkeypatch, tmp_path):
    monkeypatch.setattr(safe_http.socket, "getaddrinfo", _resolve_to("93.184.216.34"))

    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def stream(self, method, url):
            return _fake_stream(200, headers={"content-type": "audio/mpeg"}, body=b"x" * 2048)

    monkeypatch.setattr(safe_http.httpx, "Client", Client)
    destination = tmp_path / "episode.mp3"
    with pytest.raises(SafeHttpError) as caught:
        SafeHttpClient().download_to_file(
            "https://feed.example.com/episode.mp3",
            destination,
            max_bytes=1024,
            allowed_types={"audio/mpeg"},
        )
    assert caught.value.code == "download.too_large"
    assert not destination.exists()
    assert not (tmp_path / "episode.mp3.tmp").exists()


@pytest.mark.ffmpeg
def test_media_probe_rejects_corrupt_and_wrong_kind_files(tmp_path):
    probe = FfmpegAudioExtractor()
    fake_audio = tmp_path / "fake.mp3"
    fake_audio.write_bytes(b"not media")

    with pytest.raises(ValidationError) as corrupt:
        probe.probe(fake_audio, kind="audio")
    assert "media" in str(corrupt.value).lower() or "corrupt" in str(corrupt.value).lower()

    with pytest.raises(ValidationError):
        probe.probe(FIXTURES / "short.wav", kind="video")


def _malicious_epub(path: Path) -> None:
    container = """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>"""
    opf = """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="bookid">urn:uuid:test</dc:identifier>
    <dc:title>Malicious Book</dc:title>
    <dc:creator>Attacker</dc:creator>
    <dc:language>en</dc:language>
  </metadata>
  <manifest>
    <item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine><itemref idref="chapter"/></spine>
</package>"""
    chapter = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>Chapter</title><script>alert('inline')</script></head>
<body onload="alert('body')">
  <h1>Safe heading</h1>
  <p onclick="alert('click')">Visible paragraph.</p>
  <script src="https://evil.example/x.js"></script>
  <img src="https://evil.example/tracker.png" onerror="alert('img')"/>
  <a href="javascript:alert('link')">link text</a>
</body>
</html>"""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr("META-INF/container.xml", container)
        archive.writestr("OEBPS/content.opf", opf)
        archive.writestr("OEBPS/chapter.xhtml", chapter)


def _context(tmp_path: Path) -> StageContext:
    return StageContext(
        item_id="item",
        run_id="run",
        work_dir=tmp_path,
        should_cancel=lambda: False,
        log=lambda message: None,
    )


def test_epub_html_is_sanitized(tmp_path):
    book = tmp_path / "malicious.epub"
    _malicious_epub(book)

    result = EpubExtractor().extract(book, _context(tmp_path))

    chapter = result.chapters[0]
    assert "Visible paragraph." in chapter.text
    html = chapter.html.lower()
    for forbidden in ("<script", "onclick", "onerror", "onload", "javascript:", "https://"):
        assert forbidden not in html
    assert "<p" in html


def test_upload_rejects_corrupt_epub_and_cleans_temp(host):
    host.login()
    response = host.client.post(
        "/api/uploads",
        files={"file": ("broken.epub", b"not an epub", "application/epub+zip")},
    )
    assert response.status_code == 422
    assert response.json()["details"]["code"] == "epub.invalid"
    assert list(host.config.uploads_dir.iterdir()) == []


@pytest.mark.ffmpeg
def test_upload_rejects_corrupt_media_and_cleans_temp(host):
    host.login()
    response = host.client.post(
        "/api/uploads",
        files={"file": ("broken.wav", b"not audio", "audio/wav")},
    )
    assert response.status_code == 422
    assert response.json()["details"]["code"] == "upload.invalid_media"
    assert list(host.config.uploads_dir.iterdir()) == []


def test_upload_temp_directory_permissions(host):
    host.login()
    response = host.client.post(
        "/api/uploads",
        files={
            "file": (
                "aesop.epub",
                (FIXTURES / "aesop.epub").read_bytes(),
                "application/epub+zip",
            )
        },
    )
    assert response.status_code == 200, response.text
    directory = host.config.uploads_dir / response.json()["upload_id"]
    assert directory.stat().st_mode & 0o777 == 0o700
    assert (directory / "aesop.epub").stat().st_mode & 0o777 == 0o600


def test_upload_mime_must_match_extension(host):
    host.login()
    response = host.client.post(
        "/api/uploads",
        files={"file": ("book.epub", b"data", "audio/mpeg")},
    )
    assert response.status_code == 422
    assert response.json()["details"]["code"] == "upload.invalid_type"
    assert list(host.config.uploads_dir.iterdir()) == []


def test_security_headers_and_html_escaping(host):
    bundle = seed_item(host, title="<script>alert('title')</script>")
    host.login()
    page = host.client.get(f"/items/{bundle.item.id}")
    assert page.status_code == 200
    assert "alert('title')" not in page.text
    assert "&lt;script&gt;" in page.text
    csp = page.headers["content-security-policy"]
    assert "default-src 'self'" in csp
    assert "script-src 'self'" in csp
    assert "img-src 'self' data:" in csp
    assert page.headers["x-content-type-options"] == "nosniff"
    assert page.headers["referrer-policy"] == "same-origin"
    assert page.headers["x-frame-options"] == "DENY"


def test_session_cookie_attributes(api_host):
    response = api_host.client.post(
        "/login",
        data={"password": "test-password"},
        headers={"x-forwarded-proto": "https"},
    )
    assert response.status_code == 303
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=lax" in cookie
    assert "secure" in cookie
    assert "path=/" in cookie


def test_file_routes_require_auth_and_hide_missing_artifacts(api_host):
    response = api_host.client.get("/api/items/anything/audio")
    assert response.status_code == 401
    assert response.json() == {
        "code": "auth.required",
        "message": "Sign in required",
    }


def test_starlette_is_patched_for_range_dos():
    parts = tuple(int(part) for part in version("starlette").split(".")[:3])
    assert parts >= (0, 49, 1)


def test_pyproject_declares_patched_starlette():
    import tomllib

    data = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    dependencies = data["project"]["dependencies"]
    assert any(dependency.startswith("starlette>=") for dependency in dependencies)


def test_artifact_metadata_is_exposed_without_paths(host):
    bundle = seed_item(host, title="Artifact metadata")
    host.login()
    payload = host.client.get(f"/api/items/{bundle.item.id}").json()
    assert "source_path" not in payload
    artifact = payload["artifacts"][0]
    assert artifact["kind"] == "audio"
    assert artifact["sha256"]
    assert artifact["size"] > 0
    assert artifact["mime"] == "audio/mp4"
    assert "path" not in artifact
    assert str(host.config.home) not in json.dumps(payload)
