# 转写使用 mlx-whisper large-v3-turbo

MVP 在 M1 Pro 上要求 1 小时视频端到端 <30 分钟，中文优先、英文可转写，且不需要词级时间戳。选择 Apple Silicon 原生的 mlx-whisper 0.4.x + `mlx-community/whisper-large-v3-turbo`，在独立子进程中运行；FFmpeg 抽取 64kbps 单声道 AAC 用于播放，视频不落盘。

**Status**: Accepted · 2026-11-08

## Considered Options

- faster-whisper：CPU/CUDA 友好，但 macOS 无 Metal 加速；不作为首选。
- WhisperX：词级对齐/说话人分离不是 MVP 需求，依赖更重。
- SenseVoice/FunASR、whisper.cpp：作为中文质量/速度不达标时的回退。
- 云端 ASR：隐私、成本和离线约束不符 MVP；后续云端可替换适配器。

## Consequences

- MVP 主机锁定 Apple Silicon；模型约 1.6GB，首次 `trove setup` 预下载。
- 转写阶段没有百分比进度，只有阶段状态 + 已用时间；取消/重启按阶段处理。
- 端到端 <30 分钟是门控；ASR 组件目标 ≤20 分钟，给下载/整理/索引留余量。
- 见 [技术选型](../ideas/trove-tech-selection.md) 第 3.4、6、7 节；需求 FR-18/19/22/23/24、NFR-05/06。
