from __future__ import annotations

import subprocess
import tempfile
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from trove.config import Config
from trove.content_package import TranscriptDocument, TranscriptSegment
from trove.ports import StageContext

SEARCH_LIMIT = 20
SEARCH_REPEAT = 3
SEED_TERMS = ("人工智能", "记忆", "智能体", "注意力", "播客", "transcript")


def percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * ratio)))
    return ordered[index]


def summarize(values: list[float]) -> dict[str, float | int]:
    if not values:
        return {
            "count": 0,
            "min_ms": 0.0,
            "p50_ms": 0.0,
            "p95_ms": 0.0,
            "max_ms": 0.0,
            "mean_ms": 0.0,
        }
    return {
        "count": len(values),
        "min_ms": round(min(values), 2),
        "p50_ms": round(percentile(values, 0.50), 2),
        "p95_ms": round(percentile(values, 0.95), 2),
        "max_ms": round(max(values), 2),
        "mean_ms": round(sum(values) / len(values), 2),
    }


def read_queries(path: Path) -> list[str]:
    queries = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            queries.append(line)
    if not queries:
        raise ValueError("Query file is empty")
    return queries


def run_search_benchmark(
    runtime,
    queries: list[str],
    *,
    repeat: int = SEARCH_REPEAT,
    limit: int = SEARCH_LIMIT,
) -> dict[str, Any]:
    samples: list[float] = []
    per_query = []
    for query in queries:
        query_samples = []
        count = 0
        for _ in range(repeat):
            started = time.perf_counter()
            results = runtime.search.search(query, limit=limit)
            elapsed_ms = (time.perf_counter() - started) * 1000
            query_samples.append(elapsed_ms)
            samples.append(elapsed_ms)
            count = len(results)
        per_query.append(
            {
                "query": query,
                "results": count,
                "timings": summarize(query_samples),
            }
        )
    index_rows = runtime.search.index_status().total_rows
    return {
        "queries": len(queries),
        "repeat": repeat,
        "limit": limit,
        "index_rows": index_rows,
        "database_bytes": runtime.config.db_path.stat().st_size,
        "summary": summarize(samples),
        "results": per_query,
    }


def seed_library(config: Config, count: int) -> int:
    from trove.composition import build_runtime
    from trove.worker import ensure_migrated

    runtime = build_runtime(config)
    ensure_migrated(runtime)
    for index in range(count):
        term = SEED_TERMS[index % len(SEED_TERMS)]
        bundle, _ = runtime.library.create_item(
            source_key=f"bench-seed:{uuid.uuid4()}",
            source_type="local_audio",
            platform="local",
            title=f"Benchmark {term} {index:04d}",
        )
        runtime.package.write_transcript(
            bundle.item.id,
            TranscriptDocument(
                language="zh",
                model="benchmark-seed",
                segments=[
                    TranscriptSegment(
                        seq=0,
                        start_ms=0,
                        end_ms=1000,
                        text=f"{term} benchmark segment {index}",
                    )
                ],
            ),
        )
        runtime.search_index.index_item(bundle.item.id)
    return count


def run_pipeline_benchmark(config: Config, url: str) -> dict[str, Any]:
    from trove.composition import build_runtime
    from trove.worker import ensure_migrated

    runtime = build_runtime(config)
    ensure_migrated(runtime)
    started_at = datetime.now(UTC).isoformat()
    started = time.perf_counter()
    bundle, deduplicated = runtime.intake.add_video_url(url)
    run = bundle.run
    if run is None:
        raise RuntimeError("Intake did not create a Processing Run")
    runtime.processing.process(run.id)
    elapsed = time.perf_counter() - started
    final = runtime.library.get(bundle.item.id)
    return {
        "url": url,
        "item_id": bundle.item.id,
        "title": final.item.title,
        "deduplicated": deduplicated,
        "started_at": started_at,
        "elapsed_sec": round(elapsed, 3),
        "state": final.run_state,
        "error_code": final.run.error_code if final.run else None,
        "stages": [
            {
                "stage": step.stage,
                "state": step.state,
                "started_at": step.started_at,
                "finished_at": step.finished_at,
            }
            for step in final.steps
        ],
    }


def run_asr_benchmark(
    config: Config,
    audio_path: Path,
    *,
    model: str | None = None,
) -> dict[str, Any]:
    from trove.adapters.asr import MlxWhisperTranscriber

    duration = probe_duration(audio_path)
    with tempfile.TemporaryDirectory(prefix="trove-bench-asr-") as directory:
        context = StageContext(
            item_id="benchmark",
            run_id="benchmark",
            work_dir=Path(directory),
            should_cancel=lambda: False,
            log=lambda message: None,
        )
        transcriber = MlxWhisperTranscriber(model or config.asr_model)
        started_at = datetime.now(UTC).isoformat()
        started = time.perf_counter()
        result = transcriber.transcribe(audio_path, context)
        elapsed = time.perf_counter() - started
    realtime_factor = elapsed / duration if duration else None
    return {
        "audio": str(audio_path),
        "started_at": started_at,
        "duration_sec": duration,
        "elapsed_sec": round(elapsed, 3),
        "realtime_factor": round(realtime_factor, 4) if realtime_factor else None,
        "model": transcriber.model,
        "language": result.language,
        "segments": len(result.segments),
    }


def probe_duration(path: Path) -> float | None:
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=nw=1:nk=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    try:
        return float(result.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return None
