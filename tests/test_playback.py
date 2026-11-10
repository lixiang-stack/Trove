from __future__ import annotations

import json

from sqlalchemy import select

from trove.content_package import sha256_file
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
    assert 'data-transcript-search' in page.text
    assert 'id="segment-0"' in page.text
    assert 'id="segment-1"' in page.text
    assert "<script type=\"application/json\" data-player-item>" in page.text


def test_batch_replace_updates_segments_package_artifact_and_search(host):
    bundle = seed_item(host, title="批量替换")
    with host.runtime.sessions() as session:
        session.add_all(
            [
                TranscriptSegment(
                    item_id=bundle.item.id,
                    seq=0,
                    start_ms=0,
                    end_ms=1000,
                    text="智能体需要记忆。",
                ),
                TranscriptSegment(
                    item_id=bundle.item.id,
                    seq=1,
                    start_ms=1000,
                    end_ms=2000,
                    text="智能体也需要遗忘。",
                ),
                TranscriptSegment(
                    item_id=bundle.item.id,
                    seq=2,
                    start_ms=2000,
                    end_ms=3000,
                    text="这段保持不变。",
                ),
            ]
        )
        session.commit()
    package_path = host.runtime.package.write_json(
        bundle.item.id,
        "transcript.json",
        {
            "language": "zh",
            "model": "fake-whisper",
            "segments": [
                {"seq": 0, "start_ms": 0, "end_ms": 1000, "text": "智能体需要记忆。"},
                {"seq": 1, "start_ms": 1000, "end_ms": 2000, "text": "智能体也需要遗忘。"},
                {"seq": 2, "start_ms": 2000, "end_ms": 3000, "text": "这段保持不变。"},
            ],
        },
    )
    old_sha = sha256_file(package_path)
    with host.runtime.sessions() as session:
        session.add(
            Artifact(
                item_id=bundle.item.id,
                kind="transcript",
                path="transcript.json",
                sha256=old_sha,
                size=package_path.stat().st_size,
                mime="application/json",
                duration_sec=None,
            )
        )
        session.commit()
    host.runtime.search_index.index_item(bundle.item.id)
    host.login()

    response = host.client.post(
        f"/items/{bundle.item.id}/transcript/replace",
        data={"old": "智能体", "new": "智能代理"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    location = response.headers["location"]
    assert "replace=2" in location
    transcript = host.client.get(f"/api/items/{bundle.item.id}/transcript").json()
    assert [segment["text"] for segment in transcript["segments"]] == [
        "智能代理需要记忆。",
        "智能代理也需要遗忘。",
        "这段保持不变。",
    ]
    package = json.loads(package_path.read_text(encoding="utf-8"))
    assert package["language"] == "zh"
    assert package["model"] == "fake-whisper"
    assert package["segments"][0]["text"] == "智能代理需要记忆。"
    with host.runtime.sessions() as session:
        artifact = session.execute(
            select(Artifact).where(
                Artifact.item_id == bundle.item.id, Artifact.kind == "transcript"
            )
        ).scalars().first()
        assert artifact is not None
        assert artifact.sha256 != old_sha
        assert artifact.size == package_path.stat().st_size
    assert host.client.get("/api/search", params={"q": "智能体"}).json()["count"] == 0
    assert host.client.get("/api/search", params={"q": "智能代理"}).json()["count"] == 1
    page = host.client.get(location)
    assert "已更新 2 个分段" in page.text


def test_batch_replace_rejects_empty_keyword_and_reports_no_match(host):
    bundle = seed_item(host, title="替换边界")
    with host.runtime.sessions() as session:
        session.add(
            TranscriptSegment(
                item_id=bundle.item.id,
                seq=0,
                start_ms=0,
                end_ms=1000,
                text="一段转写。",
            )
        )
        session.commit()
    host.login()

    empty = host.client.post(
        f"/items/{bundle.item.id}/transcript/replace",
        data={"old": "   ", "new": "x"},
    )
    missing = host.client.post(
        f"/items/{bundle.item.id}/transcript/replace",
        data={"old": "不存在", "new": "x"},
        follow_redirects=False,
    )

    assert empty.status_code == 422
    assert "Search keyword cannot be empty" in empty.text
    assert missing.status_code == 303
    assert "replace=0" in missing.headers["location"]
    page = host.client.get(missing.headers["location"])
    assert "没有找到" in page.text


def test_listen_page_audio_url_and_media_session_payload(host):
    bundle = seed_item(host, title="Media Session", author="作者")
    host.login()
    page = host.client.get(f"/items/{bundle.item.id}/listen").text
    assert f"/api/items/{bundle.item.id}/audio" in page
    assert 'data-player-action="toggle"' in page
    assert 'data-player-action="speed"' in page


def test_invalid_html_consumption_state_is_rejected(host):
    bundle = seed_item(host, title="Invalid state route")
    host.login()
    response = host.client.post(
        f"/items/{bundle.item.id}/state", data={"state": "nonsense"}
    )
    assert response.status_code == 422
    assert "progress.invalid_state" in response.text
