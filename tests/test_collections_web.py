from __future__ import annotations

from trove.ports import LinkProbeResult

from .fakes import video_collection

PLAYLIST = "https://www.youtube.com/playlist?list=PLtestcollection"
EPISODE_1 = "https://www.youtube.com/watch?v=episode0001"
EPISODE_2 = "https://www.youtube.com/watch?v=episode0002"


def _seed(host) -> None:
    host.stack.video_inspector.collections[PLAYLIST] = video_collection(
        "Fixture Collection",
        [("Episode One", EPISODE_1, 60.0), ("Episode Two", EPISODE_2, 30.0)],
    )


def test_add_page_uses_unified_link_panel(api_host):
    api_host.login()
    page = api_host.client.get("/add")
    assert page.status_code == 200
    assert "识别链接" in page.text
    assert "本地路径" in page.text
    assert "上传文件" in page.text
    assert "视频链接" not in page.text


def test_link_preview_is_fragment_and_confirm_adds_collection(api_host):
    _seed(api_host)
    api_host.login()
    preview = api_host.client.post(
        "/add/link/preview",
        data={"url": PLAYLIST},
        headers={"HX-Request": "true"},
    )
    assert preview.status_code == 200, preview.text
    assert "添加合集（2 集）" in preview.text
    assert "Fixture Collection" in preview.text
    assert "本地路径" not in preview.text

    created = api_host.client.post("/add/link", data={"url": PLAYLIST})
    assert created.status_code == 303, created.text
    location = created.headers["location"]
    assert location.startswith("/collections/")

    page = api_host.client.get(location)
    assert page.status_code == 200
    assert "Fixture Collection" in page.text
    assert "重试失败项" not in page.text

    listing = api_host.client.get("/collections")
    assert listing.status_code == 200
    assert "Fixture Collection" in listing.text
    assert "2 集" in listing.text


def test_library_shows_collections_entry(api_host):
    _seed(api_host)
    api_host.login()
    api_host.client.post("/add/link", data={"url": PLAYLIST})
    library = api_host.client.get("/library")
    assert library.status_code == 200
    assert "合集 1" in library.text


def test_delete_collection_from_console(api_host):
    _seed(api_host)
    api_host.login()
    created = api_host.client.post("/api/collections", json={"url": PLAYLIST})
    collection_id = created.json()["collection"]["id"]
    deleted = api_host.client.post(
        f"/collections/{collection_id}/delete", data={"mode": "ungroup"}
    )
    assert deleted.status_code == 303
    assert deleted.headers["location"] == "/collections"
    assert api_host.client.get(f"/collections/{collection_id}").status_code == 404


def test_ebook_and_podcast_preview_render(api_host):
    api_host.login()
    ebook_url = "https://example.com/books/aesop.epub"
    api_host.stack.link_probe.responses[ebook_url] = LinkProbeResult(
        content_type="application/epub+zip",
        content_length=2048,
        final_url=ebook_url,
    )
    ebook = api_host.client.post(
        "/add/link/preview",
        data={"url": ebook_url},
        headers={"HX-Request": "true"},
    )
    assert ebook.status_code == 200, ebook.text
    assert "添加电子书" in ebook.text

    feed = api_host.client.post(
        "/add/link/preview",
        data={"url": "https://example.com/feed.xml"},
        headers={"HX-Request": "true"},
    )
    assert feed.status_code == 200, feed.text
    assert "The Public Domain Radio Hour" in feed.text
    assert "/add/podcast" in feed.text
