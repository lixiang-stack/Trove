from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from trove.adapters.asr import PUNC_MODEL, VAD_MODEL


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run FunASR Paraformer in a child process")
    parser.add_argument("audio")
    parser.add_argument("output")
    parser.add_argument("model")
    args = parser.parse_args(argv)

    # Load FunASR only in the worker process, not when this module is imported.
    from funasr import AutoModel

    model = AutoModel(
        model=args.model,
        vad_model=VAD_MODEL,
        punc_model=PUNC_MODEL,
        device="cpu",
        disable_update=True,
        disable_pbar=True,
        disable_log=True,
        log_level="ERROR",
    )
    outputs = model.generate(
        input=args.audio,
        batch_size_s=300,
        sentence_timestamp=True,
    )
    result: dict[str, Any] = outputs[0] if outputs else {}
    segments = [
        {
            "start": float(sentence.get("start") or 0) / 1000,
            "end": float(sentence.get("end") or 0) / 1000,
            "text": str(sentence.get("text") or "").strip(),
        }
        for sentence in result.get("sentence_info") or []
        if str(sentence.get("text") or "").strip()
    ]
    if not segments:
        text = str(result.get("text") or "").strip()
        if text:
            segments = [{"start": 0.0, "end": 0.0, "text": text}]
    payload = {
        "segments": segments,
    }
    Path(args.output).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
