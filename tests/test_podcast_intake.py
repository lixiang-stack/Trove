from __future__ import annotations

import contextlib

import pytest

from trove.adapters.feed import download_episode
from trove.adapters.safe_http import SafeHttpClient, SafeHttpError, validate_public_url
from trove.errors import ProcessingError
from trove.ports import FeedEpisode

from .fakes import FIXTURES


def test_feed_preview_returns_recent_episodes(api_host):
    api_host.login()
    response = api_host.client.post(
        "/api/feeds/preview", json={"url": "https://example.com/podcast"}
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["title"] == "The Public Domain Radio Hour"
    assert len(payload["episodes"]) == 2
    first = payload["episodes"][0]
    assert first["guid"] == "episode-001"
    assert first["title"].startswith("Episode 1")
    assert first["published_at"].startswith("2026-11-02")
    assert first["duration_sec"] == 120
    assert first["enclosure_url"] == "https://example.com/media/episode-001.mp3"


def test_html_feed_preview_uses_htmx_partial(api_host):
    api_host.login()
    response = api_host.client.post(
        "/add/feed/preview",
        data={"feed_url": "https://example.com/podcast"},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    assert "Episode 1" in response.text
    assert "<html" not in response.text


def test_add_podcast_episode_creates_item_and_audio(host):
    host.login()
    response = host.client.post(
        "/api/items",
        json={
            "kind": "podcast",
            "feed_url": "https://example.com/podcast",
            "episode_guid": "episode-001",
        },
    )
    assert response.status_code == 201, response.text
    item_id = response.json()["item"]["id"]
    payload = host.wait_for_item(item_id)
    assert payload["processing_state"] == "completed"
    assert payload["source_type"] == "podcast_episode"
    assert payload["platform"] == "podcast"
    assert payload["title"].startswith("Episode 1")
    assert (host.config.library_dir / item_id / "audio.m4a").is_file()
    source = host.runtime.library.source_document(item_id)
    assert source["feed"]["episode_guid"] == "episode-001"
    assert source["feed"]["enclosure_url"] == "https://example.com/media/episode-001.mp3"
    assert source["source_key"] == "https://example.com/podcast#episode-001"


def test_duplicate_episode_is_deduplicated(host):
    host.login()
    payload = {
        "kind": "podcast",
        "feed_url": "https://example.com/podcast",
        "episode_guid": "episode-002",
    }
    first = host.client.post("/api/items", json=payload)
    item_id = first.json()["item"]["id"]
    host.wait_for_item(item_id)
    second = host.client.post("/api/items", json=payload)
    assert second.status_code == 200
    assert second.json()["deduplicated"] is True
    assert second.json()["item"]["id"] == item_id
    assert len(host.stack.downloader.calls) == 1
    # Previewing again must not subscribe or auto-ingest anything.
    host.client.post("/api/feeds/preview", json={"url": "https://example.com/podcast"})
    assert host.client.get("/api/items").json()["count"] == 1


def test_feed_too_large_is_rejected(api_host):
    api_host.login()
    api_host.stack.feed_http.content = b"x" * (11 * 1024 * 1024)
    response = api_host.client.post(
        "/api/feeds/preview", json={"url": "https://example.com/podcast"}
    )
    assert response.status_code == 422
    assert response.json()["details"]["code"] == "feed.too_large"


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/feed",
        "http://10.0.0.1/feed",
        "http://192.168.1.2/feed",
        "http://169.254.169.254/latest/meta-data",
        "http://100.64.0.1/feed",
        "http://[::1]/feed",
        "http://[fc00::1]/feed",
        "http://localhost/feed",
        "file:///etc/passwd",
        "https://user:pass@example.com/feed",
    ],
)
def test_ssrf_validation_blocks_private_and_metadata(url):
    with pytest.raises(SafeHttpError):
        validate_public_url(url)


class _FakeStreamResponse:
    def __init__(self, url: str) -> None:
        self.status_code = 302
        self.headers = {"location": "http://127.0.0.1/secret"}
        self.url = url

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None


class _FakeClient:
    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    @contextlib.contextmanager
    def stream(self, method, url):
        yield _FakeStreamResponse(url)


def test_redirect_to_private_address_is_rejected(monkeypatch):
    import trove.adapters.safe_http as module

    monkeypatch.setattr(module.httpx, "Client", _FakeClient)
    with pytest.raises(SafeHttpError, match="私网"):
        SafeHttpClient().get_bytes("https://example.com/feed", max_bytes=1024)


def test_enclosure_size_and_type_errors_are_classified():
    class FakeHttp:
        def __init__(self, error):
            self.error = error

        def download_to_file(self, url, destination, **kwargs):
            raise self.error

    episode = FeedEpisode(
        guid="g",
        title="t",
        author=None,
        published_at=None,
        duration_sec=None,
        enclosure_url="https://example.com/ep.mp3",
        enclosure_type="audio/mpeg",
        enclosure_size=1,
    )
    too_large = FakeHttp(SafeHttpError("download.too_large", "too large"))
    with pytest.raises(ProcessingError) as exc:
        download_episode(too_large, episode, FIXTURES / "x", max_bytes=1)
    assert exc.value.code == "download.too_large"
    bad_type = FakeHttp(SafeHttpError("download.invalid_type", "bad type"))
    with pytest.raises(ProcessingError) as exc:
        download_episode(bad_type, episode, FIXTURES / "x", max_bytes=1)
    assert exc.value.code == "download.invalid_type"


def test_episode_without_guid_uses_enclosure_url(host):
    import re

    xml = (FIXTURES / "podcast.xml").read_text(encoding="utf-8")
    xml = re.sub(r"<guid[^>]*>.*?</guid>\s*", "", xml, flags=re.S)
    host.stack.feed_http.content = xml.encode("utf-8")
    host.login()
    preview = host.client.post(
        "/api/feeds/preview", json={"url": "https://example.com/podcast"}
    ).json()
    assert preview["episodes"][0]["guid"] is None
    enclosure = preview["episodes"][0]["enclosure_url"]
    response = host.client.post(
        "/api/items",
        json={
            "kind": "podcast",
            "feed_url": "https://example.com/podcast",
            "enclosure_url": enclosure,
        },
    )
    assert response.status_code == 201, response.text
    item_id = response.json()["item"]["id"]
    host.wait_for_item(item_id)
    source = host.runtime.library.source_document(item_id)
    assert source["source_key"] == f"https://example.com/podcast#{enclosure}"
    again = host.client.post(
        "/api/items",
        json={
            "kind": "podcast",
            "feed_url": "https://example.com/podcast",
            "enclosure_url": enclosure,
        },
    )
    assert again.status_code == 200
    assert again.json()["deduplicated"] is True
