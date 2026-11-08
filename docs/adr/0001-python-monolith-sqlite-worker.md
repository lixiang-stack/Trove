# MVP 主机采用 Python 单体、SQLite 与独立 worker

MVP 的 Host 是单用户、本地优先的 Mac 应用：处理管线重、并发低、需要任务持久化，但不值得引入 Redis/Postgres/消息队列。因此采用 Python 3.12 + FastAPI/Uvicorn 单体（HTML 与 JSON API 同一应用）+ SQLite（WAL）+ 本地文件库，处理放在独立 worker 进程中，通过 SQLite 作业表领取任务。

**Status**: Accepted · 2026-11-08

## Considered Options

- Node/TypeScript 全栈：ASR/EPUB 生态弱，yt-dlp 仍是 Python；不采用。
- Postgres + Redis/Celery：多两个常驻服务，单用户千条级不需要。
- Audiobookshelf sidecar：GPL-3.0，且与 Host Console/API 形成两套事实源；不采用。

## Consequences

- SQLite 单写者；用 WAL、`busy_timeout` 和短事务，worker 默认并发 1。
- 不做水平扩展；未来云端处理通过适配器/API 演进，不改变 MVP 结构。
- 处理崩溃不影响 API/播放；worker 启动时回收 stale run。
- 技术细节见 [技术选型](../ideas/trove-tech-selection.md) 第 2、3.1、3.4 节；需求见 [trove-requirements.md](../ideas/trove-requirements.md) 的 NFR-01/05/15。
