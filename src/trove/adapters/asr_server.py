from __future__ import annotations

import json
import traceback
from multiprocessing.connection import Connection
from pathlib import Path
from typing import Any


def serve(
    connection: Connection,
    model_path: str,
    vad_path: str,
    punc_path: str,
) -> None:
    """Load FunASR once and process requests until the parent closes the pipe."""
    try:
        from funasr import AutoModel

        model = AutoModel(
            model=model_path,
            vad_model=vad_path,
            punc_model=punc_path,
            device="cpu",
            disable_update=True,
            disable_pbar=True,
            disable_log=True,
            log_level="ERROR",
        )
    except Exception as exc:  # noqa: BLE001 - report model load failures to the parent
        _send(connection, {"ready": False, "error": str(exc), "traceback": traceback.format_exc()})
        connection.close()
        return

    if not _send(connection, {"ready": True}):
        connection.close()
        return

    try:
        while True:
            try:
                request = connection.recv()
            except (EOFError, OSError):
                break
            if not isinstance(request, dict):
                break
            try:
                outputs = model.generate(
                    input=str(request["audio"]),
                    batch_size_s=300,
                    sentence_timestamp=True,
                )
                result: dict[str, Any] = outputs[0] if outputs else {}
                payload = {"segments": _segments(result)}
                Path(str(request["output"])).write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                response: dict[str, Any] = {"ok": True}
            except Exception as exc:  # noqa: BLE001 - the parent turns this into asr.failed
                response = {
                    "ok": False,
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                }
            if not _send(connection, response):
                break
            if not response["ok"]:
                break
    finally:
        connection.close()


def _segments(result: dict[str, Any]) -> list[dict[str, Any]]:
    segments = [
        {
            "start": float(sentence.get("start") or 0) / 1000,
            "end": float(sentence.get("end") or 0) / 1000,
            "text": str(sentence.get("text") or "").strip(),
        }
        for sentence in result.get("sentence_info") or []
        if str(sentence.get("text") or "").strip()
    ]
    if segments:
        return segments
    text = str(result.get("text") or "").strip()
    return [{"start": 0.0, "end": 0.0, "text": text}] if text else []


def _send(connection: Connection, payload: dict[str, Any]) -> bool:
    try:
        connection.send(payload)
        return True
    except (BrokenPipeError, EOFError, OSError):
        return False
