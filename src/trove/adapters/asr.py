from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import uuid
from pathlib import Path
from typing import Any

from trove.adapters.process import run_command
from trove.config import DEFAULT_ASR_MODEL
from trove.domain.items import ASR_MODEL_MISSING_HINT, ASR_NOT_INSTALLED_HINT
from trove.errors import ProcessingError
from trove.ports import StageContext, TranscriptResult, TranscriptSegmentData

SAMPLE_RATE = 16000
TRANSCRIBE_TIMEOUT_SECONDS = 4 * 3600


class MlxWhisperTranscriber:
    """Local ASR adapter; keep the heavy model work in a child process."""

    def __init__(self, model: str = DEFAULT_ASR_MODEL, *, ffmpeg: str = "ffmpeg") -> None:
        self.model = model
        self.ffmpeg = ffmpeg

    def transcribe(self, audio_path: Path, context: StageContext) -> TranscriptResult:
        if not mlx_installed():
            raise ProcessingError("asr.not_configured", ASR_NOT_INSTALLED_HINT)
        if not model_cached(self.model):
            raise ProcessingError("asr.model_missing", ASR_MODEL_MISSING_HINT)
        if shutil.which(self.ffmpeg) is None:
            raise ProcessingError("ffmpeg.missing", "FFmpeg is missing; install it first")
        if not audio_path.is_file():
            raise ProcessingError("asr.failed", "Audio file does not exist; cannot transcribe")

        token = uuid.uuid4().hex
        prepared = context.work_dir / f".asr-{token}.wav"
        output = context.work_dir / f".asr-{token}.json"
        try:
            converted = run_command(
                context,
                [
                    self.ffmpeg,
                    "-nostdin",
                    "-y",
                    "-i",
                    str(audio_path),
                    "-vn",
                    "-ac",
                    "1",
                    "-ar",
                    str(SAMPLE_RATE),
                    str(prepared),
                ],
                timeout=3600,
                error_code="asr.failed",
            )
            if converted.returncode != 0 or not prepared.is_file():
                raise ProcessingError(
                    "asr.failed",
                    "Audio transcoding failed",
                    details={"stderr": converted.stderr[-2000:]},
                )
            result = run_command(
                context,
                [
                    sys.executable,
                    "-m",
                    "trove.adapters.asr_worker",
                    str(prepared),
                    str(output),
                    self.model,
                ],
                timeout=TRANSCRIBE_TIMEOUT_SECONDS,
                error_code="asr.failed",
            )
            if result.returncode != 0 or not output.is_file():
                detail = (result.stderr or result.stdout)[-2000:].lower()
                if "localentrynotfound" in detail or "could not locate" in detail:
                    raise ProcessingError("asr.model_missing", ASR_MODEL_MISSING_HINT)
                raise ProcessingError(
                    "asr.failed",
                    "Transcription failed",
                    details={"stderr": (result.stderr or result.stdout)[-2000:]},
                )
            try:
                payload = json.loads(output.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ProcessingError("asr.failed", "Could not read transcription result") from exc
            return transcript_from_payload(payload, model=self.model)
        finally:
            prepared.unlink(missing_ok=True)
            output.unlink(missing_ok=True)


def transcript_from_payload(payload: dict[str, Any], *, model: str | None) -> TranscriptResult:
    rows: list[tuple[int, int, str]] = []
    for segment in payload.get("segments") or []:
        if not isinstance(segment, dict):
            continue
        text = str(segment.get("text") or "").strip()
        if not text:
            continue
        start_ms = _milliseconds(segment.get("start"))
        end_ms = max(start_ms, _milliseconds(segment.get("end")))
        rows.append((start_ms, end_ms, text))
    rows.sort(key=lambda row: row[0])
    return TranscriptResult(
        segments=[
            TranscriptSegmentData(seq=index, start_ms=start, end_ms=end, text=text)
            for index, (start, end, text) in enumerate(rows)
        ],
        language=_optional_string(payload.get("language")),
        model=model,
    )


def mlx_installed() -> bool:
    return importlib.util.find_spec("mlx_whisper") is not None


def model_cached(model: str) -> bool:
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        return False
    try:
        snapshot_download(model, local_files_only=True)
        return True
    except Exception:  # noqa: BLE001 - any cache miss or local metadata error means "not ready"
        return False


def download_model(model: str) -> Path:
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise RuntimeError(ASR_NOT_INSTALLED_HINT) from exc
    return Path(snapshot_download(model))


def _milliseconds(value: Any) -> int:
    try:
        return max(0, int(round(float(value) * 1000)))
    except (TypeError, ValueError):
        return 0


def _optional_string(value: Any) -> str | None:
    return str(value) if value else None
