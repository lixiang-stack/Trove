# 转写使用 FunASR Paraformer-zh

MVP 的中文转写质量是主要短板：`mlx-whisper` + `whisper-large-v3-turbo` 在真实《道德经》讲座上把“曾仕强”写成“孙世强/曾世强”，把“刍狗”写成“除狗”，把“天地不仁”写成“天地不能”。本轮用 AISHELL-1 测试集和真实库音频量化比较后，默认改为 FunASR 的 `Paraformer-zh`（SeACo-Paraformer-large）+ `fsmn-vad` + 小标点模型，在独立子进程中运行。准确率优先；资源占用高于 whisper，但仍在本机可接受范围内。

**Status**: Accepted · 2026-11-24

## Evidence

AISHELL-1 test 的确定性 1.95 小时样本（214 个 30 秒片段，20,326 个参考字），文本归一化后计算 corpus CER；配对 bootstrap 以 whisper 为基线：

| 方案 | CER | 相对 whisper | RTF | 峰值 RSS | 模型体积 |
|---|---:|---:|---:|---:|---:|
| mlx-whisper large-v3-turbo（旧） | 7.37% | — | 0.071 | 1.74GB | ~1.5GB |
| FunASR Paraformer-zh + 小标点 | **3.19%** | **-4.14pp**（95% CI -5.13 ~ -3.37） | 0.136 | 2.81GB | ~1.25GB |
| FunASR SenseVoiceSmall fp32 | 5.45% | -1.96pp | 0.108 | 2.44GB | ~0.9GB |
| SenseVoiceSmall int8（sherpa-onnx） | 5.82% | -1.58pp | 0.018 | 0.94GB | 239MB |

真实库抽检（p05/p27/p38，人工听感不可用时以术语和上下文核对）：

- `曾仕强`、`天地不仁`、`刍狗`、`上德不德` 在 Paraformer 输出中基本正确；whisper 上述术语多处错误。
- Paraformer 仍会错写个别字词（如“自生之灭”“善行无策机”），但整体可读性和术语一致性明显优于 whisper。
- 仅看 AISHELL CER 会误导：2024 版 Paraformer ONNX 在 10 个 AISHELL 片段上 CER 只有 1.4%，但在真实讲座上明显劣化，因此未采用。

完整协议和结果见 `.scratch/asr-funasr/`。

## Considered Options

- 继续用 mlx-whisper：速度最快，但真实内容术语错误多，用户已明确认为效果不好。
- SenseVoiceSmall int8（sherpa-onnx）：资源最省（0.94GB、55x 实时、239MB），准确率仍优于 whisper；但“曾仕强”常写成“曾世强”，人名稳定性不足。
- 2024 版 Paraformer ONNX：资源省、AISHELL CER 低，但真实讲座输出明显劣化，排除。
- Qwen3-ASR 0.6B/1.7B：LLM 解码器，Mac 上需额外 MLX/ONNX 适配；本轮 FunASR 已达标，暂不引入。
- Paraformer-zh（PyTorch）：准确率最高、术语最稳，选为默认。

## Consequences

- `asr` extra 变为 `funasr` + `modelscope` + `torch` + `torchaudio`；安装体积和首次下载明显大于 mlx-whisper。
- 子进程峰值内存约 2.8GB，CPU 单核、约 7.4x 实时；1 小时音频约 8 分钟，仍满足原 20 分钟/小时目标。
- 模型加载开销已由 [ADR 0014](0014-warm-asr-process.md) 的常驻 ASR 子进程处理：首个 Item 加载，后续复用，空闲 10 分钟释放。
- 标点使用中文小模型；英文可转写，但英文标点可能仍是中文句号。
- `trove setup` 从 ModelScope 下载 ASR、VAD、标点三个模型；`trove doctor` 检查 `funasr` 和三份缓存。
- 已补 ASR-only 重跑入口：Item 页面“重新转写（不重新下载）”，或 `trove collection reprocess <collection_id> --from-stage transcribing`。
- 人工抽检仍有错字；若后续对准确率要求继续提高，优先评估 Qwen3-ASR 或领域热词/后处理，而不是回退 whisper。
- 见 [技术选型](../ideas/trove-tech-selection.md) 第 3.4、6、7 节；需求 FR-18/19/22/23/24、NFR-05/06。
