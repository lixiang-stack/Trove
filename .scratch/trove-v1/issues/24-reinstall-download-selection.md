# 24 — 重装后恢复下载选择

Status: ready-for-agent
Type: task
Milestone: M3
Blocked by: 19
Spec: [spec.md](../spec.md)
Tech: [tech-selection.md](../tech-selection.md)
Requirements: FR-73
ADRs: [0009](../../../docs/adr/0009-native-android-client-app-managed-sync.md)

## Context

票 19 要求重装 App 登录后恢复 Library/进度/下载选择。当前契约只恢复 Library 和
State；下载选择是纯本地 Artifact 状态，`allowBackup=false` 后无法跨重装恢复。
本次验收按“重装后重新选择下载”记录为例外并开此 follow-up。

## Scope

- 先决定选择保存在 Host 还是设备级设置；若放 Host，需要新增 additive 字段/端点和
  manifest/state 契约，不在原 V1 API 表内。
- 登录/首同步后恢复已选 Item；文件按 sha256 重新下载。
- 保留“移除下载只清本地、删除 Item 才走 Host soft delete”的语义。

## Acceptance Criteria

- [ ] 契约/ADR 明确下载选择的持久化位置和冲突规则。
- [ ] 重装 + 登录后恢复 Library/进度/已选下载集合。
- [ ] 文件可重新下载，sha256 校验通过。
- [ ] 未选择或已移除的 Item 不会自动下载。

## Testing

- Host seam：选择写入/读取/幂等/撤销。
- Android App seam：重装、首同步、自动重下、移除选择。
- 真机：卸载重装并登录。

## Out of Scope

- 整库自动下载；V1 仍只做选择性同步。
