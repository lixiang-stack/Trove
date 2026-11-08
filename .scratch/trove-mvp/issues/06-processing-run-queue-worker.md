# 06 — Processing Run 队列、Worker 与状态机

Status: ready-for-agent  
Type: task  
Milestone: M0  
Blocked by: 02, 04, 05  
Spec: [spec.md](../spec.md)  
Requirements: FR-08, FR-09, FR-12, FR-13, FR-22, FR-78, FR-83, NFR-04, NFR-13  
ADRs: [0001](../../../docs/adr/0001-python-monolith-sqlite-worker.md), [0008](../../../docs/adr/0008-content-package-as-source-of-truth.md)

## Context

Processing Run 是把 Source 变成可消费产物的执行单元。需要持久化队列、阶段状态、单 worker 领取、失败分类和状态展示；先把引擎和状态机建好，具体下载/转写/整理适配器由后续 issue 接入。

## Scope

- `runs` / `run_steps` 的创建、领取、阶段推进、失败记录；一个 Item 一个当前 Run。
- 状态序列：视频/播客 `queued → downloading → extracting_audio → transcribing → organizing → indexing → completed`；本地文件对应阶段；EPUB `extracting_text → organizing → indexing`。
- Worker 循环：轮询、原子领取、心跳、执行阶段、阶段边界检查取消标记；默认并发 1。
- 阶段端口：`Downloader`、`AudioExtractor`、`Transcriber`、`Organizer`、`BookExtractor`、`SearchIndex`；本 issue 用 fake 实现验证编排。
- 失败分类与稳定错误码；每个 Run 独立日志 tail；状态 API/HTML；artifact 原子写入。
- 失败不阻塞已有产物：已有音频/文本仍可播放/阅读。

## Acceptance Criteria

- [ ] 用 fake 阶段可以把一个 Run 从 `queued` 推到 `completed`，阶段顺序和状态正确。
- [ ] 任一阶段失败后 Run 为 `failed`，记录错误码/原因和阶段；不会无限重试。
- [ ] 同一 Run 不会被两个 worker 重复领取；单 worker 时一次只处理一个。
- [ ] 状态 API/HTML 显示当前阶段、失败原因和日志 tail；完成后停止轮询。
- [ ] 阶段输出先临时文件再原子 rename；崩溃不会留下被当作完成的半成品。
- [ ] 已有 artifact 在后续阶段失败时仍可被读取。

## Testing

- Host seam：fake 阶段 → 状态推进/失败/日志/artifact。
- 并发领取测试：两个 worker 竞争同一 Run 只有一个成功。
- 原子写入测试：模拟阶段中途失败，完成态不可见。
- 不测试内部 SQL 或调用顺序，只断言 API/HTML/Run 状态/文件。

## Out of Scope

- 重试/续跑/取消/重启回收；由 10 实现。
- 真实 yt-dlp/FFmpeg/ASR/DeepSeek/EPUB 适配器；由 07–09、13、16、17 接入。
