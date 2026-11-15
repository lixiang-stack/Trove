from __future__ import annotations

import json

from sqlalchemy import select

from trove.clock import utc_ms
from trove.content_package import BookChapterDocument, BookDocument
from trove.db.models import DeviceToken, Item, SyncFieldClock, SyncMutation
from trove.services.devices import hash_token

from .conftest import PASSWORD, seed_item


def _bearer(host, device_id: str, token: str, **headers: str) -> dict[str, str]:
    with host.runtime.sessions() as session:
        session.add(
            DeviceToken(
                device_id=device_id,
                name=device_id,
                token_hash=hash_token(token),
                created_at=utc_ms(),
                last_used_at=utc_ms(),
                session_epoch=host.config.session_epoch,
            )
        )
        session.commit()
    return {"authorization": f"Bearer {token}", **headers}


def _progress(host, item_id: str, body: dict, headers: dict | None = None):
    return host.client.put(
        f"/api/items/{item_id}/progress", json=body, headers=headers or {}
    )


def _tags(host, item_id: str, body: dict, headers: dict | None = None):
    return host.client.put(
        f"/api/items/{item_id}/tags", json=body, headers=headers or {}
    )


def _item(host, item_id: str) -> Item:
    with host.runtime.sessions() as session:
        return session.get(Item, item_id)


def _clocks(host, item_id: str) -> dict[str, SyncFieldClock]:
    with host.runtime.sessions() as session:
        rows = session.execute(
            select(SyncFieldClock).where(SyncFieldClock.item_id == item_id)
        ).scalars()
        return {row.field: row for row in rows}


def _with_book(host, title: str):
    bundle = seed_item(host, title=title, with_audio=False, run_state=None)
    host.runtime.package.write_book(
        bundle.item.id,
        BookDocument(
            title=title,
            chapters=[
                BookChapterDocument(
                    chapter_index=0,
                    title="One",
                    html="<p>One</p>",
                    text="One",
                    paragraphs=["One"],
                ),
                BookChapterDocument(
                    chapter_index=1,
                    title="Two",
                    html="<p>Two</p>",
                    text="Two",
                    paragraphs=["Two"],
                ),
            ],
        ),
    )
    return bundle


def test_newer_progress_wins_and_older_is_ignored(host):
    bundle = seed_item(host, title="LWW", duration=100.0)
    host.login()
    first = _progress(
        host,
        bundle.item.id,
        {"position_sec": 10.0, "client_updated_at": 1_000},
    )
    assert first.status_code == 200, first.text
    assert first.json()["applied"] is True
    assert first.json()["field_clocks"]["audio_progress"] == {
        "client_updated_at": 1_000,
        "device_id": "host-web",
    }

    older = _progress(
        host,
        bundle.item.id,
        {"position_sec": 20.0, "client_updated_at": 999},
    )
    assert older.status_code == 200
    assert older.json()["applied"] is False
    assert older.json()["item"]["audio_position_sec"] == 10.0

    newer = _progress(
        host,
        bundle.item.id,
        {"position_sec": 30.0, "client_updated_at": 1_001},
    )
    assert newer.json()["applied"] is True
    assert newer.json()["item"]["audio_position_sec"] == 30.0


def test_equal_timestamp_is_decided_by_device_id(host):
    bundle = seed_item(host, title="Tie", duration=100.0)
    host.login()
    headers = _bearer(host, "device-b", "token-b")
    first = _progress(
        host,
        bundle.item.id,
        {"position_sec": 10.0, "client_updated_at": 2_000},
        headers,
    )
    assert first.json()["applied"] is True
    assert first.json()["field_clocks"]["audio_progress"]["device_id"] == "device-b"

    lower = _progress(
        host,
        bundle.item.id,
        {"position_sec": 20.0, "client_updated_at": 2_000},
        _bearer(host, "device-a", "token-a"),
    )
    assert lower.json()["applied"] is False
    assert lower.json()["item"]["audio_position_sec"] == 10.0

    higher = _progress(
        host,
        bundle.item.id,
        {"position_sec": 30.0, "client_updated_at": 2_000},
        _bearer(host, "device-c", "token-c"),
    )
    assert higher.json()["applied"] is True
    assert higher.json()["item"]["audio_position_sec"] == 30.0


def test_audio_and_book_progress_are_independent(host):
    bundle = _with_book(host, "Independent")
    host.login()
    audio = _progress(
        host,
        bundle.item.id,
        {"position_sec": 5.0, "client_updated_at": 5_000},
    )
    assert audio.json()["applied"] is True

    book = _progress(
        host,
        bundle.item.id,
        {
            "book_locator": {"chapter_index": 1, "paragraph_index": 0, "scroll_ratio": 0.0},
            "client_updated_at": 1_000,
        },
    )
    assert book.json()["applied"] is True
    assert book.json()["item"]["audio_position_sec"] == 5.0
    assert json.loads(book.json()["item"]["book_locator"])["chapter_index"] == 1

    stale_audio = _progress(
        host,
        bundle.item.id,
        {"position_sec": 1.0, "client_updated_at": 4_000},
    )
    assert stale_audio.json()["applied"] is False
    assert stale_audio.json()["item"]["audio_position_sec"] == 5.0
    assert json.loads(stale_audio.json()["item"]["book_locator"])["chapter_index"] == 1


def test_progress_records_only_state_sequence(host):
    bundle = seed_item(host, title="State only", duration=100.0)
    host.login()
    before = _item(host, bundle.item.id)
    _progress(
        host,
        bundle.item.id,
        {"position_sec": 10.0, "client_updated_at": 1_000},
    )
    after = _item(host, bundle.item.id)
    assert after.version == before.version
    assert after.content_seq == before.content_seq
    assert after.state_seq > before.state_seq


