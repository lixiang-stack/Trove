# 29 — MVP 验收总检查

Status: resolved
Disposition: released desktop MVP with exceptions 2026-11-13; see `../acceptance.md`.
Acceptance exception: all PWA and Tailscale Serve acceptance items are SKIPPED by user decision (2026-11-13); they are not release gates.
Type: task
Milestone: M3
Blocked by: none
Spec: [spec.md](../spec.md)
Requirements: 需求文档 9.1–9.5

## Context

所有实现和专项评估完成后，需要一次总验收：跑自动化套件、核对 MVP P0/P1 范围、记录已知问题，并确认 Q10 的结论。这个 issue 不引入新功能，只做验收和放行判断。

## Scope

- 自动化：`pytest`（默认不跑网络）、Playwright、`ruff`、`mypy`、`python3 scripts/check-docs.py`。
- 范围核对：MVP P0 + P1 短名单逐项对照实现/验收证据；P2/P3 未偷偷进入。
- 手动门控引用：25 Q10、26 性能/存储、27 搜索评估、28 来源/Tag 质量。
- 安全/运维：认证、SSRF、上传、路径穿越、CSP、launchd、重启恢复；Tailscale/PWA 验收跳过。
- 记录已知问题、限制、未达标项和后续 issue；不把失败藏在“完成”里。

## Acceptance Criteria

- [x] 自动化套件全绿；默认不访问网络；文档检查通过。
- [x] P0/P1 每项有实现/测试/手动验收证据；没有未声明的 P2/P3 功能。
- [x] Q10 结论明确：通过 → 手机作为听验收；失败 → 桌面/native/React 下一步明确。
- [x] 性能/存储/搜索/来源/Tag 指标有记录；不达标项有行动 issue。
- [ ] 安全/部署检查通过；重启/取消/续跑无回归。安全 PASS；launchd/Caddy 部署验收作为例外 deferred。
- [x] 形成 MVP 放行/阻塞结论，供 PR/下一里程碑使用。

## Testing

- 运行全部自动化测试和检查。
- 逐项核对 spec 与需求文档的验收标准。
- 不新增功能；发现问题只记录或开新 issue，不在本 issue 内扩展范围。

## Out of Scope

- V1 Android、离线、同步、云端、PDF/TTS/标注/语义检索/Topic；不做。
- 新功能；发现缺口另开 issue。

## Comments

2026-11-10 — Added the release checklist at `.scratch/trove-mvp/acceptance.md`
(automated gates, manual gates, P1 evidence, known issues, release decision). The
full local suite currently passes (`./scripts/check.sh`, 313 tests including
FFmpeg and Playwright; docs check passes). Q10, performance, search, and
source/Tag evidence remain pending, so the release decision is not yet made.

2026-11-13 — 用户决定：所有 PWA 和 Tailscale Serve 验收项标记为 SKIPPED，不作为 MVP 放行门控；其余验收继续。

2026-11-13 — 收口为“桌面 MVP 放行，带例外”。自动化 `./scripts/check.sh --full` PASS（323 tests，56 docs）；21/22 手工验收 PASS；26 有真实 15 分钟样本和 1k seed 搜索证据；Q10 关闭为未通过（桌面消费，V1 Android 接手）；27/28 转 V1 backlog；PWA/Tailscale 跳过；launchd/Caddy 部署验收 deferred。详细记录见 `../acceptance.md`。23–28 及模板归档到 `../archive/`。
