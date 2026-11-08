from __future__ import annotations

from sqlalchemy import select

from trove.db.models import Artifact, TranscriptSegment

from .conftest import seed_item


def test_audio_range_etag_and_full_response(host):
    bundle = seed_item(host, title="Audio item")
    host.login()
    full = host.client.get(f"/api/items/{bundle.item.id}/audio")
    assert full.status_code == 200
    assert full.headers["accept-ranges"] == "bytes"
    assert full.headers["cache-control"] == "private"
    assert full.headers["x-content-type-options"] == "nosniff"
    assert full.headers["etag"].startswith('"')
    body = full.content
    partial = host.client.get(
        f"/api/items/{bundle.item.id}/audio", headers={"Range": "bytes=0-99"}
    )
    assert partial.status_code == 206
    assert len(partial.content) == 100
    assert partial.content == body[:100]
    assert partial.headers["content-range"] == f"bytes 0-99/{len(body)}"
    assert partial.headers["etag"] == full.headers["etag"]


def test_audio_missing_and_path_traversal(host):
    bundle = seed_item(host, title="Path traversal", with_audio=False)
    host.login()
    assert host.client.get(f"/api/items/{bundle.item.id}/audio").status_code == 404
    target = seed_item(host, title="Tampered", source_key="seed:tampered")
    with host.runtime.sessions() as session:
        artifact = session.execute(
            select(Artifact).where(
                Artifact.item_id == target.item.id, Artifact.kind == "audio"
            )
        ).scalars().first()
        artifact.path = "../../../etc/passwd"
        session.commit()
    response = host.client.get(f"/api/items/{target.item.id}/audio")
    assert response.status_code == 404


def test_progress_is_saved_and_restored(host):
    bundle = seed_item(host, title="Progress", duration=100.0)
    host.login()
    for position, expected in ((0.5, "unstarted"), (5.0, "in_progress"), (95.0, "finished")):
        response = host.client.put(
            f"/api/items/{bundle.item.id}/progress", json={"position_sec": position}
        )
        assert response.status_code == 200, response.text
        payload = response.json()["item"]
        assert payload["audio_position_sec"] == position
        assert payload["consumption_state"] == expected
    detail = host.client.get(f"/api/items/{bundle.item.id}").json()
    assert detail["audio_position_sec"] == 95.0
    assert detail["consumption_state"] == "finished"


def test_manual_consumption_state_overrides_automatic(host):
    bundle = seed_item(host, title="Manual", duration=100.0)
    host.login()
    response = host.client.put(
        f"/api/items/{bundle.item.id}/progress",
        json={"position_sec": 3.0, "consumption_state": "finished"},
    )
    assert response.status_code == 200
    assert response.json()["item"]["consumption_state"] == "finished"
    response = host.client.post(
        f"/items/{bundle.item.id}/state", data={"state": "unstarted"}
    )
    assert response.status_code == 303
    payload = host.client.get(f"/api/items/{bundle.item.id}").json()
    assert payload["consumption_state"] == "unstarted"


def test_invalid_progress_is_rejected(host):
    bundle = seed_item(host, title="Invalid progress")
    host.login()
    response = host.client.put(
        f"/api/items/{bundle.item.id}/progress", json={"position_sec": -1}
    )
    assert response.status_code == 422
    response = host.client.put(
        f"/api/items/{bundle.item.id}/progress",
        json={"position_sec": 1, "consumption_state": "nonsense"},
    )
    assert response.status_code == 422
    assert response.json()["details"]["code"] == "progress.invalid_state"


def test_transcript_and_listen_page(host):
    bundle = seed_item(host, title="Transcript item")
    with host.runtime.sessions() as session:
        session.add_all(
            [
                TranscriptSegment(
                    item_id=bundle.item.id,
                    seq=0,
                    start_ms=0,
                    end_ms=1000,
                    text="第一段关于记忆的内容。",
                ),
                TranscriptSegment(
                    item_id=bundle.item.id,
                    seq=1,
                    start_ms=1000,
                    end_ms=2000,
                    text="第二段继续讨论智能体。",
                ),
            ]
        )
        session.commit()
    host.login()
    payload = host.client.get(f"/api/items/{bundle.item.id}/transcript").json()
    assert len(payload["segments"]) == 2
    assert payload["segments"][0]["text"].startswith("第一段")
    page = host.client.get(f"/items/{bundle.item.id}/listen")
    assert page.status_code == 200
    assert "第一段关于记忆的内容" in page.text
    assert "<details class=\"now-transcript\"" in page.text
    assert "<script type=\"application/json\" data-player-item>" in page.text


def test_listen_page_audio_url_and_media_session_payload(host):
    bundle = seed_item(host, title="Media Session", author="作者")
    host.login()
    page = host.client.get(f"/items/{bundle.item.id}/listen").text
    assert f"/api/items/{bundle.item.id}/audio" in page
    assert 'data-player-action="toggle"' in page
    assert 'data-player-action="speed"' in page