def test_tags_are_replaced_normalized_and_clocked(host):
    bundle = seed_item(host, title="Tags", with_audio=False, run_state=None)
    host.login()
    before_content = _item(host, bundle.item.id).content_seq
    response = _tags(
        host,
        bundle.item.id,
        {"tags": ["  Memory ", "memory", "AI"], "client_updated_at": 1_000},
    )
    assert response.status_code == 200, response.text
    assert response.json()["applied"] is True
    assert response.json()["item"]["tags"] == ["AI", "Memory"]
    assert response.json()["field_clocks"]["tags"]["client_updated_at"] == 1_000
    after_write = _item(host, bundle.item.id)
    assert after_write.content_seq > before_content

    stale = _tags(
        host,
        bundle.item.id,
        {"tags": ["Stale"], "client_updated_at": 999},
    )
    assert stale.json()["applied"] is False
    assert stale.json()["item"]["tags"] == ["AI", "Memory"]
    assert _item(host, bundle.item.id).content_seq == after_write.content_seq

    newer = _tags(
        host,
        bundle.item.id,
        {"tags": ["New"], "client_updated_at": 1_001},
    )
    assert newer.json()["applied"] is True
    assert newer.json()["item"]["tags"] == ["New"]
    assert _item(host, bundle.item.id).content_seq > after_write.content_seq


def test_clock_skew_is_normalized_and_reported(host):
    bundle = seed_item(host, title="Skew", duration=100.0)
    host.login()
    future = utc_ms() + 10 * 60 * 1000
    response = _progress(
        host,
        bundle.item.id,
        {"position_sec": 10.0, "client_updated_at": future},
    )
    payload = response.json()
    assert payload["applied"] is True
    assert payload["warnings"] == ["sync.clock_skew"]
    stored = payload["field_clocks"]["audio_progress"]["client_updated_at"]
    assert stored < future
    assert stored <= utc_ms()


def test_idempotency_key_replays_first_response_without_side_effects(host):
    bundle = seed_item(host, title="Idempotent", duration=100.0)
    host.login()
    headers = {"idempotency-key": "mutation-1"}
    first = _progress(
        host,
        bundle.item.id,
        {"position_sec": 10.0, "client_updated_at": 1_000},
        headers,
    )
    assert first.status_code == 200
    state_seq = _item(host, bundle.item.id).state_seq

    replay = _progress(
        host,
        bundle.item.id,
        {"position_sec": 90.0, "client_updated_at": 9_000},
        headers,
    )
    assert replay.status_code == 200
    assert replay.json() == first.json()
    assert _item(host, bundle.item.id).state_seq == state_seq
    assert _item(host, bundle.item.id).audio_position_sec == 10.0

    with host.runtime.sessions() as session:
        rows = session.execute(select(SyncMutation)).scalars().all()
        assert len(rows) == 1
        assert rows[0].mutation_id == "mutation-1"


def test_bearer_tag_writes_are_attributed_to_the_device(host):
    bundle = seed_item(host, title="Bearer tags", with_audio=False, run_state=None)
    headers = _bearer(host, "device-b", "token-b")
    response = host.client.patch(
        f"/api/items/{bundle.item.id}", json={"tags": ["Device Tag"]}, headers=headers
    )
    assert response.status_code == 200, response.text
    assert _clocks(host, bundle.item.id)["tags"].device_id == "device-b"

    added = host.client.post(
        f"/api/items/{bundle.item.id}/tags",
        json={"tag": "Second"},
        headers=headers,
    )
    assert added.status_code == 200
    assert _clocks(host, bundle.item.id)["tags"].device_id == "device-b"


def test_web_writes_participate_in_lww(host):
    bundle = seed_item(host, title="Web LWW", duration=100.0)
    host.login()
    response = host.client.post(
        f"/items/{bundle.item.id}/state", data={"state": "finished"}
    )
    assert response.status_code == 303
    clocks = _clocks(host, bundle.item.id)
    assert clocks["consumption_state"].device_id == "host-web"

    web_clock = clocks["consumption_state"].client_updated_at
    older = _progress(
        host,
        bundle.item.id,
        {
            "position_sec": 10.0,
            "consumption_state": "unstarted",
            "client_updated_at": web_clock - 1,
        },
        _bearer(host, "device-old", "token-old"),
    )
    assert older.json()["applied"] is False
    assert older.json()["item"]["consumption_state"] == "finished"


def test_invalid_book_chapter_is_rejected(host):
    bundle = _with_book(host, "Bad chapter")
    host.login()
    response = _progress(
        host,
        bundle.item.id,
        {
            "book_locator": {"chapter_index": 99, "paragraph_index": 0, "scroll_ratio": 0.0},
            "client_updated_at": 1_000,
        },
    )
    assert response.status_code == 422
    assert response.json()["details"]["code"] == "book.chapter_not_found"


def test_device_token_write_requires_no_csrf(host):
    bundle = seed_item(host, title="Bearer write", duration=100.0)
    headers = _bearer(
        host, "device-1", "token-1", **{"sec-fetch-site": "cross-site"}
    )
    response = _progress(
        host,
        bundle.item.id,
        {"position_sec": 10.0, "client_updated_at": 1_000},
        headers,
    )
    assert response.status_code == 200
    assert response.json()["applied"] is True


def test_password_login_still_has_access(api_host):
    response = api_host.client.post(
        "/api/auth/device-token", json={"password": PASSWORD, "name": "Pixel"}
    )
    assert response.status_code == 201
