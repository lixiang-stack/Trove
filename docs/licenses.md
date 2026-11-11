# Dependency licenses

Trove keeps its core dependency set to MIT/BSD/Apache-2.0. This is a record for the
MVP, not legal advice; re-check after upgrading dependencies. EbookLib (AGPL) and
Audiobookshelf (GPL) are intentionally avoided.

| Dependency     | Purpose                          | License        |
| -------------- | -------------------------------- | -------------- |
| FastAPI        | HTTP API                         | MIT            |
| Starlette      | ASGI foundation, Range support   | BSD-3-Clause   |
| Uvicorn        | ASGI server                      | BSD-3-Clause   |
| Jinja2         | Server-rendered templates        | BSD-3-Clause   |
| SQLAlchemy     | ORM and SQLite access            | MIT            |
| Alembic        | Schema migrations                | MIT            |
| Pydantic       | Request/response validation      | MIT            |
| HTTPX          | Outbound HTTP                    | BSD-3-Clause   |
| feedparser     | Podcast RSS/Atom parsing         | BSD-2-Clause   |
| itsdangerous   | Signed session cookies           | BSD-3-Clause   |
| argon2-cffi    | Argon2id password hashing        | MIT            |
| lxml           | EPUB XML/HTML parsing            | BSD-3-Clause   |
| nh3            | EPUB HTML sanitization           | MIT            |
| python-multipart | Streaming upload parsing       | Apache-2.0     |
| yt-dlp         | Bilibili/YouTube extraction      | Unlicense      |
| mlx-whisper    | Optional local ASR               | MIT            |
| FFmpeg/ffprobe | Media probing and transcoding    | LGPL/GPL build-dependent |
| Playwright     | Browser tests (dev only)         | Apache-2.0     |
| pytest         | Tests (dev only)                 | MIT            |
| ruff           | Lint (dev only)                  | MIT            |
| mypy           | Types (dev only)                 | MIT            |

FFmpeg is invoked as a separate process; no FFmpeg code is linked into Trove.
The Homebrew build's license depends on the enabled codecs. Review it if you
redistribute the application or a build artifact.
