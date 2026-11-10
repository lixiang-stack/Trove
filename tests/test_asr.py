from __future__ import annotations

import os
from pathlib import Path

import pytest

from trove.adapters import asr
from trove.config import DEFAULT_ASR_MODEL
from trove.domain.items import error_label
from trove.errors import ProcessingError
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
    monkeypatch.setattr(asr, "mlx_installed", lambda: False)
    transcriber = asr.MlxWhisperTranscriber("mlx-community/whisper-large-v3-turbo")

    with pytest.raises(ProcessingError) as caught:
        transcriber.transcribe(tmp_path / "audio.m4a", _context(tmp_path))

    assert caught.value.code == "asr.not_configured"
    assert "uv sync --extra asr" in caught.value.message
    assert "uv sync --extra asr" in error_label("asr.not_configured")


def test_missing_model_raises_setup_error(tmp_path, monkeypatch):
    monkeypatch.setattr(asr, "mlx_installed", lambda: True)
    monkeypatch.setattr(asr, "model_cached", lambda model: False)
    transcriber = asr.MlxWhisperTranscriber("mlx-community/whisper-large-v3-turbo")

    with pytest.raises(ProcessingError) as caught:
        transcriber.transcribe(tmp_path / "audio.m4a", _context(tmp_path))

    assert caught.value.code == "asr.model_missing"
    assert "trove setup" in caught.value.message
    assert "trove setup" in error_label("asr.model_missing")


def test_transcript_payload_is_ordered_and_monotonic():
    payload = {
        "language": "zh",
        "segments": [
            {"start": 4.0, "end": 3.5, "text": " 第二段 "},
            {"start": 0.0, "end": 1.2, "text": "第一段"},
            {"start": 5.0, "end": 6.0, "text": "   "},
        ],
    }

    result = asr.transcript_from_payload(payload, model="whisper-large-v3-turbo")

    assert result.language == "zh"
    assert result.model == "whisper-large-v3-turbo"
    rows = [
        (segment.seq, segment.start_ms, segment.end_ms, segment.text)
        for segment in result.segments
    ]
    assert rows == [
        (0, 0, 1200, "第一段"),
        (1, 4000, 4000, "第二段"),
    ]


@pytest.mark.slow
def test_real_mlx_whisper_transcribes_fixture(tmp_path):
    if not os.environ.get("TROVE_RUN_SLOW_ASR"):
        pytest.skip("set TROVE_RUN_SLOW_ASR=1 to run the real model")
    if not asr.mlx_installed():
        pytest.skip("run `uv sync --extra asr` before the slow ASR test")
    if not asr.model_cached(DEFAULT_ASR_MODEL):
        pytest.skip("run `uv run trove setup` before the slow ASR test")

    result = asr.MlxWhisperTranscriber().transcribe(
        FIXTURES / "short.m4a", _context(tmp_path)
    )

    assert result.model == DEFAULT_ASR_MODEL
