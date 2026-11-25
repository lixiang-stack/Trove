# 11 — Docker/Compose 自托管打包

Status: ready-for-agent
Type: task
Milestone: P3
Blocked by: 01, 08
Spec: [spec.md](../spec.md)
ADRs: [0006](../../../docs/adr/0006-native-launchd-tailscale.md)

## Context

当前安装路径是 `git clone` + `uv sync --extra asr` + `brew install ffmpeg` + `trove setup` + launchd。开发者可用，普通自托管用户不可用；也没有可复现的 Linux 部署。Docker Compose 是单租户自托管的标准交付方式，且能复用同一 CLI/config/health。

## Scope

- `Dockerfile` 多阶段构建：
  - Python 3.12 slim + `uv`；安装 FFmpeg/ffprobe。
  - `ARG INSTALL_ASR=false`；为 true 时安装 `funasr/modelscope/torch/torchaudio`，镜像明显更大。
  - 非 root 用户运行；`TROVE_HOME=/data`；入口支持 `serve`/`worker`/`doctor`/`setup`。
  - 健康检查调用 `/api/health`；暴露 8765。
- `docker-compose.yml`：
  - `api`：`trove serve --no-worker`。
  - `worker`：默认 all；可选 `worker-asr`、`worker-download`、`worker-llm`、`worker-index`（依赖 08 的 pool 参数）。
  - 命名卷 `trove-data:/data`；可选 `trove-models:/models` 或把模型放 `/data/models`。
  - 可选 `caddy` profile，文档说明 TLS；默认只绑定 127.0.0.1。
  - 初始化 job：`trove db upgrade` + `trove setup`（ASR 模型下载可手动/一次性）。
- `.dockerignore`：排除 `.venv`、`.git`、`.worktree`、缓存、测试产物、模型。
- 文档：`docs/deployment.md` 增加 Docker 章节；`README.md` 增加 Quickstart；保留 launchd 章节作为 macOS 原生路径。
- 镜像标签/版本：与 `trove --version` 对齐；构建参数和镜像大小写入文档。

## Acceptance Criteria

- [ ] 干净机器上 `docker compose up -d` 后 `/api/health` 返回 200，worker 心跳 fresh。
- [ ] 用本地 audio/EPUB fixture 完成一条 Item 处理，数据写入 `trove-data` 卷。
- [ ] 重启容器后数据、队列、设置保留。
- [ ] ASR 镜像可构建，`trove doctor` 在容器内通过（模型存在时）。
- [ ] 非 root 运行；镜像内无 `.env`/token/密钥。
- [ ] `docker compose down` 不删除命名卷；文档说明如何彻底清理。
- [ ] launchd 文档和脚本不被破坏。
- [ ] 镜像大小、构建时间、ARM64/AMD64 支持情况写入文档。

## Testing

- Docker smoke：构建 → up → health → 用 fixture 入库 → 轮询完成 → 重启 → 数据仍在。
- ASR 构建：`INSTALL_ASR=true` 构建一次，跑 `trove doctor`；不要求 CI 每次都跑。
- 配置：`TROVE_HOME`、端口、卷权限、非 root 写入。
- 回归：`./scripts/check.sh --fast` 不依赖 Docker；Docker 测试单独标记/脚本。

## Out of Scope

- Kubernetes/Helm。
- Windows 原生安装包。
- 自动更新服务。
- 云端对象存储；先本地卷。
- 把 ASR 模型打进基础镜像（默认不打）。

## Notes

- 镜像分层：依赖层、源码层、ASR 层分开，避免每次改代码重装 torch。
- `docker compose` 的 worker 池参数依赖 08；本 issue 在 08 完成后为各 pool 提供 profile。
- 文档要明确：Docker 不是唯一路径，macOS 用户仍可用 launchd。
