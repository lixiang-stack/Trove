# 21 — 安全加固与攻击面测试

Status: ready-for-agent  
Type: task  
Milestone: M3  
Blocked by: 03, 05, 07, 08, 09, 11  
Spec: [spec.md](../spec.md)  
Requirements: FR-17, FR-80, FR-85, NFR-12  
ADRs: [0006](../../../docs/adr/0006-native-launchd-tailscale.md)

## Context

Host 会绑定局域网/VPN，接收用户提供的 URL、文件和 EPUB。需要在功能完成后做一次系统性安全加固，验证 SSRF、上传、文件服务、HTML 注入、认证和依赖版本。

## Scope

- SSRF：播客 feed/enclosure 的私网/回环/链路本地/元数据/CGNAT/重定向校验；视频平台白名单；无通用下载代理。
- 上传：流式大小限制、MIME/扩展名/内容校验、SHA-256、失败清理、临时目录权限。
- 文件服务：只允许 artifact 路径、防路径穿越、Range/ETag、`nosniff`、私有缓存。
- HTML：EPUB 章节 `nh3` 白名单、Jinja 自动转义、CSP 禁止远程脚本/图片、Cookie/CSRF 防护。
- 认证：限速、会话过期、Secure Cookie、密钥/session secret 权限、日志脱敏。
- 依赖：Starlette ≥0.49.1（Range DoS CVE）、其他依赖安全版本；记录许可证。
- 安全回归测试与检查清单。

## Acceptance Criteria

- [ ] 私网/元数据/回环/重定向到私网的 feed/enclosure URL 全部被拒绝。
- [ ] 超大/错误类型/损坏上传被拒绝并清理；临时目录不残留。
- [ ] 路径穿越、未知 artifact、未认证文件访问全部被拒绝。
- [ ] 恶意 EPUB HTML 的脚本/远程资源被移除；CSP 生效。
- [ ] 登录限速/会话/Cookie 属性符合 spec；日志不含密码/Cookie/Key。
- [ ] Starlette 版本不受 CVE-2025-62727 影响；依赖检查通过。

## Testing

- Host seam 安全测试：SSRF、上传、路径穿越、恶意 HTML、未认证。
- 响应头/CSP/Cookie 属性断言。
- 依赖版本检查；日志扫描敏感字段。
- 不做渗透测试/公网扫描。

## Out of Scope

- 多用户/权限模型、WAF、云端合规；不做。
- 物理设备安全、macOS 系统加固；由部署文档提示。

## Comments

2026-11-10 — Implemented the agent-side hardening: multipart uploads now validate
EPUB structure and FFprobe media streams before creating an Item; upload metadata
paths are confined to the upload directory; SSRF checks cover reserved/CGNAT/
IPv4-mapped addresses and re-validate redirects; security headers include CSP,
nosniff, frame denial, and a same-origin referrer policy. Added
`tests/test_security.py`, `docs/security.md`, and `docs/licenses.md`; pinned
Starlette `>=0.49.1`. Manual clean-Mac deployment checks remain for ticket 24/29.
