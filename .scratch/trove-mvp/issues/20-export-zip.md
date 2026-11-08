# 20 — 导出 zip 与 Markdown 索引

Status: ready-for-agent  
Type: task  
Milestone: M2  
Blocked by: 11, 13, 16, 17  
Spec: [spec.md](../spec.md)  
Requirements: FR-64, FR-22, NFR-03  
ADRs: [0008](../../../docs/adr/0008-content-package-as-source-of-truth.md)

## Context

内容包是本地拥有和迁移的证据。MVP 的 P1 导出需要把 Library 或 Item 子集打成 zip，包含来源元数据、音频、transcript、书文件、AI 结果和 Markdown 索引；视频 Item 只含 source.json + 音频。

## Scope

- 导出整个 Library 或选定 Item 子集；流式 zip，避免把全部内容读入内存。
- 每个 Item 目录包含 `source.json`、音频、`transcript.json`、`book.epub`/`book.json`、`ai.json`、封面（如有）。
- 视频 Item 不含视频文件，只含 `source.json` + 音频。
- `index.md`：Item 列表、来源、作者、日期、摘要、Tag、文件清单。
- 导出不修改原库；未知/未完成 Item 的处理策略（跳过或包含已完成部分）明确。
- API/HTML 导出入口；文件名/大小合理。

## Acceptance Criteria

- [ ] 导出 zip 可解压，目录结构/文件清单符合内容包约定。
- [ ] `index.md` 可读，包含来源/摘要/Tag/文件清单。
- [ ] 视频 Item 不含视频文件；本地原始文件不被移动/删除。
- [ ] 可选子集导出只包含选定 Item；未知 ID 返回稳定错误。
- [ ] 导出过程中不修改库；失败清理临时 zip。
- [ ] 导出在手机/桌面浏览器可下载。

## Testing

- Host seam：seed 音频/书/视频 Item → 导出 → 解压断言文件/内容/index.md。
- 子集/空集/未知 ID/失败清理测试。
- 大文件流式导出冒烟（不占满内存）。
- 不测试压缩算法细节，只断言内容。

## Out of Scope

- 备份/恢复 UI（P2）、独立 Markdown 导出（P2）、云同步（P2）。
- 视频文件导出；不做。
