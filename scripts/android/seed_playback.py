#!/usr/bin/env python3
"""Create a long silent audio Item in a TROVE_HOME for playback acceptance."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "android"))

from seed_acceptance import add_item
from trove.composition import build_runtime
from trove.config import load_config


def generate_audio(path: Path, seconds: int) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise SystemExit("ffmpeg is required to generate the playback fixture")
    subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=44100:cl=mono",
            "-t",
            str(seconds),
            "-c:a",
            "aac",
            "-b:a",
            "32k",
            str(path),
        ],
        check=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=int, default=3600)
    parser.add_argument("--home", type=Path)
    parser.add_argument("--title")
    args = parser.parse_args()
    if args.seconds < 1:
        parser.error("--seconds must be positive")

    home = args.home
    if home is None:
        env_home = os.environ.get("TROVE_HOME")
        if not env_home:
            raise SystemExit("set TROVE_HOME or pass --home")
        home = Path(env_home)
    home = home.expanduser().resolve()
    os.environ["TROVE_HOME"] = str(home)
    config = load_config()
    config.ensure_layout()
    audio = home / f"playback-{args.seconds}s.m4a"
    if not audio.is_file():
        generate_audio(audio, args.seconds)
    runtime = build_runtime(config)
    title = args.title or f"后台播放验收 {args.seconds}s"
    item_id = add_item(
        runtime,
        config,
        title=title,
        source_key=f"acceptance:playback:{args.seconds}:{title}",
        audio=audio,
        tags=["验收"],
        with_transcript=False,
        duration=float(args.seconds),
    )
    print(item_id)
    print(title)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
