# 14 — ASR 运行时基准：FunASR vs sherpa-onnx/ONNX

Status: ready-for-agent
Type: research
Milestone: P4
Blocked by: none
Spec: [spec.md](../spec.md)
ADRs: [0013](../../../docs/adr/0013-paraformer-local-asr.md)

## Context

当前 ASR 是 FunASR Paraformer-zh + PyTorch，参考机约 7–8x realtime、峰值 RSS 约 2.8GB，首次加载模型有冷启动。产品化后，如果内存/启动/部署体积成为瓶颈，换运行时（sherpa-onnx/ONNX Runtime/whisper.cpp）可能比换语言或拆服务收益更大。需要用真实音频数据决定，而不是凭感觉。

## Scope

- 建立可复现基准，至少比较：
  - 当前 FunASR Paraformer-zh（VAD + punc）。
  - sherpa-onnx 的 Paraformer（或等价中文模型）。
  - 可选：ONNX Runtime / faster-whisper / whisper.cpp，作为对照。
- 音频集：3–5 条真实中文音频，覆盖短（<2 min）、中（10–20 min）、长（>60 min）；统一 16k mono WAV；保留原始来源说明。
- 指标：
  - RTF（音频秒 / 处理秒）、首段延迟、冷启动时间。
  - 峰值 RSS、模型磁盘占用、CPU 使用率。
  - 中文 CER/WER（人工校对或现有 golden transcript）、标点质量、时间戳可用性。
  - 安装/构建复杂度、许可证。
- 复用 `.scratch/asr-funasr/bench.py` 或新增脚本；输出 JSON/CSV + Markdown 报告。
- 报告放 `.scratch/productization/asr-runtime-benchmark.md`；给出“保持 FunASR / 迁移某运行时 / 需要更多数据”的明确建议。
- 如果建议迁移，另开实现 issue；本 issue 不改生产代码。

## Acceptance Criteria

- [ ] 基准脚本可从干净 checkout 复现；命令、版本、模型 hash 写入报告。
- [ ] 每条音频都有 RTF、峰值 RSS、CER/WER、冷启动数据。
- [ ] 对比表包含质量、性能、内存、安装复杂度、许可证。
- [ ] 报告明确回答：是否值得替换 FunASR；如果不值得，触发条件是什么。
- [ ] 不修改生产依赖或默认模型。
- [ ] 报告链接回 spec 和 ADR-0013。

## Testing

- 脚本在参考机上跑通；输出可解析。
- 至少一条音频用两种运行时跑完，确认指标口径一致。
- 人工抽查转写文本，避免只看速度不看质量。

## Out of Scope

- 生产迁移、模型打包、GPU 集群。
- Go 重写；如果新运行时提供 Go 绑定，只作为报告附录。
- 多语言 ASR 质量评估；先聚焦中文。

## Notes

- 质量优先于速度：如果 CER 明显变差，性能收益不算通过。
- 冷启动要区分“进程启动 + 模型加载”和“首次推理”。
- 许可证要记录（FunASR/ModelScope、sherpa-onnx、模型权重），产品分发前需要合规确认。
