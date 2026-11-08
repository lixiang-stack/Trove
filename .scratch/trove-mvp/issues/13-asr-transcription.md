# 13 — mlx-whisper 转写与 Transcript 阅读

Status: ready-for-agent  
Type: task  
Milestone: M1  
Blocked by: 06, 07, 08, 09  
Spec: [spec.md](../spec.md)  
Requirements: FR-19, FR-22, FR-23, FR-24, FR-34, FR-37, NFR-05, NFR-07  
ADRs: [0004](../../../docs/adr/0004-mlx-whisper-local-asr.md)

## Context

转写把音频变成可读、可检索的载体。MVP 只需要分段时间戳，不需要词级时间戳；转写必须本地、Apple Silicon 加速，并在独立子进程中运行以便取消/重启。

## Scope

- `trove setup` 预下载 `mlx-community/whisper-large-v3-turbo`；检查 FFmpeg/MLX。
- macOS 14k/16k 单声道临时音频给 ASR；原始播放音频不被覆盖。
- mlx-whisper 子进程：`language=auto`、`task=transcribe`、`word_timestamps=False`、关闭 `condition_on_previous_text`、设置静音/压缩阈值。
- 输出 `transcript.json` 与 `transcript_segments`；语言、模型版本随结果保存。
- Transcribe 阶段接入 Processing Run；模型缺失/失败/取消的错误码；重试由 10 处理。
- Transcript 阅读：在 B Now Playing 内默认折叠；点击标题就地展开/收起；展开后支持分段、时间戳、文内搜索/高亮；不做点击跳转/同步滚动。

## Acceptance Criteria

- [ ] 用短音频 fixture + fake Transcriber 可完成 transcribe 阶段并写入分段。
- [ ] 真实 mlx-whisper 在 1 小时中文音频上可跑通；分段 start/end 单调且可读。
- [ ] 模型缺失时给出 `asr.model_missing` 和 setup 提示；失败/取消不产生半成品 transcript。
- [ ] B 的 transcript 默认折叠；点击就地展开/收起；展开后显示分段/时间戳，文内搜索可过滤和高亮；手机可读。
- [ ] 不做词级时间戳；不要求同步滚动。
- [ ] ASR 组件基准可被 26 调用（1 小时 ≤20 分钟）。

## Testing

- Host seam + fake Transcriber：阶段、分段、失败、取消、页面。
- 真实 mlx-whisper 集成测试标记为 `slow`/手动；不默认跑模型。
- 中文两字词在 transcript 文本中存在，供 14 搜索验证。
- 文内搜索 Playwright 冒烟。

## Out of Scope

- FTS 索引与全局搜索（14/15）。
- 词级时间戳、WhisperX 对齐、说话人分离；不做。
