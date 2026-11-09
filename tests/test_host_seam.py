from __future__ import annotations

import json

import pytest

from .fakes import FIXTURES, wait_until


def test_host_seam_can_login_and_read_pages(host):
    host.login()
    assert "Library" in host.client.get("/library").text
    assert host.client.get("/api/health").status_code == 200


def test_fake_pipeline_completes_with_real_files(host):
    host.login()
    response = host.client.post(
        "/api/items", json={"kind": "url", "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}
    )
    assert response.status_code == 201, response.text
    item_id = response.json()["item"]["id"]
    payload = host.wait_for_item(item_id)
    assert payload["processing_state"] == "completed"
    run = payload["run"]
    stages = [step["stage"] for step in run["steps"] if step["state"] == "completed"]
    assert stages == [
        "downloading",
        "extracting_audio",
        "transcribing",
        "organizing",
        "indexing",
    ]
    item_dir = host.config.library_dir / item_id
    assert (item_dir / "audio.m4a").is_file()
    assert (item_dir / "transcript.json").is_file()
    assert (item_dir / "ai.json").is_file()
    assert payload["summary"] == "这是一段关于记忆与智能体的讨论。"
    assert set(payload["tags"]) == {"智能体", "记忆", "LLM"}

    audio = host.client.get(f"/api/items/{item_id}/audio")
    assert audio.status_code == 200
    assert audio.headers["content-type"].startswith("audio/")
    transcript = host.client.get(f"/api/items/{item_id}/transcript").json()
    assert len(transcript["segments"]) == 3
    assert "记忆" in transcript["segments"][0]["text"]
    # yt-dlp and the network were replaced by fakes.
    assert host.stack.downloader.calls
    assert host.stack.feed_http.urls == []


def test_epub_fixture_is_parsed(host):
    host.login()
    response = host.client.post(
        "/api/items",
        json={"kind": "path", "path": str(FIXTURES / "aesop.epub")},
    )
    assert response.status_code == 201, response.text
    item_id = response.json()["item"]["id"]
    payload = host.wait_for_item(item_id)
    assert payload["processing_state"] == "completed"
    book = json.loads(
        (host.config.library_dir / item_id / "book.json").read_text(encoding="utf-8")
    )
    assert "North Wind" in book["chapters"][0]["title"]
    assert "traveller" in book["chapters"][0]["text"]
    detail = host.client.get(f"/api/items/{item_id}").json()
    assert detail["has_book"] is True
    assert (host.config.library_dir / item_id / "book.epub").is_file()
    assert (host.config.library_dir / item_id / "book.json").is_file()


def test_ffmpeg_extracts_a_real_audio_artifact(host):
    host.login()
    response = host.client.post(
        "/api/items", json={"kind": "path", "path": str(FIXTURES / "short.wav")}
    )
    assert response.status_code == 201, response.text
    item_id = response.json()["item"]["id"]
    payload = host.wait_for_item(item_id)
    assert payload["processing_state"] == "completed"
    audio = host.config.library_dir / item_id / "audio.wav"
    assert audio.is_file()
    assert audio.stat().st_size > 1000


def test_worker_polling_timeout_has_clear_diagnostic():
    with pytest.raises(TimeoutError, match="condition not met"):
        wait_until(lambda: False, timeout=0.1)
