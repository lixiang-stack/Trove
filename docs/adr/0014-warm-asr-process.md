# 转写进程常驻并复用模型

`ParaformerTranscriber` 之前每次转写都启动一个 `asr_worker`，在子进程里重新加载 Paraformer、VAD、标点三个模型；热缓存下一次加载约 4–6 秒，冷启动更久。批量处理 Collection 时，这部分固定开销会按 Item 数累加。本决策让一个常驻 ASR 子进程在 worker 生命周期内复用模型，空闲 10 分钟后退出。

**Status**: Accepted · 2026-11-25

## Evidence

同一进程连续转写两个 150 秒真实音频：

| | 耗时 |
|---|---:|
| 第一次（加载模型 + 转写） | 27.6s |
| 第二次（复用模型，仅转写） | 18.7s |

每次节省约 **8.9 秒**。模型路径从 ModelScope ID 改为本地 snapshot 路径后，单次加载也从 6.2s 降到 4.2s。100 个 Item 约省 7–10 分钟加载时间。

## Decision

- `ParaformerTranscriber` 持有一个常驻 `asr_server` 子进程，通过 `multiprocessing` Pipe 发送音频/输出路径并接收结果。
- 子进程只加载一次模型；请求串行处理，天然限制单 worker 的 ASR 并发为 1。
- 成功后启动 10 分钟空闲计时器；超时终止子进程，释放约 2.8GB RSS，下一次转写重新加载。
- 取消、超时、子进程崩溃时杀掉子进程并报错；下一次转写重新启动。
- 父进程退出时关闭 Pipe；子进程读到 EOF 后退出。

## Considered Options

- 继续每次启动子进程：取消/隔离最简单，但每个 Item 固定加载 4–6 秒。
- 在 worker 进程内缓存模型：少一层 IPC，但失去取消能力和崩溃隔离，一次模型异常会拖垮整个 worker。
- 独立 ASR HTTP 服务：复用最好，但增加端口、鉴权、launchd 服务、健康检查，对当前规模过度。
- 常驻子进程：保留进程隔离和取消能力，代价是空闲时占用内存，用 idle timeout 控制。

## Consequences

- 一个 worker 同时最多一个 ASR 请求；不要在同一 `~/Trove` 上跑多个 worker，否则仍会有多份模型和内存。
- 空闲 10 分钟内再次转写可直接复用；超过 10 分钟会重新加载。
- 取消或超时会丢弃已加载的模型，下一次请求重新加载。
- 子进程使用 `multiprocessing` 的 `spawn`，调用方需要有真实的模块入口（Trove CLI/worker 满足）；REPL、`python -c` 等无 `__main__` 文件的调用方式不支持。
- 见 [ADR 0013](0013-paraformer-local-asr.md)、[技术选型](../ideas/trove-tech-selection.md)。
