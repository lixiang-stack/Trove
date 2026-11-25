from __future__ import annotations

import os
import sys
import time
import types
from pathlib import Path

import pytest

from trove.adapters import asr
from trove.config import DEFAULT_ASR_MODEL
from trove.domain.items import error_label
from trove.errors import ProcessingCancelled, ProcessingError
from trove.ports import StageContext

from .fakes import FIXTURES


def _context(tmp_path: Path) -> StageContext:
    return StageContext(
        item_id="item",
        run_id="run",
        work_dir=tmp_path,
        should_cancel=lambda: False,
        log=lambda message: None,
    )


def test_missing_package_raises_install_error(tmp_path, monkeypatch):
    monkeypatch.setattr(asr, "funasr_installed", lambda: False)
    transcriber = asr.ParaformerTranscriber(DEFAULT_ASR_MODEL)

    with pytest.raises(ProcessingError) as caught:
        transcriber.transcribe(tmp_path / "audio.m4a", _context(tmp_path))

    assert caught.value.code == "asr.not_configured"
    assert "uv sync --extra asr" in caught.value.message
    assert "uv sync --extra asr" in error_label("asr.not_configured")


def test_missing_model_raises_setup_error(tmp_path, monkeypatch):
    monkeypatch.setattr(asr, "funasr_installed", lambda: True)
    monkeypatch.setattr(asr, "cached_model_paths", lambda model: None)
    transcriber = asr.ParaformerTranscriber(DEFAULT_ASR_MODEL)

    with pytest.raises(ProcessingError) as caught:
        transcriber.transcribe(tmp_path / "audio.m4a", _context(tmp_path))

    assert caught.value.code == "asr.model_missing"
    assert "trove setup" in caught.value.message
    assert "trove setup" in error_label("asr.model_missing")


def test_model_alias_resolves_to_modelscope_id():
    assert asr.resolve_model_id("paraformer-zh") == (
        "iic/speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch"
    )
    assert asr.resolve_model_id("custom/model") == "custom/model"


def test_download_model_fetches_asr_vad_and_punctuation(monkeypatch, tmp_path):
    calls = []
    module = types.ModuleType("modelscope")

    def snapshot_download(model_id, **_kwargs):
        calls.append(model_id)
        return str(tmp_path / model_id.replace("/", "--"))

    module.snapshot_download = snapshot_download
    monkeypatch.setitem(sys.modules, "modelscope", module)

    path = asr.download_model("paraformer-zh")

    assert [call.split("/")[0] for call in calls] == ["iic", "iic", "iic"]
    assert calls == [
        "iic/speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch",
        asr.VAD_MODEL,
        asr.PUNC_MODEL,
    ]
    assert path.name.endswith("vocab8404-pytorch")


def test_transcript_payload_is_ordered_and_monotonic():
    payload = {
        "language": "zh",
        "segments": [
            {"start": 4.0, "end": 3.5, "text": " 第二段 "},
            {"start": 0.0, "end": 1.2, "text": "第一段"},
            {"start": 5.0, "end": 6.0, "text": "   "},
        ],
    }

    result = asr.transcript_from_payload(payload, model="paraformer-zh")

    assert result.language == "zh"
    assert result.model == "paraformer-zh"
    rows = [
        (segment.seq, segment.start_ms, segment.end_ms, segment.text)
        for segment in result.segments
    ]
    assert rows == [
        (0, 0, 1200, "第一段"),
        (1, 4000, 4000, "第二段"),
    ]


class _FakeProcess:
    def __init__(self) -> None:
        self.alive = True
        self.terminated = False

    def is_alive(self) -> bool:
        return self.alive

    def terminate(self) -> None:
        self.terminated = True
        self.alive = False

    def join(self, timeout=None) -> None:
        return None

    def kill(self) -> None:
        self.terminated = True
        self.alive = False


class _FakeConnection:
    def __init__(self) -> None:
        self.closed = False

    def send(self, payload) -> None:
        return None

    def poll(self, timeout) -> bool:
        return False

    def recv(self):
        raise AssertionError("recv should not be called")

    def close(self) -> None:
        self.closed = True


def test_request_cancellation_stops_the_asr_process(tmp_path):
    transcriber = asr.ParaformerTranscriber()
    process = _FakeProcess()
    connection = _FakeConnection()
    transcriber._process = process
    transcriber._connection = connection
    context = _context(tmp_path)
    context.should_cancel = lambda: True

    with pytest.raises(ProcessingCancelled):
        transcriber._request(tmp_path / "audio.wav", tmp_path / "out.json", context)

    assert process.terminated
    assert connection.closed
    assert transcriber._process is None


def test_request_timeout_stops_the_asr_process(tmp_path, monkeypatch):
    monkeypatch.setattr(asr, "TRANSCRIBE_TIMEOUT_SECONDS", 0)
    transcriber = asr.ParaformerTranscriber()
    process = _FakeProcess()
    connection = _FakeConnection()
    transcriber._process = process
    transcriber._connection = connection

    with pytest.raises(ProcessingError) as caught:
        transcriber._request(tmp_path / "audio.wav", tmp_path / "out.json", _context(tmp_path))

    assert caught.value.message == "Transcription timed out"
    assert process.terminated
    assert transcriber._process is None


def test_idle_timeout_stops_the_asr_process():
    transcriber = asr.ParaformerTranscriber()
    process = _FakeProcess()
    connection = _FakeConnection()
    transcriber._process = process
    transcriber._connection = connection
    transcriber._last_used = time.monotonic() - asr.ASR_IDLE_SECONDS - 1

    transcriber._idle_stop()

    assert process.terminated
    assert connection.closed
    assert transcriber._process is None


@pytest.mark.slow
def test_real_funasr_transcribes_fixture(tmp_path):
    if not os.environ.get("TROVE_RUN_SLOW_ASR"):
        pytest.skip("set TROVE_RUN_SLOW_ASR=1 to run the real model")
    if not asr.funasr_installed():
        pytest.skip("run `uv sync --extra asr` before the slow ASR test")
    if not asr.model_cached(DEFAULT_ASR_MODEL):
        pytest.skip("run `uv run trove setup` before the slow ASR test")

    transcriber = asr.ParaformerTranscriber()
    try:
        first = transcriber.transcribe(FIXTURES / "short.m4a", _context(tmp_path))
        server = transcriber._process
        assert server is not None
        server_pid = server.pid
        # The second call must reuse the warm ASR process.
        second = transcriber.transcribe(FIXTURES / "short.m4a", _context(tmp_path))
        assert transcriber._process is server
        assert transcriber._process.pid == server_pid
    finally:
        transcriber.close()

    assert first.model == DEFAULT_ASR_MODEL
    assert second.model == DEFAULT_ASR_MODEL
