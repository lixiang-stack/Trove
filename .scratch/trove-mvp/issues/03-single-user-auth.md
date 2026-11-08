# 03 — 单用户认证与会话

Status: ready-for-agent  
Type: task  
Milestone: M0  
Blocked by: 01  
Spec: [spec.md](../spec.md)  
Requirements: FR-76, FR-80, NFR-12  
ADRs: [0006](../../../docs/adr/0006-native-launchd-tailscale.md)

## Context

Host 会绑定到局域网/VPN，必须默认拒绝未认证操作。MVP 只有一个用户，不需要注册、角色或多用户；需要密码哈希、会话、登录限速和基础 CSRF 防护。

## Scope

- `trove auth set-password`：Argon2id 哈希写入配置（0600），不保存明文。
- 登录/登出 HTML 与 JSON 路由；签名 Cookie（HttpOnly、SameSite=Lax、HTTPS 时 Secure，30 天）。
- 认证依赖：未认证 API 返回 401，未认证 HTML 跳转登录。
- 登录失败按 IP 限速（如 5 次/5 分钟）；成功后重置。
- 写操作校验 Origin/Sec-Fetch-Site；不使用 GET 改状态。
- session secret 随机生成并持久化；日志不打印 Cookie/密码。

## Acceptance Criteria

- [ ] 首次运行未设置密码时，管理页面提示先执行设置密码命令。
- [ ] 正确密码登录成功；错误密码失败且不泄露用户是否存在。
- [ ] 未认证访问受保护 API 返回 401，访问 HTML 跳转登录页。
- [ ] 登出后旧 Cookie 失效；会话在服务重启后仍有效。
- [ ] 登录失败限速生效；HTTPS 下 Cookie 带 Secure。
- [ ] 配置文件和 `.env` 权限为 0600。

## Testing

- Host seam：未认证/登录/错误密码/登出/会话持久化。
- 限速测试：连续失败后返回 429，成功后重置。
- 脚本检查日志和响应中不含密码、Cookie、session secret。
- `python3 scripts/check-docs.py` 通过。

## Out of Scope

- 多用户、注册、OAuth、设备 token、权限角色。
- Tailscale/HTTPS 的实际部署；由 24 实现。
