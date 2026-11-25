# FunASR vs mlx-whisper: measured results

- Date: 2026-11-24
- Machine: Apple M1 Pro, 32GB, macOS 14.6.1
- Runtime: Python 3.12.14, mlx-whisper 0.4.3, FunASR 1.4.29, sherpa-onnx 2.0.3

## TL;DR

- Every FunASR option tested beat `mlx-whisper` large-v3-turbo on Chinese CER.
- The accuracy-first winner is **FunASR Paraformer-zh (SeACo-Paraformer-large) + FSMN-VAD + the small CT-Transformer punctuation model**. AISHELL-1 sample CER: **3.19% vs 7.37%** for whisper, a paired improvement of **-4.14pp (95% CI -5.13 to -3.37, p < 0.00001)**.
- On the real 道德经 library it fixes the user-visible errors: `曾仕强` (not 孙世强/曾世强), `刍狗` (not 除狗), `天地不仁` (not 天地不能), `上德不德` (not 上德不得).
- Cost: 2.81GB peak RSS, one CPU core, RTF 0.136 (about 7.4x realtime), and about 1.25GB of models. This is heavier than whisper but still well inside the original 20 minutes per audio hour target.
- A resource-first alternative is SenseVoiceSmall int8 via sherpa-onnx: 5.82% CER, 0.94GB peak, 55x realtime, 239MB model. It is lighter but writes `曾仕强` as `曾世强`.

The default shipped in this branch is the accuracy-first Paraformer option, chosen by the user after seeing these numbers.

## Protocol

### Accuracy set

- AISHELL-1 test split (`AudioLLMs/aishell_1_zh_test`), human transcripts.
- Deterministic sample: every 5th utterance, 1,384 utterances / 1.95h / 20,326 reference characters.
- 30-second chunks: whole utterances concatenated with 200ms silence. This measures long-form behavior without penalising whisper for 30-second padding on 5-second files.
- Text normalisation: strip tags/punctuation, NFKC, traditional to simplified (`zhconv`), Chinese numerals to Arabic (`cn2an`), keep letters/numbers.
- Corpus CER via `jiwer`; 5,000-sample bootstrap 95% CI over chunks; paired bootstrap of per-chunk CER difference against whisper.

### Resource set

- Same AISHELL chunks for wall time, RTF, and peak RSS.
- Real library items p05 (6.6min), p27 (19min), p38 (29min) for qualitative domain checks and long-form behavior. No human reference, so they are not part of CER.
- Peak RSS is sampled every 50ms in the process; RTF is inference time divided by audio duration. Model load is reported separately.

### Engines

| Engine | Implementation |
|---|---|
| `whisper` | `mlx-whisper` 0.4.3, `mlx-community/whisper-large-v3-turbo` |
| `paraformer` | FunASR `paraformer-zh` + FSMN-VAD + small punctuation model, PyTorch CPU |
| `paraformer-large-punc` | Same ASR + `ct-punc` (large 1GB punctuation model) |
| `sensevoice` | FunASR SenseVoiceSmall fp32, PyTorch CPU |
| `sherpa` | SenseVoiceSmall int8 via sherpa-onnx, fixed 30s windows |
| `sherpa-fp32` | SenseVoiceSmall fp32 via sherpa-onnx |

## Accuracy

Corpus CER on the 1.95h AISHELL sample:

| Engine | CER | 95% CI | Δ vs whisper | Paired 95% CI | p |
|---|---:|---:|---:|---:|---:|
| whisper | 7.37% | 6.48–8.49% | — | — | — |
| paraformer (final small punc) | **3.19%** | 2.71–3.87% | **-4.14pp** | -5.13 to -3.37 | <0.00001 |
| paraformer-large-punc | 3.19% | 2.71–3.87% | -4.14pp | -5.13 to -3.37 | <0.00001 |
| sensevoice | 5.45% | 4.75–6.20% | -1.96pp | -2.91 to -1.27 | <0.00001 |
| sherpa-fp32 | 5.76% | 5.06–6.54% | -1.64pp | -2.60 to -0.93 | <0.00001 |
| sherpa (int8) | 5.82% | 5.12–6.60% | -1.58pp | -2.52 to -0.89 | <0.00001 |

The punctuation model does not change the ASR words; it only inserts punctuation. The final small-punctuation row matches the large-punctuation CER exactly and uses less memory/disk, so the large punctuation model has no accuracy benefit here.

## Resources

