# 18 — Android 设置、同步状态与存储管理

Status: ready-for-agent
Type: task
Milestone: M2
Blocked by: 09, 10, 12
Spec: [spec.md](../spec.md)
Tech: [tech-selection.md](../tech-selection.md)
Requirements: FR-73, NFR-11
ADRs: [0009](../../../docs/adr/0009-native-android-client-app-managed-sync.md)

## Context

手机需要可控的同步/下载行为和可解释的存储占用。设置页要能改 Host、查看设备、控制同步频率/Wi-Fi/充电、设置配额、清理下载、查看诊断；错误和离线状态要可见。

## Scope

- Settings：Host 地址、账号/设备、登出/清除数据。
- 同步：周期开关/间隔（系统允许范围）、手动刷新、上次成功/错误码。
- 下载：Wi-Fi/充电约束、存储配额、占用/可清理空间、移除下载。
- 电池优化引导（系统设置页）；通知权限状态。
- 诊断：API 版本、Host URL 脱敏、cursor 状态、下载队列、错误码；不含 token/password/Cookie/完整路径。
- 全局同步状态条：Idle/Syncing/Offline/Error。
- 清除本地数据需确认；登出默认保留下载。

## Acceptance Criteria

- [ ] 设置持久化；Host URL/设备信息/同步状态正确。
- [ ] 配额/约束生效；移除下载释放空间且保留 Host Item。
- [ ] 同步失败/离线有可见状态和重试；上次成功时间正确。
- [ ] 诊断信息脱敏；token/password/Cookie/完整路径不出现。
- [ ] 登出/清除数据行为符合确认语义。
- [ ] 电池优化/通知权限入口可用。

## Testing

- App seam：设置持久化、配额/约束、移除下载、诊断脱敏、登出/清除。
- 真实设备：通知权限、电池优化设置页、存储占用。

## Out of Scope

- Play Store 设置/账号体系。
- 多 Host/多用户。
