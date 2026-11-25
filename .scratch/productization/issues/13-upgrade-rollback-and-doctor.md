# 13 — 升级/回滚、doctor --json 与发布检查

Status: ready-for-agent
Type: task
Milestone: P3
Blocked by: 11
Spec: [spec.md](../spec.md)

## Context

当前升级依赖文档里的 `git pull` + `uv sync` + `trove db upgrade` + `launchctl kickstart`；`trove doctor` 只输出人类可读文本，没有稳定 JSON；没有发布检查清单和回滚演练。产品化后需要让用户和自动化都能判断“能不能升级/怎么回滚”。

## Scope

- `trove doctor --json`：
  - 输出稳定 schema：`ok`、`checks[]`（`name`、`status`、`message`、`fix`）、`versions`（trove/python/ffmpeg/yt-dlp/sqlite/asr model）。
  - 覆盖：目录权限、DB revision、FTS5、FFmpeg/ffprobe、yt-dlp、ASR 模型、端口、worker 心跳、磁盘空间。
  - 人类可读模式保持现有输出；JSON 模式退出码与 `ok` 一致。
- 升级：
  - `trove db upgrade` 前自动做 SQLite 备份（或明确提示备份命令）；失败时保留备份并给出回滚命令。
  - 文档写清发布流程：版本 bump、changelog、迁移测试、镜像 tag、launchd kickstart、Docker pull。
- 回滚：
  - 文档写清“停 worker → 恢复 DB 备份 → 切回上一镜像/checkout → 启动”的步骤。
  - 内容包向后兼容；manifest schema_version 不兼容时拒绝启动并提示。
- `GET /api/health` 增加构建信息（version/commit/build time），保持现有字段。
- 发布检查清单加入 `docs/deployment.md`；可选脚本 `scripts/release-check.sh` 做只读检查。

## Acceptance Criteria

- [ ] `trove doctor --json` 输出可被 `jq` 解析；schema 在文档中列出。
- [ ] 缺 FFmpeg/模型/迁移时 JSON 仍完整输出，`ok=false`，退出码非零。
- [ ] 升级前备份可用；迁移失败可用备份回滚。
- [ ] 在临时 `TROVE_HOME` 上从上一版本 DB 升级到 head，doctor 通过。
- [ ] 回滚演练：恢复备份后 worker 能启动，旧内容包可读。
- [ ] `/api/health` 新增字段不破坏现有 Android/CLI 解析。
- [ ] 发布检查清单和回滚步骤写入 `docs/deployment.md`。
- [ ] 现有 deployment/config 测试保持绿。

## Testing

- 单测：doctor JSON schema、各检查项的 pass/fail/fix。
- 集成：临时 home + 旧 revision DB → upgrade → doctor；缺工具/模型场景。
- 回滚：备份 → 破坏迁移 → 恢复 → 启动 worker。
- 契约：health 响应新增字段的向后兼容测试。

## Out of Scope

- 自动更新/自动回滚服务。
- 云端迁移编排。
- 修改 Alembic 历史迁移；只加新迁移。
- 备份加密/远程存储。

## Notes

- 备份默认放 `TROVE_HOME/backups/`，保留最近 N 份；不要静默删除用户数据。
- `doctor --json` 的 `fix` 字段只放可执行命令/文档链接，不放交互式提示。
- 发布检查脚本只读，不自动改系统；避免和 launchd/Docker 权限纠缠。
