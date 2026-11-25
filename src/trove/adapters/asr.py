from __future__ import annotations

import atexit
import importlib.util
import json
import multiprocessing
import shutil
import threading
import time
import uuid
from multiprocessing.connection import Connection
from multiprocessing.process import BaseProcess
from pathlib import Path
from typing import Any

from trove.adapters.asr_server import serve
from trove.adapters.process import run_command
from trove.config import DEFAULT_ASR_MODEL
from trove.domain.items import ASR_MODEL_MISSING_HINT, ASR_NOT_INSTALLED_HINT
from trove.errors import ProcessingCancelled, ProcessingError
from trove.ports import StageContext, TranscriptResult, TranscriptSegmentData

SAMPLE_RATE = 16000
TRANSCRIBE_TIMEOUT_SECONDS = 4 * 3600
MODEL_READY_TIMEOUT_SECONDS = 5 * 60
ASR_IDLE_SECONDS = 10 * 60
POLL_SECONDS = 0.1
VAD_MODEL = "iic/speech_fsmn_vad_zh-cn-16k-common-pytorch"
PUNC_MODEL = "iic/punc_ct-transformer_zh-cn-common-vocab272727-pytorch"
MODEL_ALIASES = {
    "paraformer-zh": "iic/speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch"
}


class ParaformerTranscriber:
    """Local ASR adapter; keep the heavy model warm in a child process."""

    def __init__(self, model: str = DEFAULT_ASR_MODEL, *, ffmpeg: str = "ffmpeg") -> None:
        self.model = model
        self.ffmpeg = ffmpeg
        self._lock = threading.Lock()
        self._process: BaseProcess | None = None
        self._connection: Connection | None = None
        self._idle_timer: threading.Timer | None = None
        self._last_used = 0.0
        atexit.register(self.close)

    def transcribe(self, audio_path: Path, context: StageContext) -> TranscriptResult:
        if not funasr_installed():
            raise ProcessingError("asr.not_configured", ASR_NOT_INSTALLED_HINT)
        model_paths = cached_model_paths(self.model)
        if model_paths is None:
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
            with self._lock:
                self._ensure_server(model_paths, context)
                self._request(prepared, output, context)
            try:
                payload = json.loads(output.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ProcessingError("asr.failed", "Could not read transcription result") from exc
            return transcript_from_payload(payload, model=self.model)
        finally:
            prepared.unlink(missing_ok=True)
            output.unlink(missing_ok=True)

    def close(self) -> None:
        with self._lock:
            self._stop_server()

    def _ensure_server(
        self, model_paths: tuple[Path, Path, Path], context: StageContext
    ) -> None:
        if (
            self._process is not None
            and self._process.is_alive()
            and self._connection is not None
        ):
            self._cancel_idle()
            return
        self._stop_server()
        child_context = multiprocessing.get_context("spawn")
        parent_connection, child_connection = child_context.Pipe(duplex=True)
        process = child_context.Process(
            target=serve,
            args=(
                child_connection,
                str(model_paths[0]),
                str(model_paths[1]),
                str(model_paths[2]),
            ),
            daemon=True,
        )
        try:
            process.start()
        except OSError as exc:
            parent_connection.close()
            child_connection.close()
            raise ProcessingError("asr.failed", "Could not start ASR process") from exc
        child_connection.close()
        self._process = process
        self._connection = parent_connection
        self._wait_until_ready(context)

    def _wait_until_ready(self, context: StageContext) -> None:
        connection = self._connection
        process = self._process
        assert connection is not None and process is not None
        deadline = time.monotonic() + MODEL_READY_TIMEOUT_SECONDS
        while True:
            if context.should_cancel():
                self._stop_server()
                raise ProcessingCancelled("cancelled")
            try:
                has_message = connection.poll(POLL_SECONDS)
            except (EOFError, OSError) as exc:
                self._stop_server()
                raise ProcessingError("asr.failed", "ASR process is not available") from exc
            if has_message:
                try:
                    message = connection.recv()
                except EOFError:
                    message = None
                break
            if not process.is_alive():
                self._stop_server()
                raise ProcessingError("asr.failed", "ASR process exited during model load")
            if time.monotonic() > deadline:
                self._stop_server()
                raise ProcessingError("asr.failed", "ASR model load timed out")
        if not isinstance(message, dict) or not message.get("ready"):
            detail = message.get("traceback", "") if isinstance(message, dict) else ""
            self._stop_server()
            raise ProcessingError(
                "asr.failed",
                "ASR model failed to load",
                details={"stderr": str(detail)[-2000:]},
            )

    def _request(self, audio: Path, output: Path, context: StageContext) -> None:
        connection = self._connection
        process = self._process
        assert connection is not None and process is not None
        self._cancel_idle()
        try:
            connection.send({"audio": str(audio), "output": str(output)})
        except (BrokenPipeError, EOFError, OSError) as exc:
            self._stop_server()
            raise ProcessingError("asr.failed", "ASR process is not available") from exc

        deadline = time.monotonic() + TRANSCRIBE_TIMEOUT_SECONDS
        while True:
            if context.should_cancel():
                self._stop_server()
                raise ProcessingCancelled("cancelled")
            try:
                has_message = connection.poll(POLL_SECONDS)
            except (EOFError, OSError) as exc:
                self._stop_server()
                raise ProcessingError("asr.failed", "ASR process is not available") from exc
            if has_message:
                try:
                    response = connection.recv()
                except EOFError:
                    response = None
                break
            if not process.is_alive():
                self._stop_server()
                raise ProcessingError("asr.failed", "ASR process exited during transcription")
            if time.monotonic() > deadline:
                self._stop_server()
                raise ProcessingError("asr.failed", "Transcription timed out")
        if not isinstance(response, dict) or not response.get("ok"):
            detail = response.get("traceback", "") if isinstance(response, dict) else ""
            self._stop_server()
            raise ProcessingError(
                "asr.failed",
                "Transcription failed",
                details={"stderr": str(detail)[-2000:]},
            )
        self._last_used = time.monotonic()
        self._schedule_idle()

    def _schedule_idle(self) -> None:
        self._cancel_idle()
        timer = threading.Timer(ASR_IDLE_SECONDS, self._idle_stop)
        timer.daemon = True
        self._idle_timer = timer
        timer.start()

    def _cancel_idle(self) -> None:
        timer = self._idle_timer
        self._idle_timer = None
        if timer is not None:
            timer.cancel()

    def _idle_stop(self) -> None:
        with self._lock:
            if self._process is None:
                return
            remaining = ASR_IDLE_SECONDS - (time.monotonic() - self._last_used)
            if remaining > 0:
                self._schedule_idle()
                return
            self._stop_server()

    def _stop_server(self) -> None:
        self._cancel_idle()
        connection = self._connection
        self._connection = None
        if connection is not None:
            connection.close()
        process = self._process
        self._process = None
        if process is None:
            return
        if process.is_alive():
            process.terminate()
            process.join(timeout=3)
        if process.is_alive():
            process.kill()
            process.join(timeout=1)


def transcript_from_payload(payload: dict[str, Any], *, model: str | None) -> TranscriptResult:
    rows: list[tuple[int, int, str]] = []
    for segment in payload.get("segments") or []:
        if not isinstance(segment, dict):
            continue
        text = str(segment.get("text") or "").strip()
        if not text or not any(char.isalnum() for char in text):
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


def funasr_installed() -> bool:
    return (
        importlib.util.find_spec("funasr") is not None
        and importlib.util.find_spec("torch") is not None
    )


def resolve_model_id(model: str) -> str:
    return MODEL_ALIASES.get(model, model)


def cached_model_paths(model: str) -> tuple[Path, Path, Path] | None:
    # Optional ASR dependency; keep base installs and CLI startup free of modelscope.
    try:
        from modelscope import snapshot_download
    except ImportError:
        return None
    paths = []
    for model_id in (resolve_model_id(model), VAD_MODEL, PUNC_MODEL):
        try:
            paths.append(Path(snapshot_download(model_id, local_files_only=True)))
        except Exception:  # noqa: BLE001 - any cache miss means "not ready"
            return None
    return paths[0], paths[1], paths[2]


def model_cached(model: str) -> bool:
    return cached_model_paths(model) is not None


def download_model(model: str) -> Path:
    # Optional ASR dependency; imported only when setup downloads model weights.
    try:
        from modelscope import snapshot_download
    except ImportError as exc:
        raise RuntimeError(ASR_NOT_INSTALLED_HINT) from exc
    paths = {
        model_id: Path(snapshot_download(model_id))
        for model_id in (resolve_model_id(model), VAD_MODEL, PUNC_MODEL)
    }
    return paths[resolve_model_id(model)]


def _milliseconds(value: Any) -> int:
    try:
        return max(0, int(round(float(value) * 1000)))
    except (TypeError, ValueError):
        return 0


def _optional_string(value: Any) -> str | None:
    return str(value) if value else None
