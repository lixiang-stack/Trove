from __future__ import annotations

import subprocess
import sys

import pytest

pytestmark = pytest.mark.network


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://www.bilibili.com/video/BV1GJ411x7h7",
    ],
)
def test_real_platform_metadata_is_reachable(url):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "yt_dlp",
            "--no-playlist",
            "--simulate",
            "--print",
            "%(title)s",
            url,
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    assert result.stdout.strip()
