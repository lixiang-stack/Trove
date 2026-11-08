# 01 — Host 骨架与运行入口

Status: ready-for-agent  
Type: task  
Milestone: M0  
Blocked by: none  
Spec: [spec.md](../spec.md)  
Requirements: FR-76, FR-80, FR-83, NFR-01, NFR-13

## Context

仓库目前只有文档，没有应用代码。第一个可执行切片需要让 Host 能在 Mac 上启动：配置、数据目录、FastAPI 应用、Jinja 基础布局、SQLite 连接和健康检查。后续所有 issue 都建立在这个骨架上。

## Scope

- 建立 Python 3.12 + uv 项目，声明 FastAPI、Uvicorn、Jinja2、SQLAlchemy、Alembic、Pydantic 等基础依赖。
- 配置加载：`TROVE_HOME` 覆盖数据目录，默认 `~/Trove`；创建 config、library、cache、logs，权限 0700。
- FastAPI 应用工厂、Jinja 基础布局、本地 vendored HTMX/Pico CSS（不使用 CDN）。
- CLI 入口：`trove serve`、`trove worker`（worker 先占位）、`trove db upgrade`、`trove doctor`。
- 健康检查 `/api/health`，结构化日志，基础请求日志。
- SQLite 连接配置：WAL、foreign keys、`busy_timeout`；迁移目录与初始迁移骨架。

## Acceptance Criteria

- [ ] 在干净环境执行依赖安装后，`uv run trove serve` 能启动并访问基础页面。
- [ ] `/api/health` 返回 200，包含 Host、数据库和迁移状态。
- [ ] 数据目录按 `TROVE_HOME` 创建，权限为 0700；缺少 FFmpeg/yt-dlp 时 `trove doctor` 给出可操作提示。
- [ ] 基础布局加载本地 HTMX/Pico，不依赖任何 CDN。
- [ ] `trove db upgrade` 可重复执行；SQLite 开启 WAL/foreign keys。
- [ ] 日志写入 `logs/`，不包含密钥。

## Testing

- Host seam 冒烟测试：启动 API，请求 `/api/health` 和基础页面。
- 临时 `TROVE_HOME` 测试目录创建、权限和重复启动。
- `uv run pytest`、`ruff check`、`mypy` 和 `python3 scripts/check-docs.py` 通过。

## Out of Scope

- 认证、业务表、入库、处理、播放、搜索；这些由后续 issue 实现。
- launchd/Tailscale 部署；由 24 实现。
