#!/usr/bin/env python3
"""Compare ASR engines on real Trove library audio (no human reference).

This produces transcripts, segment counts, wall time, RTF and peak RSS. Domain
terms are checked separately because the library has no ground-truth text.
"""

from __future__ import annotations

import argparse
import json
import os
import threading
import time
from pathlib import Path

import psutil

ROOT = Path.home() / "Trove" / "cache" / "asr-bench"
OUT = ROOT / "real"
SHERPA = ROOT / "sherpa"


class RssSampler:
    def __init__(self) -> None:
        self.peak = 0
        self._stop = threading.Event()
        self._process = psutil.Process()

    def _run(self) -> None:
        while not self._stop.wait(0.05):
            try:
                self.peak = max(self.peak, self._process.memory_info().rss)
            except psutil.Error:
                return

    def __enter__(self):
        threading.Thread(target=self._run, daemon=True).start()
        return self

    def __exit__(self, *args):
        self._stop.set()


def segments_from_whisper(output: dict) -> list[dict]:
    return [
        {
            "start_ms": round(float(segment.get("start") or 0) * 1000),
            "end_ms": round(float(segment.get("end") or 0) * 1000),
            "text": str(segment.get("text") or "").strip(),
        }
        for segment in output.get("segments") or []
        if str(segment.get("text") or "").strip()
    ]


def run_whisper(audio: Path) -> dict:
    import mlx_whisper

    started = time.perf_counter()
    cpu_started = time.process_time()
    with RssSampler() as sampler:
        output = mlx_whisper.transcribe(
            str(audio),
            path_or_hf_repo=os.environ.get(
                "WHISPER_MODEL", "mlx-community/whisper-large-v3-turbo"
            ),
            language=None,
            task="transcribe",
            word_timestamps=False,
            condition_on_previous_text=False,
            no_speech_threshold=0.6,
            logprob_threshold=-1.0,
            compression_ratio_threshold=2.4,
            verbose=False,
        )
    return {
        "engine": "whisper",
        "model": os.environ.get("WHISPER_MODEL", "mlx-community/whisper-large-v3-turbo"),
        "language": output.get("language"),
        "segments": segments_from_whisper(output),
        "elapsed": time.perf_counter() - started,
        "cpu_seconds": time.process_time() - cpu_started,
        "peak_rss_bytes": sampler.peak,
    }


def run_funasr(audio: Path, engine: str) -> dict:
    from funasr import AutoModel

    started = time.perf_counter()
    cpu_started = time.process_time()
    with RssSampler() as sampler:
        common = {
            "device": "cpu",
            "disable_update": True,
            "disable_pbar": True,
            "disable_log": True,
            "log_level": "ERROR",
        }
        if engine == "sensevoice":
            model = AutoModel(model="iic/SenseVoiceSmall", vad_model="fsmn-vad", **common)
        else:
            model = AutoModel(
                model="paraformer-zh",
                vad_model="fsmn-vad",
                punc_model="iic/punc_ct-transformer_zh-cn-common-vocab272727-pytorch",
                **common,
            )
        output = model.generate(
            input=str(audio),
            language="zh",
            use_itn=True,
            batch_size_s=300,
            sentence_timestamp=True,
        )[0]
        sentences = output.get("sentence_info") or []
        segments = [
            {
                "start_ms": int(sentence.get("start") or 0),
                "end_ms": int(sentence.get("end") or 0),
                "text": str(sentence.get("text") or "").strip(),
            }
            for sentence in sentences
            if str(sentence.get("text") or "").strip()
        ]
        if not segments:
            segments = [{"start_ms": 0, "end_ms": 0, "text": str(output.get("text") or "")}]
    return {
        "engine": engine,
        "model": "iic/SenseVoiceSmall" if engine == "sensevoice" else "paraformer-zh",
        "language": "zh",
        "segments": segments,
        "elapsed": time.perf_counter() - started,
        "cpu_seconds": time.process_time() - cpu_started,
        "peak_rss_bytes": sampler.peak,
    }


