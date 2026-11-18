from __future__ import annotations

import json

from trove.adapters import video_inspect
from trove.adapters.video_inspect import YtDlpVideoInspector
from trove.config import Config

from .fakes import FIXTURES


def test_parse_real_youtube_playlist_fixture():
    data = json.loads(
        (FIXTURES / "yt_dlp_youtube_playlist.json").read_text(encoding="utf-8")
    )
    info = video_inspect._parse_info(data)
    assert info.is_playlist is True
    assert info.title == "Opera Gems in the Public Domain"
    assert len(info.entries) == 3
    assert all(
        entry.url.startswith("https://www.youtube.com/watch?v=")
        for entry in info.entries
    )
    assert all(entry.title and entry.duration_sec for entry in info.entries)


def test_parse_real_bilibili_multipart_fixture():
    data = json.loads(
        (FIXTURES / "yt_dlp_bilibili_multipart.json").read_text(encoding="utf-8")
    )
    info = video_inspect._parse_info(data)
    assert info.is_playlist is True
    assert info.title and "FFmpeg" in info.title
    assert [entry.url for entry in info.entries] == [
        "https://www.bilibili.com/video/BV1Ft411s7Xa?p=1",
        "https://www.bilibili.com/video/BV1Ft411s7Xa?p=2",
        "https://www.bilibili.com/video/BV1Ft411s7Xa?p=3",
    ]
    assert [entry.title for entry in info.entries] == [
        "Episode 1",
        "Episode 2",
        "Episode 3",
    ]
    assert all(entry.duration_sec is None for entry in info.entries)


def _completed(payload: dict, returncode: int = 0, stderr: str = ""):
    return video_inspect.subprocess.CompletedProcess(
        args=[],
        returncode=returncode,
        stdout=json.dumps(payload),
        stderr=stderr,
    )


def test_parse_youtube_playlist_and_bilibili_entries():
    info = video_inspect._parse_info(
        {
            "_type": "playlist",
            "title": "Fixture playlist",
            "uploader": "Fixture Channel",
            "entries": [
                {"id": "episode0001", "ie_key": "Youtube", "title": "One", "duration": 30},
                {
                    "webpage_url": "https://www.bilibili.com/video/BV1xx411c7mD?p=2",
                    "title": "Two",
                    "duration": 40,
                },
            ],
        }
    )
    assert info.is_playlist is True
    assert info.title == "Fixture playlist"
    assert info.author == "Fixture Channel"
    assert [entry.url for entry in info.entries] == [
        "https://www.youtube.com/watch?v=episode0001",
        "https://www.bilibili.com/video/BV1xx411c7mD?p=2",
    ]
    assert [entry.index for entry in info.entries] == [1, 2]


def test_inspector_uses_no_playlist_for_single_and_caps_playlist(monkeypatch, tmp_path):
    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return _completed(
            {"_type": "video", "title": "Single", "uploader": "A", "duration": 12}
        )

    monkeypatch.setattr(video_inspect.subprocess, "run", fake_run)
    config = Config(home=tmp_path)
    inspector = YtDlpVideoInspector(config)
    single = inspector.inspect("https://www.youtube.com/watch?v=dQw4w9WgXcQ", playlist=False)
    assert single.is_playlist is False
    assert "--no-playlist" in calls[0]
    assert "--playlist-end" in calls[0]

    inspector.inspect("https://www.youtube.com/playlist?list=PL1234567890", playlist=True)
    assert "--no-playlist" not in calls[1]
    assert calls[1][calls[1].index("--playlist-end") + 1] == str(
        config.max_collection_items + 1
    )


def test_inspector_classifies_common_errors(monkeypatch, tmp_path):
    def fake_run(command, **kwargs):
        return _completed({}, returncode=1, stderr="ERROR: Sign in to confirm your age")

    monkeypatch.setattr(video_inspect.subprocess, "run", fake_run)
    inspector = YtDlpVideoInspector(Config(home=tmp_path))
    try:
        inspector.inspect("https://www.youtube.com/watch?v=dQw4w9WgXcQ", playlist=False)
    except Exception as exc:  # ProcessingError
        assert getattr(exc, "code", None) == "download.login_required"
    else:
        raise AssertionError("expected an inspection error")
