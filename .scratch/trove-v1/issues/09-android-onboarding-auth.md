# 09 — Android 连接、登录与设备 token

Status: ready-for-agent
Type: task
Milestone: M0
Blocked by: 03, 08
Spec: [spec.md](../spec.md)
Tech: [tech-selection.md](../tech-selection.md)
Requirements: FR-73, NFR-08
ADRs: [0009](../../../docs/adr/0009-native-android-client-app-managed-sync.md)

## Context

手机第一次打开 App 需要配置 Host 地址、用密码换设备 token，并把 token 安全保存；之后所有 API/媒体请求都用 Bearer。token 被撤销或密码修改时，App 要回到登录而不是无限重试。

## Scope

- Host URL 输入/校验：正式 release 必须 HTTPS；去掉尾部 `/`；不要求路径前缀。
- 登录页：Host 地址 + 密码 + 设备名；调用 `POST /api/auth/device-token`。
- TokenStore：Android Keystore AES-GCM 加密 token，密文/IV 存 DataStore；不使用 EncryptedSharedPreferences。
- OkHttp 拦截器加 `Authorization: Bearer`；登录/健康检查不带 token。
- 401/`auth.device_revoked` 清 token、停止同步、回登录；本地下载保留。
- 设备信息/撤销入口（调用 Host devices API）；登出撤销当前设备。
- 明确错误：密码错、token 失效、Host 离线、TLS 不受信、明文 URL 被拒绝。
- 不实现 LAN flavor；由 20 处理。

## Acceptance Criteria

- [ ] 正确密码登录成功并进入 App；Host URL/token 重启后保留。
- [ ] 错误密码/限速/Host 离线/TLS 错误显示可读提示；不崩溃、不丢本地数据。
- [ ] token 撤销或密码修改后下一次请求回登录；不无限重试。
- [ ] 明文 HTTP Host 在正式 release 被拒绝。
- [ ] 登出撤销 token；清除本地数据是单独确认动作。
- [ ] token 不出现在日志/诊断/UI 明文。

## Testing

- App seam：正确/错误登录、token 持久化、401 回登录、Host 离线、明文拒绝。
- Keystore 加密/解密单元测试（Robolectric）；日志脱敏断言。
- 不依赖真实网络；用 fake API/MockWebServer。

## Out of Scope

- Library/同步/播放/下载；由 10–13 实现。
- LAN flavor/证书安装引导；由 20 实现。