def run_sherpa(audio: Path, fp32: bool) -> dict:
    import numpy as np
    import sherpa_onnx
    import soundfile as sf

    started = time.perf_counter()
    cpu_started = time.process_time()
    with RssSampler() as sampler:
        model_dir = SHERPA / "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17"
        recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
            model=str(model_dir / ("model.onnx" if fp32 else "model.int8.onnx")),
            tokens=str(model_dir / "tokens.txt"),
            num_threads=int(os.environ.get("SHERPA_THREADS", "4")),
            language="zh",
            use_itn=True,
        )
        config = sherpa_onnx.VadModelConfig()
        config.silero_vad.model = str(SHERPA / "silero_vad.onnx")
        config.silero_vad.min_silence_duration = float(
            os.environ.get("SHERPA_MIN_SILENCE", "0.25")
        )
        config.sample_rate = 16000
        window_size = config.silero_vad.window_size
        vad = sherpa_onnx.VoiceActivityDetector(config, buffer_size_in_seconds=100)

        audio_samples, sample_rate = sf.read(str(audio), dtype="float32")
        if sample_rate != 16000:
            raise SystemExit(f"Expected 16 kHz audio, got {sample_rate}")
        vad_segments = []
        pending = np.zeros(0, dtype=np.float32)

        for offset in range(0, len(audio_samples), window_size):
            chunk = audio_samples[offset : offset + window_size]
            pending = np.concatenate([pending, chunk])
            while len(pending) >= window_size:
                vad.accept_waveform(pending[:window_size])
                pending = pending[window_size:]
            while not vad.empty():
                segment = vad.front
                vad_segments.append(
                    {
                        "start": segment.start,
                        "samples": np.array(segment.samples, dtype=np.float32),
                    }
                )
                vad.pop()
        if len(pending):
            vad.accept_waveform(pending)
        vad.flush()
        while not vad.empty():
            segment = vad.front
            vad_segments.append(
                {"start": segment.start, "samples": np.array(segment.samples, dtype=np.float32)}
            )
            vad.pop()

        fixed_window = float(os.environ.get("SHERPA_FIXED_WINDOW", "0"))
        if fixed_window > 0:
            step = int(fixed_window * 16000)
            bounds = [0]
            if os.environ.get("SHERPA_CUT_ALIGN") == "1":
                frame = 320
                hop = 160
                search = int(2.0 * 16000)
                while bounds[-1] + step < len(audio_samples):
                    target = bounds[-1] + step
                    low = max(bounds[-1] + int(0.5 * step), target - search)
                    high = min(len(audio_samples), target + search)
                    best = target
                    best_energy = float("inf")
                    for position in range(low, max(low + 1, high - frame), hop):
                        energy = float(np.mean(audio_samples[position : position + frame] ** 2))
                        if energy < best_energy:
                            best_energy = energy
                            best = position
                    bounds.append(best)
                bounds.append(len(audio_samples))
            else:
                bounds = list(range(0, len(audio_samples), step)) + [len(audio_samples)]
            segments = []
            for start, end in zip(bounds, bounds[1:], strict=False):
                stream = recognizer.create_stream()
                stream.accept_waveform(16000, audio_samples[start:end])
                recognizer.decode_stream(stream)
                text = stream.result.text.strip()
                if text:
                    segments.append(
                        {
                            "start_ms": round(start / 16000 * 1000),
                            "end_ms": round(end / 16000 * 1000),
                            "text": text,
                        }
                    )
            return {
                "engine": "sherpa-fp32" if fp32 else "sherpa",
                "model": "sherpa-onnx SenseVoiceSmall fp32"
                if fp32
                else "sherpa-onnx SenseVoiceSmall int8",
                "language": "zh",
                "segments": segments,
                "elapsed": time.perf_counter() - started,
                "cpu_seconds": time.process_time() - cpu_started,
                "peak_rss_bytes": sampler.peak,
            }

        group_seconds = float(os.environ.get("SHERPA_GROUP_SECONDS", "20"))
        groups = []
        current = []
        current_seconds = 0.0
        for segment in vad_segments:
            if current:
                previous_end = current[-1]["start"] + len(current[-1]["samples"])
                gap = segment["start"] - previous_end
                if current_seconds >= group_seconds or gap > 1.0 * 16000:
                    groups.append(current)
                    current = []
                    current_seconds = 0.0
            current.append(segment)
            current_seconds += len(segment["samples"]) / 16000
        if current:
            groups.append(current)

        segments = []
        for group in groups:
            start = group[0]["start"]
            end = group[-1]["start"] + len(group[-1]["samples"])
            samples = audio_samples[start:end]
            stream = recognizer.create_stream()
            stream.accept_waveform(16000, samples)
            recognizer.decode_stream(stream)
            text = stream.result.text.strip()
            if text:
                segments.append(
                    {
                        "start_ms": round(start / 16000 * 1000),
                        "end_ms": round(end / 16000 * 1000),
                        "text": text,
                    }
                )
        if not segments and len(audio_samples):
            stream = recognizer.create_stream()
            stream.accept_waveform(16000, audio_samples)
            recognizer.decode_stream(stream)
            text = stream.result.text.strip()
            if text:
                segments.append(
                    {
                        "start_ms": 0,
                        "end_ms": round(len(audio_samples) / 16000 * 1000),
                        "text": text,
                    }
                )
    return {
        "engine": "sherpa-fp32" if fp32 else "sherpa",
        "model": "sherpa-onnx SenseVoiceSmall fp32"
        if fp32
        else "sherpa-onnx SenseVoiceSmall int8",
        "language": "zh",
        "segments": segments,
        "elapsed": time.perf_counter() - started,
        "cpu_seconds": time.process_time() - cpu_started,
        "peak_rss_bytes": sampler.peak,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--engine",
        choices=["whisper", "sensevoice", "paraformer", "sherpa", "sherpa-fp32"],
        required=True,
    )
    parser.add_argument("--audio", required=True)
    parser.add_argument("--tag", required=True)
    args = parser.parse_args()

    audio = Path(args.audio).expanduser()
    if args.engine == "whisper":
        payload = run_whisper(audio)
    elif args.engine in {"sensevoice", "paraformer"}:
        payload = run_funasr(audio, args.engine)
    else:
        payload = run_sherpa(audio, fp32=args.engine == "sherpa-fp32")
    import soundfile as sf

    payload["audio"] = str(audio)
    payload["audio_seconds"] = round(sf.info(str(audio)).duration, 3)
    payload["rtf"] = round(payload["elapsed"] / payload["audio_seconds"], 4)
    payload["avg_cores"] = round(payload["cpu_seconds"] / payload["elapsed"], 2)
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{args.tag}.{args.engine}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"{args.engine}: {len(payload['segments'])} segments, "
        f"{payload['elapsed']:.1f}s, RTF {payload['rtf']:.3f}, "
        f"{payload['avg_cores']:.1f} cores, "
        f"peak RSS {payload['peak_rss_bytes'] / 1e9:.2f} GB -> {path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
