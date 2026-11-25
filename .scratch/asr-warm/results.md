# Warm ASR process: measured results

- Date: 2026-11-25
- Machine: Apple M1 Pro, 32GB, macOS 14.6.1
- Model: FunASR Paraformer-zh + FSMN-VAD + small CT-Transformer punctuation

## Problem

Each transcription spawned a new `asr_worker` process, so the model was loaded
again for every Item. Warm leaf load is about 4–6 seconds; a collection of 100
Items pays that cost 100 times.

## Change

- `ParaformerTranscriber` owns a persistent `asr_server` child process.
- The child loads the model once and serves requests over a `multiprocessing` Pipe.
- Cancellation, timeout, or a crash terminates the child; the next run reloads.
- Ten minutes without a request terminates the child and releases memory.
- Model paths are passed as local snapshot directories instead of ModelScope IDs.

## Measurements

Two consecutive 150-second transcriptions in one process:

| Call | Elapsed | Notes |
|---|---:|---|
| First | 27.6s | includes model load |
| Second | 18.7s | warm model, inference only |

Saving: about **8.9 seconds per subsequent Item**. The machine was busy with
Spotlight indexing during the run, so absolute numbers are conservative.

Model load with local snapshot paths versus ModelScope IDs (warm page cache):

| Input | Load |
|---|---:|
| ModelScope IDs | 6.2s |
| Local snapshot paths | 4.2s |

## Trade-offs

- The child holds about 2.8GB RSS while warm; idle timeout releases it after 10 minutes.
- One request at a time per worker; no parallel ASR within a worker.
- Cancellation kills the warm process, so the next Item reloads.
- `multiprocessing` uses `spawn`; callers need a real module entry point (Trove CLI/worker).
- Running multiple workers against one `~/Trove` still creates multiple model copies;
  the documented deployment remains one worker.

## Verification

- `uv run pytest tests/test_asr.py -q` — 8 passed.
- `TROVE_RUN_SLOW_ASR=1 uv run pytest tests/test_asr.py::test_real_funasr_transcribes_fixture -q -m slow` — passed; the slow test asserts the same child PID is reused.
- `uv run trove bench asr` on real audio — passed.
- Targeted reprocess/ffmpeg tests — passed.
