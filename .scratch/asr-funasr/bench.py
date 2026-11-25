#!/usr/bin/env python3
"""Reproducible ASR bake-off: mlx-whisper vs FunASR on AISHELL-1 test audio.

Run each command with the matching virtualenv:

    .venv-funasr/bin/python .scratch/asr-funasr/bench.py prepare --sample-every 5
    .venv-whisper/bin/python .scratch/asr-funasr/bench.py run --engine whisper
    .venv-funasr/bin/python .scratch/asr-funasr/bench.py run --engine sensevoice
    .venv-funasr/bin/python .scratch/asr-funasr/bench.py report

The AISHELL parquet files are expected under ~/Trove/cache/asr-bench/aishell.
Outputs stay under ~/Trove/cache/asr-bench.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import resource
import threading
import time
import unicodedata
from pathlib import Path

import psutil

ROOT = Path.home() / "Trove" / "cache" / "asr-bench"
AISHELL = ROOT / "aishell"
WAV_DIR = ROOT / "aishell_wav_sample"
CHUNK_DIR = ROOT / "aishell_chunks"
MANIFEST = ROOT / "manifest_sample.json"
CHUNK_MANIFEST = ROOT / "manifest_chunks.json"
OUT_DIR = ROOT / "runs"
SAMPLE_RATE = 16000
CHUNK_SECONDS = 30.0
CHUNK_GAP_SECONDS = 0.2


def normalize(text: str) -> str:
    import warnings

    import cn2an
    import zhconv

    text = re.sub(r"<\|[^|]*\|>", "", text)
    text = zhconv.convert(unicodedata.normalize("NFKC", text).lower(), "zh-cn")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            text = cn2an.transform(text, "cn2an")
    except (ValueError, TypeError):
        pass
    kept = []
    for char in text:
        category = unicodedata.category(char)
        if category.startswith("L") or category.startswith("N"):
            kept.append(char)
    return "".join(kept)


def prepare(sample_every: int) -> None:
    import numpy as np
    import pyarrow.parquet as pq
    import soundfile as sf

    AISHELL.mkdir(parents=True, exist_ok=True)
    WAV_DIR.mkdir(parents=True, exist_ok=True)
    CHUNK_DIR.mkdir(parents=True, exist_ok=True)
    rows: list[tuple[str, str]] = []
    for shard in sorted(AISHELL.glob("test-*.parquet")):
        table = pq.read_table(shard, columns=["context", "answer"])
        for ctx, answer in zip(
            table["context"].to_pylist(), table["answer"].to_pylist(), strict=False
        ):
            rows.append((ctx["bytes"], answer))
    if not rows:
        raise SystemExit(f"No parquet files in {AISHELL}")

    entries = []
    total_duration = 0.0
    for source_index in range(0, len(rows), sample_every):
        audio_bytes, answer = rows[source_index]
        audio, sample_rate = sf.read(io.BytesIO(audio_bytes), dtype="float32")
        if sample_rate != SAMPLE_RATE:
            raise SystemExit(f"Unexpected sample rate {sample_rate}")
        utterance_id = f"utt_{source_index:05d}"
        path = WAV_DIR / f"{utterance_id}.wav"
        if not path.exists():
            sf.write(path, audio, sample_rate, subtype="PCM_16")
        duration = len(audio) / sample_rate
        total_duration += duration
        entries.append(
            {
                "id": utterance_id,
                "path": str(path),
                "reference": answer,
                "duration": round(duration, 3),
            }
        )
    MANIFEST.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")

    chunks = []
    gap = np.zeros(int(CHUNK_GAP_SECONDS * SAMPLE_RATE), dtype=np.float32)
    pending_audio: list[np.ndarray] = []
    pending_refs: list[str] = []
    pending_seconds = 0.0
    pending_ids: list[str] = []

    def flush() -> None:
        nonlocal pending_audio, pending_refs, pending_seconds, pending_ids
        if not pending_audio:
            return
        audio = np.concatenate(
            [
                part
                for pair in zip(pending_audio, [gap] * len(pending_audio), strict=False)
                for part in pair
            ][:-1]
        )
        chunk_id = f"chunk_{len(chunks):04d}"
        path = CHUNK_DIR / f"{chunk_id}.wav"
        sf.write(path, audio, SAMPLE_RATE, subtype="PCM_16")
        chunks.append(
            {
                "id": chunk_id,
                "path": str(path),
                "reference": "".join(pending_refs),
                "duration": round(len(audio) / SAMPLE_RATE, 3),
                "members": pending_ids,
            }
        )
        pending_audio, pending_refs, pending_seconds, pending_ids = [], [], 0.0, []

    for entry in entries:
        audio, sample_rate = sf.read(entry["path"], dtype="float32")
        pending_audio.append(audio)
        pending_refs.append(entry["reference"])
        pending_ids.append(entry["id"])
        pending_seconds += entry["duration"]
        if pending_seconds >= CHUNK_SECONDS:
            flush()
    flush()
    CHUNK_MANIFEST.write_text(json.dumps(chunks, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"prepared {len(entries)} utterances / {len(chunks)} chunks, "
        f"{total_duration / 3600:.2f} h, "
        f"{sum(len(e['reference']) for e in entries)} reference chars"
    )


class RssSampler:
    def __init__(self) -> None:
        self.peak = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._process = psutil.Process()

    def _run(self) -> None:
        while not self._stop.wait(0.05):
            try:
                self.peak = max(self.peak, self._process.memory_info().rss)
            except psutil.Error:
                return

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *args):
        self._stop.set()
        self._thread.join(timeout=1)


def _load_manifest(path: Path) -> list[dict]:
    if not path.exists():
        raise SystemExit(f"Missing manifest {path}; run prepare first")
    return json.loads(path.read_text(encoding="utf-8"))


def run_whisper(limit: int | None, manifest_path: Path) -> dict:
    import mlx_whisper

    entries = _load_manifest(manifest_path)[:limit]
    model = os.environ.get("WHISPER_MODEL", "mlx-community/whisper-large-v3-turbo")
    results = []
    load_seconds = None
    started = time.perf_counter()
    inference_seconds = 0.0
    with RssSampler() as sampler:
        for index, entry in enumerate(entries):
            t0 = time.perf_counter()
            output = mlx_whisper.transcribe(
                entry["path"],
                path_or_hf_repo=model,
                language=None,
                task="transcribe",
                word_timestamps=False,
                condition_on_previous_text=False,
                no_speech_threshold=0.6,
                logprob_threshold=-1.0,
                compression_ratio_threshold=2.4,
                verbose=False,
            )
            elapsed = time.perf_counter() - t0
            if index == 0:
                # mlx loads inside the first call; total wall below is what matters
                load_seconds = 0.0
            inference_seconds += elapsed
            results.append(
                {
                    "id": entry["id"],
                    "text": output.get("text", ""),
                    "language": output.get("language"),
                    "elapsed": elapsed,
                }
            )
    total_seconds = time.perf_counter() - started
    return {
        "engine": "whisper",
        "model": model,
        "utterances": len(entries),
        "audio_seconds": sum(e["duration"] for e in entries),
        "total_seconds": total_seconds,
        "inference_seconds": inference_seconds,
        "load_seconds": load_seconds,
        "peak_rss_bytes": sampler.peak,
        "maxrss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "results": results,
    }


def _funasr_model(engine: str):
    from funasr import AutoModel

    common = {
        "device": "cpu",
        "disable_update": True,
        "disable_pbar": True,
        "disable_log": True,
        "log_level": "ERROR",
    }
    if engine == "sensevoice":
        return AutoModel(
            model=os.environ.get("FUNASR_MODEL", "iic/SenseVoiceSmall"),
            vad_model="fsmn-vad",
            **common,
        )
    if engine == "paraformer":
        return AutoModel(
            model=os.environ.get("FUNASR_MODEL", "paraformer-zh"),
            vad_model="fsmn-vad",
            punc_model="iic/punc_ct-transformer_zh-cn-common-vocab272727-pytorch",
            **common,
        )
    raise SystemExit(f"Unknown engine {engine}")


def run_funasr(engine: str, limit: int | None, manifest_path: Path) -> dict:
    entries = _load_manifest(manifest_path)[:limit]
    total_audio = sum(e["duration"] for e in entries)
    started = time.perf_counter()
    with RssSampler() as sampler:
        model = _funasr_model(engine)
        load_seconds = time.perf_counter() - started
        results = []
        inference_seconds = 0.0
        batch_size = int(os.environ.get("FUNASR_BATCH_SECONDS", "300"))
        for entry in entries:
            kwargs = {
                "language": "zh",
                "use_itn": True,
                "batch_size_s": batch_size,
                "sentence_timestamp": True,
            }
            t0 = time.perf_counter()
            output = model.generate(input=entry["path"], **kwargs)
            elapsed = time.perf_counter() - t0
            inference_seconds += elapsed
            row = output[0]
            sentences = row.get("sentence_info") or []
            text = "".join(str(s.get("text") or "") for s in sentences)
            if not text:
                text = str(row.get("text") or "")
            results.append(
                {
                    "id": entry["id"],
                    "text": text,
                    "language": "zh",
                    "elapsed": elapsed,
                    "sentences": len(sentences),
                }
            )
    total_seconds = time.perf_counter() - started
    return {
        "engine": engine,
        "model": os.environ.get(
            "FUNASR_MODEL",
            "iic/SenseVoiceSmall" if engine == "sensevoice" else "paraformer-zh",
        ),
        "utterances": len(entries),
        "audio_seconds": total_audio,
        "total_seconds": total_seconds,
        "inference_seconds": inference_seconds,
        "load_seconds": load_seconds,
        "peak_rss_bytes": sampler.peak,
        "maxrss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "results": results,
    }


def run_sherpa(limit: int | None, manifest_path: Path, *, fp32: bool = False) -> dict:
    import sherpa_onnx
    import soundfile as sf

    entries = _load_manifest(manifest_path)[:limit]
    model_dir = ROOT / "sherpa" / "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17"
    started = time.perf_counter()
    with RssSampler() as sampler:
        recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
            model=str(model_dir / ("model.onnx" if fp32 else "model.int8.onnx")),
            tokens=str(model_dir / "tokens.txt"),
            num_threads=int(os.environ.get("SHERPA_THREADS", "4")),
            language=os.environ.get("SHERPA_LANGUAGE", "zh"),
            use_itn=True,
            debug=False,
        )
        load_seconds = time.perf_counter() - started
        results = []
        inference_seconds = 0.0
        for entry in entries:
            audio, sample_rate = sf.read(entry["path"], dtype="float32")
            stream = recognizer.create_stream()
            stream.accept_waveform(sample_rate, audio)
            t0 = time.perf_counter()
            recognizer.decode_stream(stream)
            elapsed = time.perf_counter() - t0
            inference_seconds += elapsed
            results.append(
                {
                    "id": entry["id"],
                    "text": stream.result.text,
                    "language": "zh",
                    "elapsed": elapsed,
                    "tokens": len(stream.result.tokens),
                }
            )
    total_seconds = time.perf_counter() - started
    return {
        "engine": "sherpa-fp32" if fp32 else "sherpa",
        "model": "sherpa-onnx SenseVoiceSmall fp32" if fp32 else "sherpa-onnx SenseVoiceSmall int8",
        "utterances": len(entries),
        "audio_seconds": sum(e["duration"] for e in entries),
        "total_seconds": total_seconds,
        "inference_seconds": inference_seconds,
        "load_seconds": load_seconds,
        "peak_rss_bytes": sampler.peak,
        "maxrss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "results": results,
    }


def run(args) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest_path = Path(args.manifest).expanduser()
    if args.engine == "whisper":
        payload = run_whisper(args.limit, manifest_path)
    elif args.engine == "sherpa":
        payload = run_sherpa(args.limit, manifest_path)
    elif args.engine == "sherpa-fp32":
        payload = run_sherpa(args.limit, manifest_path, fp32=True)
    else:
        payload = run_funasr(args.engine, args.limit, manifest_path)
    payload["started_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    payload["manifest"] = str(manifest_path)
    output_path = OUT_DIR / f"{args.engine}.json"
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"{args.engine}: {payload['utterances']} utts / {payload['audio_seconds'] / 3600:.2f} h, "
        f"wall {payload['total_seconds']:.1f}s, inference {payload['inference_seconds']:.1f}s, "
        f"RTF {payload['inference_seconds'] / payload['audio_seconds']:.3f}, "
        f"peak RSS {payload['peak_rss_bytes'] / 1e9:.2f} GB"
    )


def _align_errors(reference: str, hypothesis: str) -> list[tuple[str, str, str]]:
    import difflib

    matcher = difflib.SequenceMatcher(a=reference, b=hypothesis, autojunk=False)
    errors = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        errors.append((tag, reference[i1:i2], hypothesis[j1:j2]))
    return errors


def _bootstrap_ci(values: list[float], iterations: int = 5000) -> tuple[float, float]:
    import random

    if not values:
        return 0.0, 0.0
    random.seed(20261124)
    means = []
    for _ in range(iterations):
        means.append(
            sum(values[random.randrange(len(values))] for _ in range(len(values))) / len(values)
        )
    means.sort()
    return means[int(0.025 * iterations)], means[int(0.975 * iterations)]


def _paired_bootstrap(
    left: list[float], right: list[float], iterations: int = 5000
) -> tuple[float, float, float, float]:
    """Bootstrap the mean of left - right for paired per-chunk CER values."""
    import random

    differences = [a - b for a, b in zip(left, right, strict=False)]
    random.seed(20261124)
    means = []
    for _ in range(iterations):
        means.append(
            sum(
                differences[random.randrange(len(differences))]
                for _ in range(len(differences))
            )
            / len(differences)
        )
    means.sort()
    observed = sum(differences) / len(differences)
    lower = means[int(0.025 * iterations)]
    upper = means[int(0.975 * iterations)]
    below = sum(1 for value in means if value <= 0) / iterations
    above = sum(1 for value in means if value >= 0) / iterations
    p_value = min(1.0, 2 * min(below, above))
    return observed, lower, upper, p_value


def report(args) -> None:
    import jiwer

    runs = {}
    for path in sorted(OUT_DIR.glob("*.json")):
        if path.name.startswith("report"):
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        runs[payload["engine"]] = payload
    if not runs:
        raise SystemExit("No run files; run at least one engine first")
    manifests = {payload["manifest"] for payload in runs.values()}
    if len(manifests) != 1:
        raise SystemExit(f"Runs used different manifests: {sorted(manifests)}")
    manifest = {
        entry["id"]: entry for entry in _load_manifest(Path(manifests.pop()).expanduser())
    }

    per_chunk_cer: dict[str, dict[str, float]] = {}
    report_rows = []
    for engine, payload in runs.items():
        references = []
        hypotheses = []
        per_utterance = []
        row_cers = {}
        errors = []
        for row in payload["results"]:
            entry = manifest.get(row["id"])
            if entry is None:
                continue
            reference = normalize(entry["reference"])
            hypothesis = normalize(row["text"])
            references.append(reference)
            hypotheses.append(hypothesis)
            if reference:
                value = jiwer.cer(reference, hypothesis)
                per_utterance.append(value)
                row_cers[row["id"]] = value
            errors.extend(_align_errors(reference, hypothesis))
        per_chunk_cer[engine] = row_cers
        counts = jiwer.process_characters(references, hypotheses)
        cer = counts.cer
        low, high = _bootstrap_ci(per_utterance)
        exact = sum(
            1 for a, b in zip(references, hypotheses, strict=False) if a == b
        ) / max(1, len(references))
        bad = sum(1 for value in per_utterance if value > 0.5) / max(1, len(per_utterance))
        substitutions: dict[tuple[str, str], int] = {}
        for tag, ref, hyp in errors:
            if tag == "replace":
                key = (ref, hyp)
                substitutions[key] = substitutions.get(key, 0) + 1
        top = sorted(substitutions.items(), key=lambda item: item[1], reverse=True)[:15]
        report_rows.append(
            {
                "engine": engine,
                "model": payload["model"],
                "utterances": len(references),
                "audio_hours": round(payload["audio_seconds"] / 3600, 3),
                "wall_seconds": round(payload["total_seconds"], 1),
                "inference_seconds": round(payload["inference_seconds"], 1),
                "load_seconds": round(payload["load_seconds"], 1),
                "rtf_inference": round(payload["inference_seconds"] / payload["audio_seconds"], 4),
                "rtf_end_to_end": round(payload["total_seconds"] / payload["audio_seconds"], 4),
                "peak_rss_gb": round(payload["peak_rss_bytes"] / 1e9, 2),
                "cer": round(cer, 4),
                "cer_ci95": [round(low, 4), round(high, 4)],
                "character_errors": {
                    "substitutions": counts.substitutions,
                    "deletions": counts.deletions,
                    "insertions": counts.insertions,
                    "reference_chars": counts.hits
                    + counts.substitutions
                    + counts.deletions,
                },
                "sentence_exact_match": round(exact, 4),
                "utterances_cer_gt_50pct": round(bad, 4),
                "top_substitutions": [
                    {"reference": ref, "hypothesis": hyp, "count": count}
                    for (ref, hyp), count in top
                ],
            }
        )
        print(
            f"{engine:12s} CER {cer * 100:5.2f}%  95%CI [{low * 100:.2f}, {high * 100:.2f}]  "
            f"RTF {payload['inference_seconds'] / payload['audio_seconds']:.3f}  "
            f"RSS {payload['peak_rss_bytes'] / 1e9:.2f} GB  exact {exact * 100:.1f}%"
        )

    if "whisper" in per_chunk_cer:
        baseline = per_chunk_cer["whisper"]
        for row in report_rows:
            if row["engine"] == "whisper":
                continue
            candidate = per_chunk_cer[row["engine"]]
            common = sorted(set(baseline) & set(candidate))
            observed, low, high, p_value = _paired_bootstrap(
                [candidate[key] for key in common],
                [baseline[key] for key in common],
            )
            row["paired_delta_cer_vs_whisper"] = {
                "mean_delta": round(observed, 4),
                "ci95": [round(low, 4), round(high, 4)],
                "p_value": round(p_value, 5),
                "chunks": len(common),
            }
            print(
                f"{row['engine']:12s} ΔCER vs whisper "
                f"{observed * 100:+.2f} pp  95%CI [{low * 100:+.2f}, {high * 100:+.2f}]  "
                f"p={p_value:.5f}"
            )

    output_path = OUT_DIR / "report.json"
    output_path.write_text(json.dumps(report_rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {output_path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    prepare_parser = sub.add_parser("prepare")
    prepare_parser.add_argument("--sample-every", type=int, default=1)
    run_parser = sub.add_parser("run")
    run_parser.add_argument(
        "--engine",
        choices=["whisper", "sensevoice", "paraformer", "sherpa", "sherpa-fp32"],
        required=True,
    )
    run_parser.add_argument("--limit", type=int, default=None)
    run_parser.add_argument("--manifest", default=str(CHUNK_MANIFEST))
    sub.add_parser("report")
    args = parser.parse_args(argv)
    if args.command == "prepare":
        prepare(args.sample_every)
    elif args.command == "run":
        run(args)
    else:
        report(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
