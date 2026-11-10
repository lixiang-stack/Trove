from __future__ import annotations

import re

from trove.clock import utc_ms

from .conftest import seed_item


def _order(html: str) -> list[str]:
    ordered: list[str] = []
    for item_id in re.findall(r'data-item-id="([^"]+)"', html):
        if item_id not in ordered:
            ordered.append(item_id)
    return ordered


def test_library_orders_by_recent_added(host):
    first = seed_item(host, title="First", source_key="seed:first")
    second = seed_item(host, title="Second", source_key="seed:second")
    third = seed_item(host, title="Third", source_key="seed:third")
    now = utc_ms()
    with host.runtime.sessions() as session:
        from trove.db.models import Item

        session.get(Item, first.item.id).created_at = now - 3000
        session.get(Item, second.item.id).created_at = now - 2000
        session.get(Item, third.item.id).created_at = now - 1000
        session.commit()
    host.login()
    assert _order(host.client.get("/library?sort=recent_added").text) == [
        third.item.id,
        second.item.id,
        first.item.id,
    ]
    assert _order(
        host.client.get("/library?sort=recent_consumed").text
    )[0] in {first.item.id, second.item.id, third.item.id}


def test_consumption_state_without_progress_displays_as_unstarted(host):
    bundle = seed_item(
        host,
        title="Stale progress state",
        consumption_state="in_progress",
        position=0.0,
    )
    host.login()
    payload = host.item(bundle.item.id)
    assert payload["consumption_state"] == "unstarted"
    assert payload["consumption_label"] == "Unstarted"
    page = host.client.get("/library")
    assert "Stale progress state" in page.text
    assert "consumption state-in_progress" not in page.text
    assert "consumption state-unstarted" in page.text
    unstarted = host.client.get("/library", params={"consumption": "unstarted"})
    assert "Stale progress state" in unstarted.text
    in_progress = host.client.get("/library", params={"consumption": "in_progress"})
    assert "Stale progress state" not in in_progress.text


def test_library_orders_by_recent_consumed(host):
    first = seed_item(
        host,
        title="First consumed",
        source_key="seed:c1",
        consumption_state="in_progress",
        position=1.0,
    )
    second = seed_item(
        host,
        title="Second consumed",
        source_key="seed:c2",
        consumption_state="in_progress",
        position=1.0,
    )
    with host.runtime.sessions() as session:
        from trove.db.models import Item

        now = utc_ms()
        session.get(Item, first.item.id).last_consumed_at = now - 1000
        session.get(Item, second.item.id).last_consumed_at = now - 500
        session.commit()
    host.login()
    assert _order(host.client.get("/library?sort=recent_consumed").text)[:2] == [
        second.item.id,
        first.item.id,
    ]


def test_inbox_filters_processing_and_failed(host):
    ready = seed_item(host, title="Ready item", source_key="seed:ready")
    processing = seed_item(
        host,
        title="Processing item",
        source_key="seed:processing",
        run_state="transcribing",
    )
    failed = seed_item(
        host,
        title="Failed item",
        source_key="seed:failed",
        run_state="failed",
    )
    host.login()
    library = host.client.get("/library")
    assert set(_order(library.text)) == {ready.item.id, processing.item.id, failed.item.id}
    inbox = host.client.get("/library?state=processing,failed")
    assert set(_order(inbox.text)) == {processing.item.id, failed.item.id}
    assert "Ready item" not in inbox.text
    assert "Transcribing" in inbox.text
    assert "Failed" in inbox.text


def test_active_status_badge_polls_and_failed_does_not(host):
    processing = seed_item(
        host,
        title="Processing",
        source_key="seed:poll",
        run_state="downloading",
    )
    failed = seed_item(
        host,
        title="Failed",
        source_key="seed:nopoll",
        run_state="failed",
    )
    host.login()
    active = host.client.get(f"/items/{processing.item.id}/status?context=row")
    assert "hx-trigger" in active.text
    assert "badge-processing" in active.text
    terminal = host.client.get(f"/items/{failed.item.id}/status?context=row")
    assert "hx-trigger" not in terminal.text
    assert "badge-failed" in terminal.text


def test_row_shows_title_author_type_tags_and_progress(host):
    bundle = seed_item(
        host,
        title="Row details",
        author="作者名",
        tags=["记忆", "智能体"],
        consumption_state="in_progress",
        position=1.0,
        duration=2.0,
        source_type="podcast_episode",
        platform="podcast",
    )
    host.login()
    row = host.client.get("/library").text
    assert "Row details" in row
    assert "作者名" in row
    assert "Podcast" in row
    assert "记忆" in row
    assert "In progress" in row
    assert "progress-line" in row
    assert f'data-audio-url="/api/items/{bundle.item.id}/audio"' in row


def test_navigation_skeleton_and_empty_state(host):
    host.login()
    library = host.client.get("/library").text
    for path in ("/library", "/search", "/add"):
        assert f'href="{path}"' in library
    assert "Library 还是空的" in library
    assert "添加第一条内容" in library
    add = host.client.get("/add").text
    assert "视频链接" in add
    assert "播客 feed" in add


def test_click_item_opens_now_playing_page(host):
    bundle = seed_item(host, title="Open me")
    host.login()
    page = host.client.get(f"/items/{bundle.item.id}/listen")
    assert page.status_code == 200
    assert "NOW PLAYING" in page.text
    assert f'href="/items/{bundle.item.id}"' in page.text
    assert 'href="/library"' in page.text


def test_inline_player_is_present_without_navigation(host):
    bundle = seed_item(host, title="Inline")
    host.login()
    library = host.client.get("/library").text
    assert f'data-inline-for="{bundle.item.id}"' in library
    assert 'data-play-item' in library
    assert "打开播放页" in library
