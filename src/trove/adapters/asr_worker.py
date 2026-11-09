from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run mlx-whisper in a child process")
    parser.add_argument("audio")
    parser.add_argument("output")
    parser.add_argument("model")
    args = parser.parse_args(argv)

    import mlx_whisper

    result: dict[str, Any] = mlx_whisper.transcribe(
        args.audio,
        path_or_hf_repo=args.model,
        language=None,
        task="transcribe",
        word_timestamps=False,
        condition_on_previous_text=False,
        no_speech_threshold=0.6,
        logprob_threshold=-1.0,
        compression_ratio_threshold=2.4,
        verbose=False,
    )
    payload = {
        "language": result.get("language"),
        "segments": [
            {
                "start": segment.get("start"),
                "end": segment.get("end"),
                "text": segment.get("text"),
            }
            for segment in result.get("segments") or []
        ],
    }
    Path(args.output).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
