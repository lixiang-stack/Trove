# 25 — Q10 一周手机播放 Spike

Status: resolved
Disposition: closed 2026-11-13 — Q10 NOT ACCEPTED; desktop consumption for MVP; V1 Android next.
Acceptance exception: Tailscale Serve acceptance is SKIPPED by user decision (2026-11-13); use Caddy HTTPS for Q10.
Type: task
Milestone: M3
Blocked by: 11, 12, 15, 24
Spec: [spec.md](../spec.md)
Requirements: FR-34, FR-87

## Context

Q10 是 MVP 的核心产品门控：手机浏览器能否承担主要听设备？需要在真实手机 + HTTPS 环境下连续使用一周，验证连续播放、后台/锁屏、倍速、进度续听和媒体通知。Host Console 不依赖 Q10；Consumer Web Shell 的消费验收依赖它。

## Scope

- 准备至少 5 条可听 Item（含 1 小时长内容），通过 Caddy HTTPS 在目标手机访问（Tailscale 验收已跳过）。
- 连续一周记录：播放/暂停/拖动/倍速、锁屏/后台、媒体通知、导航时音频是否中断、进度恢复、搜索/transcript 阅读。
- 记录失败场景、浏览器/系统版本、网络环境、复现步骤。
- 按 Q10 通过/失败给出决定：
  - 通过 → 手机浏览器作为“听”的验收设备。
  - 失败 → 消费收缩到桌面，native 播放器进入下一里程碑；或按 2 的备选换 React 表现层。

## Acceptance Criteria

- [ ] 一周内每天至少一次手机播放/续听，记录原始观察。
- [ ] 覆盖锁屏/后台/倍速/媒体通知/导航不断音/进度恢复。
- [ ] 形成 pass/fail 结论和依据；失败时明确下一步（桌面/native/React）。
- [ ] 不把 Q10 失败当成 Host Console 失败；入库/管理/搜索仍验收。
- [ ] 记录真实设备/浏览器/Caddy HTTPS 方式，便于复现。

## Testing

- 手动真实设备测试；不做自动化替代。
- 可与 26 的性能/ASR 记录交叉引用。
- 结果写入本 issue 的 `## Comments` 或 `.scratch/trove-mvp/` 下的记录文件。

## Out of Scope

- 实现 native 播放器、离线播放、Up Next、睡眠定时；不做。
- 公网访问/多用户；不做。

## Comments

2026-11-10 — Added the raw-observation template at `.scratch/trove-mvp/archive/q10-log.md`
(environment, seven daily rows, failure cases, pass/fail decision). No device data
has been fabricated; the week-long phone spike remains human work.

2026-11-13 — Tailscale 验收跳过；Q10 仍使用 Caddy HTTPS 执行，不因 Tailscale 跳过而取消手机播放门控。

2026-11-13 — 用户决定关闭 Q10 为“未通过/未接受”，不执行一周 spike。依据：Tailscale 路径不可用，Caddy 未安装；此前的真机 PWA 验收已暴露播放稳定性、状态同步和移动端布局问题（PWA-1..PWA-7）。按需求文档的产品预案，MVP 消费收缩到桌面浏览器，移动端播放交给 V1 Android；这不是 Host Console 的失败。
