# 03 — Host 设备认证、撤销与 CLI

Status: ready-for-agent
Type: task
Milestone: M0
Blocked by: 02
Spec: [spec.md](../spec.md)
Tech: [tech-selection.md](../tech-selection.md)
Requirements: FR-73, NFR-08
ADRs: [0009](../../../docs/adr/0009-native-android-client-app-managed-sync.md)

## Context

Android 需要长期设备 token，而不是每次输入密码或复用浏览器 Cookie。Host 必须在保留现有 Cookie 会话的同时接受 Bearer，并支持设备撤销、密码修改失效和安全的 token 存储。

## Scope

- `POST /api/auth/device-token`：密码 + 设备名换取一次性 token；沿用现有 IP 登录限速。
- token 使用 `secrets.token_urlsafe(32)`；Host 只存 SHA-256 hash；返回 `device_id` + token。
- 中间件同时接受 Cookie 和 `Authorization: Bearer`；Bearer 写请求跳过 CSRF，Cookie 仍走 Origin/Sec-Fetch-Site 校验。
- 校验 `session_epoch`；密码修改/撤销使 token 失效；返回 `auth.device_revoked`。
- `GET /api/devices`、`DELETE /api/devices/{device_id}`；`trove device list/revoke` CLI。
- `last_used_at` 最多每 5 分钟更新一次；日志不打印 token/Authorization。

## Acceptance Criteria

- [ ] 密码换 token 成功；Bearer 可访问受保护 API；错误密码返回稳定错误/限速。
- [ ] 撤销后 token 立即 401/`auth.device_revoked`；密码修改使所有设备 token 失效。
- [ ] Cookie 会话和现有登录/登出行为不回归。
- [ ] Bearer 写请求不受 Cookie CSRF 规则误伤；Cookie 写请求仍拒绝跨站。
- [ ] 设备列表/撤销 API 与 CLI 可用；token 不出现在响应、日志或异常里。

## Testing

- Host seam：token 换取、Bearer 访问、撤销、密码修改、错误 token、限速、CSRF 对照。
- 日志脱敏断言：响应/日志不出现 token 或 Authorization。
- 现有认证/安全测试保持绿。

## Out of Scope

- Android 客户端登录/存储；由 09 实现。
- LAN flavor/明文 HTTP；由 20 处理。