| Engine | RTF | Peak RSS | Model size | Notes |
|---|---:|---:|---:|---|
| whisper | 0.071 | 1.74GB | ~1.5GB | MLX/Metal; fastest |
| paraformer (final) | 0.136 | 2.81GB | ~1.25GB | CPU, one core; ~7.4x realtime |
| paraformer-large-punc | 0.142 | 2.83GB (AISHELL) / 4.16GB (p05) | ~2.1GB | Same CER; large punctuation model |
| sensevoice | 0.108 | 2.44GB | ~0.9GB | PyTorch CPU |
| sherpa (int8) | 0.018 | 0.94GB | 239MB | Lightest and fastest |

The final Paraformer configuration uses the 292MB `punc_ct-transformer_zh-cn-common-vocab272727` model instead of the 1GB `ct-punc`. CER is identical (3.19%); the small model only reduces disk and peak memory.

### Real-library speed

Final small-punctuation Paraformer, warm model load, 150s clip:

- 150s clip: 32.3s end-to-end (including about 10s model load), 57 sentence segments, RTF 0.215 including load.
- Inference alone on the 150s clip: 18.5s, RTF 0.124.
- Full p05 (6.6min): 48.4s, RTF 0.123, 2.75GB peak, 1.0 core, 144 sentence segments.
- Whisper on the same 150s clip: 8.6s, RTF 0.058, 1.24GB, 0.3 cores.
- Extrapolated 1h audio: about 7–9 minutes for Paraformer, under the 20 min/h target; whisper is about 2x faster but less accurate.

## Real library evidence

The library is the 曾仕强《道德经》lecture series. Term counts over the full transcripts:

| Item | Whisper | Paraformer |
|---|---|---|
| p05 | 孙世强×1, 除狗×5, 天地不能×1 | 曾仕强×1, 刍狗×5, 天地不仁×1 |
| p27 | no 曾仕强; hallucinated `请不吝点赞 订阅 转发 打赏…` preamble | 曾仕强×1 |
| p38 | 曾世强×2, 上德不德×3 | 曾仕强×2, 上德不德×1 |

Representative p05 opening:

- Whisper: `请关注孙世强解读道德经…天地不能以万物为除狗…圣人不能以百姓为除狗`
- Paraformer: `敬请关注曾仕强解读道德经，道德经，第五章天地不仁，以万物为刍狗圣人，不能以百姓为刍狗。`

Representative p38 opening:

- Whisper: `请继续关注曾世强解读《道德经》…上德不得`
- Paraformer: `请继续关注曾仕强解读道德经。道德经从第三十八章开始就进入了德经…上德不德`

Paraformer still makes mistakes (`土狗` once in p05, `自生之灭`, `善行无策机` in p27), so this is a large improvement rather than a perfect transcript.

## Counterexample: AISHELL alone is not enough

A 2024 Paraformer-large ONNX int8 export (`yiyu-earth/sherpa-onnx-paraformer-zh-2024-04-25`) scored **1.41% CER** on the first 10 AISHELL chunks at RTF 0.016, but on the real 道德经 audio it produced `自信关注曾是强…圣狗…自生之命`, clearly worse than the PyTorch SeACo model. It was rejected. This is why the decision uses both AISHELL CER and real-library term checks.

## Caveats

- AISHELL is read news speech; the real content is a Taiwanese-accented lecture with classical Chinese. The ranking is corroborated by the term counts, but CER on the library itself is not available without human transcripts.
- The two FunASR options are a real trade-off; SenseVoice int8 is the choice if memory or speed becomes the constraint.
- Model load is about 10s warm and dominates short clips; the follow-up warm-process change amortises it for large collections (see `.scratch/asr-warm/results.md`).
- English is transcribed correctly by Paraformer (tested with `asr_example_en.wav`), but the small punctuation model may add Chinese `。`.

## Reproduction

Raw parquet/wav, run JSON, and report JSON live under `~/Trove/cache/asr-bench/` (outside the repo). The harness is in this directory:

```bash
.venv-funasr/bin/python .scratch/asr-funasr/bench.py prepare --sample-every 5
.venv-whisper/bin/python .scratch/asr-funasr/bench.py run --engine whisper
.venv-funasr/bin/python .scratch/asr-funasr/bench.py run --engine paraformer
.venv-funasr/bin/python .scratch/asr-funasr/bench.py report
```

`real_bench.py` runs one engine over a real library item and writes the transcript, RTF, CPU cores, and peak RSS:

```bash
.venv-funasr/bin/python .scratch/asr-funasr/real_bench.py \
  --engine paraformer --audio ~/Trove/cache/asr-bench/real/p05.wav --tag p05
```

The final `report.json` is the source of the accuracy table; the Markdown above is a stable summary.
