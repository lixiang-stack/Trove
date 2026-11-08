# 08 — 本地音频/视频与 EPUB 入库

Status: ready-for-agent  
Type: task  
Milestone: M0  
Blocked by: 05, 06, 07  
Spec: [spec.md](../spec.md)  
Requirements: FR-02, FR-03, FR-07, FR-14, FR-15, FR-85

## Context

用户还需要添加 Mac 上的本地音频/视频和 EPUB。复制音频/EPUB 进库但不动原文件；本地视频只保留路径和抽出的音频；上传必须有类型/大小限制和 SHA-256 去重。

## Scope

- 手机上传：流式落临时文件，边写边算 SHA-256，限制视频 4GB/音频 500MB/EPUB 100MB（可配）。
- 桌面 host path：校验存在/可读/类型；不复制视频，只抽取音频。
- 本地音频：复制进库；浏览器不支持格式转码为 `audio.m4a`。
- 本地视频：保留 `source_path`，FFmpeg 抽音频，库内不存视频。
- EPUB：校验 zip/mimetype 和基本结构，复制原件进库，创建 Run；完整解析留给 16。
- 去重：本地文件按 SHA-256；重复添加返回已存在。
- 失败清理临时文件；不删除用户原文件。

## Acceptance Criteria

- [ ] 上传音频/EPUB 后生成 Item、内容包文件和 `queued` Run；原文件保持不变。
- [ ] 添加本地视频后只存在来源路径 + `audio.m4a`，库内没有视频副本。
- [ ] 超过大小/类型限制的上传被拒绝，临时文件被清理。
- [ ] 同一文件第二次添加返回已存在，不重复复制/处理。
- [ ] 不支持的音频格式被转码，可被播放器读取。
- [ ] EPUB 非 DRM/可重排的校验在入库阶段给出明确结果；解析/阅读由 16 完成。

## Testing

- Host seam：上传音频/EPUB、host path 视频、重复文件、超限文件。
- 真实 FFmpeg fixture：本地音频复制/转码、视频抽音频。
- 路径安全：不存在/不可读/目录路径被拒绝。
- 移动端上传进度冒烟。

## Out of Scope

- EPUB 章节/阅读器；由 16 实现。
- 播客 feed；由 09 实现。
- 转写/整理/索引；由 13/17/14 接入。
