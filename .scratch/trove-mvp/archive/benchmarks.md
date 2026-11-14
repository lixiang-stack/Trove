# Performance and storage benchmarks

Ticket: [26 — ASR、搜索与存储性能基准](26-performance-storage-benchmark.md)
Status: archived — evidence recorded in acceptance.md; 1 h sample optional

Record real commands, data, machine, model versions, and dates. Do not use synthetic
audio or a fake library for the reported numbers.

## Machine and versions

| Field        | Value |
| ------------ | ----- |
| Mac model    | M1 Pro |
| macOS        |       |
| Trove        | `uv run trove --version` |
| ASR model    | `mlx-community/whisper-large-v3-turbo` |
| FFmpeg       | `ffmpeg -version` |
| Date         |       |

## ASR component

```bash
uv run trove bench asr "/path/to/real-1-hour-chinese-audio.m4a" --json
```

| Metric | Target | Measured |
| ------ | ------ | -------- |
| Duration | 1 hour | |
| Elapsed | ≤20 min | |
| Realtime factor | ≤0.333 | |
| Language / segments | | |

## End-to-end video

Add a real 1-hour video URL and run the full pipeline synchronously (network and
real tools required; `TROVE_LLM_ENABLED=false` skips organization if needed):

```bash
uv run trove bench pipeline "https://www.youtube.com/watch?v=<single-video>" --json
```

| Metric | Target | Measured |
| ------ | ------ | -------- |
| End-to-end | <30 min | |
| Download | | |
| Audio extraction | | |
| Transcription | | |
| Organization | | |
| Indexing | | |

## Search

Prepare 1k Items (real + repeatable seed) and a pre-registered query file. Use a
disposable home for the repeatable seed so the real library stays clean; the format
starts from [bench-queries.example.txt](bench-queries.example.txt):

```bash
TROVE_HOME=~/Trove-bench uv run trove bench seed --count 1000
TROVE_HOME=~/Trove-bench uv run trove bench search --queries ... --json
```

```bash
uv run trove bench search --queries .scratch/trove-mvp/bench-queries.txt --repeat 3 --json
```

| Metric | Target | Measured |
| ------ | ------ | -------- |
| Items | ~1,000 | |
| Queries | | |
| p50 | | |
| p95 | <1 s (goal <100 ms) | |
| Index rows | | |
| SQLite file size | | |

## Storage

After importing 20 real Items, record `du -sh` per package and extrapolate to
100 hours of audio + 100 books:

```bash
du -sh ~/Trove/library/* | sort -h
du -sh ~/Trove/library ~/Trove/trove.db
```

| Component | 20 Items | Extrapolated 100h + 100 books |
| --------- | -------- | ----------------------------- |
| Audio | | |
| EPUB sources | | |
| Transcripts | | |
| Book JSON | | |
| AI JSON | | |
| SQLite | | |
| **Total** | | target <5 GB |

If a target fails, record the action (ASR change, bitrate, index tuning, chunking)
and open an improvement issue. Do not claim the NFR is met.
