# 22 — V1 验收总检查

Status: ready-for-agent
Type: task
Milestone: M3
Blocked by: 14, 15, 17, 19, 20, 21
Spec: [spec.md](../spec.md)
Tech: [tech-selection.md](../tech-selection.md)
Requirements: FR-69, FR-70, FR-71, FR-72, FR-73, NFR-11
ADRs: [0009](../../../docs/adr/0009-native-android-client-app-managed-sync.md)

## Context

所有 V1 功能和硬化完成后，需要一次总验收：自动化套件、真实 Xiaomi 13 + Host、同步/离线/播放/阅读/搜索闭环、已知问题和放行结论。这个 issue 不引入新功能。

## Scope

- 自动化：Host 测试、Android JVM/Compose 测试、lint、docs check；instrumented/真机结果记录。
- 真机 + 真实 Host（Caddy 或 Tailscale HTTPS）：
  - 分享链接 → Host 处理 → 下载 → 飞行模式播放 ≥60 分钟 → 锁屏/通知/蓝牙/倍速/续听。
  - 下载 EPUB → 离线阅读/翻章/图片/脚注/书内搜索/位置恢复。
  - 离线搜索已下载内容，中文两字词命中；打开 transcript/书匹配段落。
  - 离线改 Tag/进度/完成状态 → 重连同步 → Web/另一设备 canonical。
  - Host 删除 → 手机 tombstone 删除；重新添加复活；重装恢复 Library/进度。
  - 下载中断/续传/sha 校验/配额不足；token 撤销；密码修改。
  - Caddy/Tailscale 连接、用户 CA、release/lan flavor 行为。
- 记录已知问题、限制、未达标项和 follow-up；给出 RELEASE/BLOCKED 结论。

## Acceptance Criteria

- [ ] 自动化套件全绿；Android/Host 文档检查通过。
- [ ] 真机闭环全部 PASS，或有明确例外/后续 issue。
- [ ] 同步冲突/重装/删除/撤销无数据丢失或静默覆盖。
- [ ] 性能：本地 1k 搜索 p95 <1s；首同步/播放/下载可接受。
- [ ] 安全：HTTPS/token/备份/日志/EPUB 恶意输入检查 PASS。
- [ ] 无未声明的 P2/P3 功能进入 V1。
- [ ] 形成 V1 release decision 和已知问题清单。

## Testing

- 运行 Host/Android 自动化；真实设备手动验收记录证据。
- 不使用模拟器替代真机后台播放/媒体通知。
- 失败项开 follow-up，不在本 issue 内扩展范围。

## Out of Scope

- 新功能；发现缺口另开 issue。
- Play Store 上架、云端、多用户、iOS、PDF/TTS/标注/语义检索。
