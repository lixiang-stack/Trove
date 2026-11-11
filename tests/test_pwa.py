from __future__ import annotations

import json
import struct


def _png_size(data: bytes) -> tuple[int, int]:
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    return struct.unpack(">II", data[16:24])


def test_manifest_and_service_worker_are_public(api_host):
    manifest = api_host.client.get("/manifest.webmanifest")
    assert manifest.status_code == 200
    assert manifest.headers["content-type"].startswith("application/manifest+json")
    payload = json.loads(manifest.text)
    assert payload["name"] == "拾藏 Trove"
    assert payload["display"] == "standalone"
    assert payload["start_url"] == "/library"
    assert payload["scope"] == "/"
    assert {icon["sizes"] for icon in payload["icons"]} == {"192x192", "512x512"}

    worker = api_host.client.get("/sw.js")
    assert worker.status_code == 200
    assert worker.headers["content-type"].startswith("text/javascript")
    assert worker.headers["service-worker-allowed"] == "/"
    assert worker.headers["cache-control"] == "no-store"
    assert "trove-shell-v1" in worker.text
    assert 'url.pathname.startsWith("/static/")' in worker.text


def test_manifest_icons_exist_and_have_expected_sizes(api_host):
    for name, expected in (
        ("icon-180.png", (180, 180)),
        ("icon-192.png", (192, 192)),
        ("icon-512.png", (512, 512)),
    ):
        response = api_host.client.get(f"/static/{name}")
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"
        assert _png_size(response.content) == expected
    logo = api_host.client.get("/static/icon.svg")
    assert logo.status_code == 200
    assert logo.headers["content-type"].startswith("image/svg+xml")


def test_base_html_links_manifest_and_pwa_registration(api_host):
    page = api_host.client.get("/login")
    assert page.status_code == 200
    assert 'rel="manifest" href="/manifest.webmanifest"' in page.text
    assert 'rel="apple-touch-icon" href="/static/icon-180.png"' in page.text
    assert '<meta name="theme-color" content="#b5462f">' in page.text
    assert "/static/pwa.js?v=" in page.text
