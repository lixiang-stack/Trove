# ASR replacement: FunASR / SenseVoice bake-off

Status: research complete, integration proposed

## Problem

Trove currently transcribes with `mlx-whisper` + `mlx-community/whisper-large-v3-turbo`.
On the real Chinese library it makes domain-visible errors (wrong names and
classical terms), for example:

- `曾仕强` → `孙世强` / `曾世强`
- `天地不仁` → `天地不能`
- `刍狗` → `除狗`

The user asked for a local replacement with **higher transcription accuracy**
and **lower resource usage**, trying FunASR first.

## Candidates

| Candidate | Runtime | Why |
|---|---|---|
| mlx-whisper large-v3-turbo | MLX / Metal | Current baseline |
| FunASR SenseVoiceSmall fp32 | PyTorch CPU | Reference implementation of the proposed model |
| FunASR Paraformer-zh fp32 + ct-punc | PyTorch CPU | Chinese-specialised FunASR model with punctuation |
| SenseVoiceSmall int8 | sherpa-onnx CPU | Deployment candidate: same weights, ONNX int8, no PyTorch |
| SenseVoiceSmall fp32 | sherpa-onnx CPU | Quantisation ablation |
| Qwen3-ASR | deferred | LLM decoder; not part of the first FunASR trial |

## Evaluation protocol

### Accuracy set

- AISHELL-1 test split (`AudioLLMs/aishell_1_zh_test`), human transcripts.
- Deterministic sample: every 5th utterance, 1,384 utterances / 1.95 h /
  20,326 reference characters.
- 30 s chunks (whole utterances concatenated with 200 ms silence) so long-form
  throughput is measured without per-file padding artefacts.
- Corpus CER after normalisation: strip model tags/punctuation, NFKC,
  traditional → simplified (`zhconv`), Chinese numerals → Arabic (`cn2an`),
  keep letters/numbers only.
- 5,000-sample bootstrap 95% CI over chunks; paired bootstrap of the per-chunk
  CER difference against whisper.

### Resource set

- Same AISHELL chunks for wall time / RTF / peak RSS.
- Real Trove audio (`p05`, `p27`, `p38`) for qualitative domain checks and
  long-form VAD behaviour. These have no human reference, so they do not
  contribute to CER.

### Recorded metrics

- CER, substitutions/deletions/insertions, sentence exact match, share of
  chunks with CER > 50%.
- Model load time, inference time, end-to-end RTF, peak RSS, model size.
- Known-term errors on the real library (manual inspection).

## Acceptance criteria

1. CER is lower than mlx-whisper, with a paired-bootstrap 95% CI that excludes
   zero.
2. RTF is no worse than mlx-whisper on the same long-form audio.
3. Peak RSS is no higher than mlx-whisper.
4. Model download size is no larger than mlx-whisper.
5. Output keeps segment start/end timestamps and supports Chinese + English.
6. `trove setup`, `trove doctor`, failure hints, and tests are updated.

## Decision rule

If SenseVoice int8 meets all criteria, ship sherpa-onnx int8. If int8 accuracy
is materially worse than fp32, use fp32. If neither beats whisper, revisit
Fun-ASR-Nano or Qwen3-ASR before changing the default.

## Decision

The user chose accuracy-first after reviewing the trade-off: ship **FunASR
Paraformer-zh + FSMN-VAD + small CT-Transformer punctuation**, not SenseVoice.
SenseVoice int8 remains documented as the resource-first alternative.
