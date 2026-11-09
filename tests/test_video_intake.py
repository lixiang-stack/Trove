from __future__ import annotations

import pytest

from trove.domain.urls import canonicalize_video_url
from trove.errors import ValidationError


@pytest.mark.parametrize(
    ("raw", "canonical", "platform"),
    [
        (
            "https://youtu.be/dQw4w9WgXcQ?t=42&utm_source=x",
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "youtube",
        ),
        (
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ&utm_medium=feed&fbclid=z",
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "youtube",
        ),
        (
            "https://m.youtube.com/shorts/abc123XYZ",
            "https://www.youtube.com/watch?v=abc123XYZ",
            "youtube",
        ),
        (
            "https://www.bilibili.com/video/BV1xx411c7mD/?spm_id_from=333.999",
            "https://www.bilibili.com/video/BV1xx411c7mD",
            "bilibili",
        ),
        (
            "http://bilibili.com/video/av123?p=1",
            "https://www.bilibili.com/video/av123",
            "bilibili",
        ),
        (
            "https://www.bilibili.com/video/BV1MLqDYxEpN?p=2",
            "https://www.bilibili.com/video/BV1MLqDYxEpN?p=2",
            "bilibili",
        ),
    ],
)
def test_url_normalization(raw, canonical, platform):
    result = canonicalize_video_url(raw)
    assert result.canonical == canonical
    assert result.source_key == canonical
    assert result.platform == platform
    assert result.raw == raw


@pytest.mark.parametrize(
    "raw",
    [
        "https://www.youtube.com/playlist?list=PL123",
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PL123",
        "https://www.bilibili.com/video/BV1xx411c7mD?p=0",
        "https://www.bilibili.com/video/BV1xx411c7mD?list=123",
        "https://www.bilibili.com/live/123",
        "https://vimeo.com/123",
        "ftp://youtube.com/watch?v=abc123",
        "https://youtube.com/watch?v=bad id",
    ],
)
def test_playlist_and_unsupported_urls_are_rejected(raw):
    with pytest.raises(ValidationError) as exc:
        canonicalize_video_url(raw)
    assert exc.value.details
    assert exc.value.details["code"].startswith("url.")


def test_add_bilibili_and_youtube_creates_queued_run(api_host):
    api_host.login()
    for url in (
        "https://www.bilibili.com/video/BV1xx411c7mD",
        "https://www.bilibili.com/video/BV1xx411c7mD?p=2",
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    ):
        response = api_host.client.post("/api/items", json={"kind": "url", "url": url})
        assert response.status_code == 201, response.text
        payload = response.json()["item"]
        assert payload["source_type"] == "video_url"
        assert payload["source_url_raw"] == url
        assert payload["run"]["state"] == "queued"


def test_duplicate_canonical_url_is_deduplicated(host):
    host.login()
    first = host.client.post(
        "/api/items",
        json={"kind": "url", "url": "https://youtu.be/dQw4w9WgXcQ?utm_source=a"},
    )
    assert first.status_code == 201
    item_id = first.json()["item"]["id"]
    host.wait_for_item(item_id)
    second = host.client.post(
        "/api/items",
        json={
            "kind": "url",
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ&fbclid=b",
        },
    )
    assert second.status_code == 200
    assert second.json()["deduplicated"] is True
    assert second.json()["item"]["id"] == item_id
    assert len(host.stack.downloader.calls) == 1
    with host.runtime.sessions() as session:
        from sqlalchemy import text

        assert session.execute(text("SELECT count(*) FROM runs")).scalar() == 1


def test_download_failure_is_reported_without_touching_library(host):
    host.login()
    response = host.client.post(
        "/api/items", json={"kind": "url", "url": "https://youtu.be/firstvideo"}
    )
    assert response.status_code == 201
    first_id = response.json()["item"]["id"]
    host.wait_for_item(first_id)
    host.stack.downloader.fail_code = "download.geo_restricted"
    response = host.client.post(
        "/api/items", json={"kind": "url", "url": "https://youtu.be/blockedvideo"}
    )
    item_id = response.json()["item"]["id"]
    payload = host.wait_for_item(item_id)
    assert payload["run"]["state"] == "failed"
    assert payload["run"]["error_code"] == "download.geo_restricted"
    library = host.client.get("/library")
    assert "Fixture Video" in library.text
    assert "https://www.youtube.com/watch?v=blockedvideo" in library.text
    blocked_detail = host.client.get(f"/items/{item_id}")
    assert "https://youtu.be/blockedvideo" in blocked_detail.text
    assert host.client.get(f"/api/items/{first_id}").status_code == 200


def test_detail_shows_source_metadata(host):
    host.login()
    response = host.client.post(
        "/api/items", json={"kind": "url", "url": "https://youtu.be/dQw4w9WgXcQ"}
    )
    item_id = response.json()["item"]["id"]
    host.wait_for_item(item_id)
    detail = host.client.get(f"/items/{item_id}")
    assert "https://youtu.be/dQw4w9WgXcQ" in detail.text
    assert "https://www.youtube.com/watch?v=dQw4w9WgXcQ" in detail.text
    assert "Fixture Author" in detail.text
    assert "2026-11-01T00:00:00+00:00" in detail.text
    item_dir = host.config.library_dir / item_id
    assert not list(item_dir.glob("*.mp4"))
    assert not list(item_dir.glob("*.webm"))
    assert (item_dir / "audio.m4a").is_file()


def test_html_add_form_rejects_playlist(api_host):
    api_host.login()
    response = api_host.client.post(
        "/add/url",
        data={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PL123"},
    )
    assert response.status_code == 422
    assert "播放列表" in response.text
