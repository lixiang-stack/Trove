# 06 — 内容包 manifest 与 schema_version

Status: ready-for-agent
Type: task
Milestone: P1
Blocked by: none
Spec: [spec.md](../spec.md)
ADRs: [0008](../../../docs/adr/0008-content-package-as-source-of-truth.md)

## Context

内容包是事实源，但每个 Item 目录只有固定文件名和 JSON 文档，没有包级 manifest 或 `schema_version`。长期升级、导出/导入、跨版本读取时，只能靠字段存在性猜版本；`_extra_fields` 能保留未知字段，但不能表达“这个包按哪版布局写入”。

## Scope

- 为每个 Item 目录新增 `manifest.json`：
  - `schema_version`（初始 `1`）、`item_id`、`created_at`、`updated_at`。
  - `artifacts`：`kind`、`path`、`sha256`、`size`、`mime`，与 `Artifact` 表一致。
- `ContentPackage` 增加 `read_manifest` / `write_manifest`；在安装/替换/删除 artifact、写入 transcript/book/ai 后刷新 manifest。
- 读取时：
  - manifest 存在：校验 `schema_version`；不兼容返回 `storage.package_version`，不静默降级。
  - manifest 缺失：保持现有读取行为（兼容旧包）；新写入时补 manifest。
- 导出：`export` 生成的 zip 包含每个 Item 的 manifest；导入/恢复路径如果存在，按 manifest 校验。
- 增加 `trove package verify <item_id>` 或等价 CLI：比对文件存在性、大小、sha256；不通过返回非零。若成本过高，先只做 manifest 读取和导出，verify 放到后续。
- 不改变现有文件名、目录结构、JSON 文档字段。

## Acceptance Criteria

- [ ] 新 Item 完成后目录里有 `manifest.json`，contents 与 `Artifact` 表一致。
- [ ] 旧 Item（无 manifest）仍能 list/read/play/search/export；下一次写入后补上 manifest。
- [ ] manifest `schema_version` 不兼容时返回稳定 `storage.package_version`，错误信息可读。
- [ ] 替换音频/封面、重写 transcript/book/ai 后 manifest 的 sha256/size 更新。
- [ ] 导出 zip 包含 manifest；现有 `test_export.py` 扩展后通过。
- [ ] 内容包布局测试、host seam、搜索重建保持绿。
- [ ] `ruff`、`mypy` 通过。

## Testing

- 单测：manifest round-trip；未知字段保留；版本不匹配；artifact 替换后刷新。
- 兼容：构造无 manifest 的旧 Item 目录，读取/导出/重建索引。
- 集成：host seam 完成一条视频/EPUB，断言 manifest 与 artifact 表一致。
- 导出：zip 内 manifest 存在且 JSON 可解析。

## Out of Scope

- 全量回填所有历史 Item 的 manifest；按需惰性写入即可。
- 校验所有文件的 sha256（可作为后续 `package verify` issue）。
- 改变 `source.json`/`transcript.json`/`book.json`/`ai.json` 的字段或布局。
- 对象存储迁移。

## Notes

- manifest 是“包级索引”，不是新的事实源；文件内容仍以实际文件为准。
- 写入顺序保持“先临时文件、再原子 rename”，manifest 最后刷新，避免指向半写文件。
- 如果 `export` 当前直接遍历目录，确保 manifest 不会被遗漏或重复。
