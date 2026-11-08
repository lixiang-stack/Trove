from __future__ import annotations

import json

from sqlalchemy import text

from .conftest import seed_item


def test_library_and_detail_show_seeded_item(host):
    bundle = seed_item(
        host,
        title="记忆是智能体的瓶颈",
        author="张三",
        source_url_raw="https://example.com/watch?v=abc&utm_source=x",
        source_url_canonical="https://example.com/watch?v=abc",
        source_type="video_url",
        platform="youtube",
        tags=["智能体", "记忆"],
    )
    host.login()
    library = host.client.get("/library")
    assert library.status_code == 200
    assert "记忆是智能体的瓶颈" in library.text
    assert "张三" in library.text
    detail = host.client.get(f"/items/{bundle.item.id}")
    assert detail.status_code == 200
    assert "https://example.com/watch?v=abc" in detail.text
    assert "智能体" in detail.text

    payload = host.client.get(f"/api/items/{bundle.item.id}").json()
    source = json.loads(
        (host.config.library_dir / bundle.item.id / "source.json").read_text(encoding="utf-8")
    )
    for key in ("title", "author", "source_url_raw", "source_url_canonical", "source_type"):
        assert payload[key] == source[key]


def test_patch_title_and_author_syncs_everywhere(host):
    bundle = seed_item(
        host,
        title="Old title",
        author="Old author",
        source_url_raw="https://example.com/old?utm_source=x",
        source_url_canonical="https://example.com/old",
    )
    host.login()
    response = host.client.patch(
        f"/api/items/{bundle.item.id}",
        json={"title": "New title", "author": "New author"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["title"] == "New title"
    assert payload["author"] == "New author"
    assert payload["source_url_raw"] == "https://example.com/old?utm_source=x"
    assert payload["source_url_canonical"] == "https://example.com/old"
    detail = host.client.get(f"/items/{bundle.item.id}")
    assert "New title" in detail.text and "New author" in detail.text
    library = host.client.get("/library")
    assert "New title" in library.text
    source = json.loads(
        (host.config.library_dir / bundle.item.id / "source.json").read_text(encoding="utf-8")
    )
    assert source["title"] == "New title"
    assert source["author"] == "New author"


def test_delete_removes_derived_data_but_keeps_original(host):
    original = host.config.home / "user-original.m4a"
    original.write_bytes(b"user-owned")
    bundle = seed_item(host, title="Delete me", source_path=str(original))
    with host.runtime.sessions() as session:
        host.runtime.search_index.index_item(session, bundle.item.id)
        session.commit()
        assert session.execute(text("SELECT count(*) FROM search_fts")).scalar() >= 1
    host.login()
    response = host.client.delete(f"/api/items/{bundle.item.id}")
    assert response.status_code == 204
    assert not (host.config.library_dir / bundle.item.id).exists()
    assert original.read_bytes() == b"user-owned"
    assert host.client.get(f"/api/items/{bundle.item.id}").status_code == 404
    with host.runtime.sessions() as session:
        assert session.execute(text("SELECT count(*) FROM search_fts")).scalar() == 0
        assert session.execute(text("SELECT count(*) FROM items")).scalar() == 0
        assert session.execute(text("SELECT count(*) FROM artifacts")).scalar() == 0


def test_unknown_item_returns_404(host):
    host.login()
    assert host.client.get("/api/items/missing").status_code == 404
    assert host.client.get("/items/missing").status_code == 404


def test_empty_library_links_to_add(host):
    host.login()
    response = host.client.get("/library")
    assert "Library 还是空的" in response.text
    assert "添加第一条内容" in response.text


def test_library_requires_auth(api_host):
    assert api_host.client.get("/library").status_code == 303
    assert api_host.client.get("/api/items").status_code == 401


def test_title_edit_updates_search_index(host):
    bundle = seed_item(host, title="Alpha Old", tags=["记忆"])
    host.login()
    with host.runtime.sessions() as session:
        host.runtime.search_index.index_item(session, bundle.item.id)
        session.commit()
    assert host.client.get("/api/search", params={"q": "Alpha"}).json()["count"] == 1
    host.client.patch(f"/api/items/{bundle.item.id}", json={"title": "Gamma New"})
    assert host.client.get("/api/search", params={"q": "Alpha"}).json()["count"] == 0
    results = host.client.get("/api/search", params={"q": "Gamma"}).json()
    assert results["count"] == 1
    assert results["results"][0]["item"]["title"] == "Gamma New"
