from __future__ import annotations

import argparse
import getpass
import http.client
import importlib.util
import json
import os
import platform
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from trove import __version__
from trove.app import create_app
from trove.composition import build_runtime
from trove.config import (
    PASSWORD_ENV,
    PASSWORD_FILE_ENV,
    ConfigError,
    load_config,
)
from trove.db.engine import (
    DatabaseUpgradeError,
    current_revision,
    fts5_available,
    head_revision,
    upgrade_database,
)
from trove.domain.items import ASR_MODEL_MISSING_HINT, ASR_NOT_INSTALLED_HINT
from trove.domain.worker_pools import ALL_POOL
from trove.logging_setup import configure_logging
from trove.web.urls import locate_url
from trove.worker import ensure_migrated, resolve_worker_pools, run_worker


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="trove", description="Trove Host")
    parser.add_argument("--version", action="version", version=f"trove {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve = subparsers.add_parser("serve", help="run the API and web shell")
    serve.add_argument("--host", default=None)
    serve.add_argument("--port", type=int, default=None)
    serve.add_argument("--lan", action="store_true", help="bind all interfaces")
    serve.add_argument(
        "--no-worker",
        action="store_true",
        help="do not start the processing worker child process",
    )

    worker = subparsers.add_parser("worker", help="run the processing worker")
    worker.add_argument(
        "--pool",
        action="append",
        default=[],
        metavar="POOL",
        help="worker pool to run: all, download, asr, llm, or index (repeatable)",
    )
    worker.add_argument(
        "--stages",
        default=None,
        help="comma-separated stages to claim instead of a named pool",
    )
    worker.add_argument(
        "--concurrency",
        type=int,
        default=None,
        help="claiming threads per pool; index pools always run one",
    )

    db = subparsers.add_parser("db", help="database commands")
    db_sub = db.add_subparsers(dest="db_command", required=True)
    db_sub.add_parser("upgrade", help="apply migrations")

    search = subparsers.add_parser("search", help="search the library from the terminal")
    search.add_argument("query")
    search.add_argument("--json", action="store_true", dest="as_json")
    search.add_argument("--limit", type=int, default=20)
    search.add_argument("--type", default="", dest="item_type")
    search.add_argument("--consumption", default="")
    search.add_argument("--tag", default="")
    search.add_argument("--source", default="")

    bench = subparsers.add_parser("bench", help="local performance benchmarks")
    bench_sub = bench.add_subparsers(dest="bench_command", required=True)
    bench_asr = bench_sub.add_parser("asr", help="time a real ASR transcription")
    bench_asr.add_argument("audio")
    bench_asr.add_argument("--model", default=None)
    bench_asr.add_argument("--json", action="store_true", dest="as_json")
    bench_search = bench_sub.add_parser("search", help="time search queries against the library")
    bench_search.add_argument("--queries", required=True, help="one query per line")
    bench_search.add_argument("--repeat", type=int, default=3)
    bench_search.add_argument("--limit", type=int, default=20)
    bench_search.add_argument("--json", action="store_true", dest="as_json")
    bench_pipeline = bench_sub.add_parser(
        "pipeline", help="time a full real video pipeline (network and tools required)"
    )
    bench_pipeline.add_argument("url")
    bench_pipeline.add_argument("--json", action="store_true", dest="as_json")
    bench_seed = bench_sub.add_parser(
        "seed", help="insert repeatable search-benchmark Items into TROVE_HOME"
    )
    bench_seed.add_argument("--count", type=int, default=1000)
    bench_seed.add_argument("--json", action="store_true", dest="as_json")

    index = subparsers.add_parser("index", help="search index commands")
    index_sub = index.add_subparsers(dest="index_command", required=True)
    index_sub.add_parser("rebuild", help="rebuild the search index")
    status = index_sub.add_parser("status", help="show search index coverage")
    status.add_argument("--json", action="store_true", dest="as_json")

    package = subparsers.add_parser("package", help="content package commands")
    package_sub = package.add_subparsers(dest="package_command", required=True)
    package_verify = package_sub.add_parser(
        "verify", help="verify an Item content package manifest"
    )
    package_verify.add_argument("item_id")

    collection = subparsers.add_parser("collection", help="collection maintenance")
    collection_sub = collection.add_subparsers(
        dest="collection_command", required=True
    )
    collection_reprocess = collection_sub.add_parser(
        "reprocess", help="reprocess every episode in a collection"
    )
    collection_reprocess.add_argument("collection_id")
    collection_reprocess.add_argument("--from-stage", default="organizing")
    collection_reprocess.add_argument(
        "--reset-ai-tags",
        action="store_true",
        help="delete AI tags before queueing the runs",
    )

    doctor = subparsers.add_parser("doctor", help="check Host dependencies and layout")
    doctor.add_argument("--json", action="store_true", dest="as_json")
    subparsers.add_parser("setup", help="download the ASR model and check dependencies")

    service = subparsers.add_parser("service", help="install or remove launchd agents")
    service_sub = service.add_subparsers(dest="service_command", required=True)
    for action in ("install", "uninstall"):
        command = service_sub.add_parser(action, help=f"{action} launchd agents")
        command.add_argument("--root", default=None, help="repository root")
        command.add_argument("--home", default=None, help="TROVE_HOME to use")
        command.add_argument("--agents-dir", default=None, help="LaunchAgents directory")
        command.add_argument(
            "--pool",
            action="append",
            default=[],
            metavar="POOL",
            help="worker pool agent to render: all, download, asr, llm, or index",
        )
        command.add_argument("--dry-run", action="store_true")

    auth = subparsers.add_parser("auth", help="authentication commands")
    auth_sub = auth.add_subparsers(dest="auth_command", required=True)
    set_password = auth_sub.add_parser("set-password", help="set the single-user password")
    set_password.add_argument(
        "--password-stdin", action="store_true", help="read the password from stdin"
    )

    device = subparsers.add_parser("device", help="manage Android device tokens")
    device_sub = device.add_subparsers(dest="device_command", required=True)
    device_list = device_sub.add_parser("list", help="list authorized devices")
    device_list.add_argument("--json", action="store_true", dest="as_json")
    device_revoke = device_sub.add_parser("revoke", help="revoke a device token")
    device_revoke.add_argument("device_id")

    sync = subparsers.add_parser("sync", help="sync administration")
    sync_sub = sync.add_subparsers(dest="sync_command", required=True)
    sync_sub.add_parser(
        "reset-epoch", help="rotate the sync epoch and force all clients to resync"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        config = load_config()
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1

    if args.command == "serve":
        return _serve(config, args)
    if args.command == "worker":
        try:
            pools = resolve_worker_pools(
                config,
                pools=args.pool,
                stages=args.stages,
                concurrency=args.concurrency,
            )
        except ConfigError as exc:
            print(f"Configuration error: {exc}", file=sys.stderr)
            return 2
        configure_logging(config)
        runtime = build_runtime(config)
        stop_event = threading.Event()

        def stop_worker(_signum, _frame) -> None:
            stop_event.set()

        signal.signal(signal.SIGINT, stop_worker)
        signal.signal(signal.SIGTERM, stop_worker)
        run_worker(runtime, stop_event, pools=pools)
        return 0
    if args.command == "db":
        return _db(config)
    if args.command == "search":
        return _search(config, args)
    if args.command == "index":
        return _index(config, args)
    if args.command == "package":
        return _package(config, args)
    if args.command == "collection":
        return _collection(config, args)
    if args.command == "bench":
        return _bench(config, args)
    if args.command == "doctor":
        return _doctor(config, as_json=args.as_json)
    if args.command == "setup":
        return _setup(config)
    if args.command == "service":
        return _service(config, args)
    if args.command == "auth":
        return _auth(config, args)
    if args.command == "device":
        return _device(config, args)
    if args.command == "sync":
        return _sync(config, args)
    parser.error("Unknown command")
    return 2


def _serve(config, args) -> int:
    import uvicorn

    host = args.host or config.host
    if args.lan:
        host = "0.0.0.0"
    port = args.port or config.port
    if host not in {"127.0.0.1", "::1", "localhost"} and not args.lan:
        print(
            "Hint: for non-local access, prefer Tailscale Serve or HTTPS.",
            file=sys.stderr,
        )
    if args.lan:
        print(
            "Warning: --lan binds 0.0.0.0; use only on a trusted local network.",
            file=sys.stderr,
        )
    worker_process = None if args.no_worker else _start_worker_child(config)
    app = create_app(config)
    try:
        uvicorn.run(app, host=host, port=port, log_level="info")
    finally:
        if worker_process is not None:
            _stop_worker_child(worker_process)
    return 0


def _start_worker_child(config) -> subprocess.Popen[str] | None:
    from trove.worker import heartbeat_is_fresh, read_heartbeat

    heartbeat = read_heartbeat(config)
    if heartbeat_is_fresh(heartbeat) and _heartbeat_process_alive(heartbeat):
        print("Detected an existing worker; skipping the built-in worker.", file=sys.stderr)
        return None
    print(
        "Starting the built-in processing worker (disable with --no-worker).",
        file=sys.stderr,
    )
    environment = os.environ.copy()
    environment["TROVE_PARENT_PID"] = str(os.getpid())
    process = subprocess.Popen(
        [sys.executable, "-m", "trove.cli", "worker"],
        env=environment,
        text=True,
    )
    deadline = time.monotonic() + 3
    from trove.worker import heartbeat_is_fresh, read_heartbeat

    while time.monotonic() < deadline:
        if heartbeat_is_fresh(read_heartbeat(config)):
            break
        if process.poll() is not None:
            print(
                "Built-in worker failed to start; check database migrations and run "
                "uv run trove doctor.",
                file=sys.stderr,
            )
            break
        time.sleep(0.05)
    return process


def _heartbeat_process_alive(heartbeat: dict | None) -> bool:
    if not heartbeat:
        return False
    pid = heartbeat.get("pid")
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _stop_worker_child(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _db(config) -> int:
    config.ensure_layout()
    configure_logging(config, console=False)
    try:
        backup = upgrade_database(config)
    except DatabaseUpgradeError as exc:
        print(str(exc), file=sys.stderr)
        if exc.backup_path is not None:
            print(
                "Restore the pre-upgrade database with:\n"
                f"  cp {exc.backup_path} {config.db_path}\n"
                f"  rm -f {config.db_path}-wal {config.db_path}-shm",
                file=sys.stderr,
            )
        return 1
    if backup is not None:
        print(f"Database backup: {backup}")
    current = current_revision(_engine(config))
    print(f"Database migrated to {current}")
    return 0


def _engine(config):
    from sqlalchemy import create_engine

    return create_engine(f"sqlite:///{config.db_path}")


def _search(config, args) -> int:
    runtime = build_runtime(config)
    ensure_migrated(runtime)
    try:
        results = runtime.search.search(
            args.query,
            item_type=args.item_type or None,
            consumption=args.consumption or None,
            tag=args.tag or None,
            platform=args.source or None,
            limit=args.limit,
        )
    except ValueError as exc:
        print(f"Invalid query: {exc}", file=sys.stderr)
        return 2
    if args.as_json:
        print(
            json.dumps(
                _search_payload(runtime, args.query, results),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    print(f'{len(results)} Items matched "{args.query}"')
    for result in results:
        item = result.bundle.item
        print(f"\n{item.title}")
        print(f"  {item.source_type} · {item.platform} · {item.author or 'Unknown author'}")
        for evidence in result.evidence:
            print(f"  [{evidence.doc_kind}] {evidence.snippet}")
            print(
                "    "
                + locate_url(
                    item.id, item.source_type, evidence.doc_kind, evidence.ref
                )
            )
    return 0


def _search_payload(runtime, query: str, results) -> dict:
    return {
        "query": query,
        "count": len(results),
        "results": [
            {
                "item": runtime.library.payload(result.bundle),
                "score": result.score,
                "evidence": [
                    {
                        "doc_kind": evidence.doc_kind,
                        "ref": evidence.ref,
                        "text": evidence.text,
                        "snippet": evidence.snippet,
                        "score": evidence.score,
                        "url": locate_url(
                            result.bundle.item.id,
                            result.bundle.item.source_type,
                            evidence.doc_kind,
                            evidence.ref,
                        ),
                    }
                    for evidence in result.evidence
                ],
            }
            for result in results
        ],
    }


def _index(config, args) -> int:
    if args.index_command == "rebuild":
        runtime = build_runtime(config)
        ensure_migrated(runtime)
        count = runtime.search_index.rebuild()
        print(f"Search index rebuilt: {count} Items")
        return 0
    return _index_status(config, args)


def _index_status(config, args) -> int:
    runtime = build_runtime(config)
    ensure_migrated(runtime)
    status = runtime.search.index_status()
    if args.as_json:
        print(
            json.dumps(
                {
                    "items": [
                        {
                            "item_id": item.item_id,
                            "title": item.title,
                            "counts": item.counts,
                            "expected": item.expected,
                            "missing_kinds": item.missing_kinds,
                            "stale": bool(item.missing_kinds),
                        }
                        for item in status.items
                    ],
                    "total_rows": status.total_rows,
                    "orphan_rows": status.orphan_rows,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    print(
        f"Search index: {len(status.items)} Items · {status.total_rows} rows"
        f" · {status.orphan_rows} orphan rows"
    )
    for item in status.items:
        if item.missing_kinds:
            missing = ", ".join(
                f"{kind} {item.counts.get(kind, 0)}/{item.expected[kind]}"
                for kind in item.missing_kinds
            )
            print(f"✗ {item.title} · missing: {missing}")
            continue
        counts = ", ".join(
            f"{kind}={item.counts.get(kind, 0)}"
            for kind in ("title", "summary", "tag", "transcript", "book")
            if item.counts.get(kind)
        )
        print(f"✓ {item.title} · {counts or 'no indexed rows'}")
    return 0


def _package(config, args) -> int:
    from trove.content_package import ContentPackage
    from trove.errors import TroveError

    package = ContentPackage(config)
    try:
        problems = package.verify_manifest(args.item_id)
    except TroveError as exc:
        print(f"{exc.code}: {exc.message}", file=sys.stderr)
        return 1
    if problems:
        print(f"{args.item_id}: {len(problems)} package problem(s)", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem.path}: {problem.message}", file=sys.stderr)
        return 1
    print(f"{args.item_id}: content package verified")
    return 0


def _collection(config, args) -> int:
    from trove.domain.items import REPROCESSABLE_STAGES

    if args.from_stage not in REPROCESSABLE_STAGES:
        print(
            f"Invalid stage: {args.from_stage}; choose organizing or indexing",
            file=sys.stderr,
        )
        return 2
    runtime = build_runtime(config)
    ensure_migrated(runtime)
    reset = runtime.collections.reset_ai_tags(args.collection_id) if args.reset_ai_tags else 0
    count = runtime.collections.reprocess(args.collection_id, args.from_stage)
    if args.reset_ai_tags:
        print(f"Deleted {reset} AI tag links; queued {count} {args.from_stage} runs")
    else:
        print(f"Queued {count} {args.from_stage} runs")
    return 0


def _bench(config, args) -> int:
    from trove.benchmarks import (
        read_queries,
        run_asr_benchmark,
        run_pipeline_benchmark,
        run_search_benchmark,
        seed_library,
    )

    payload: dict[str, Any]
    if args.bench_command == "seed":
        if args.count < 1:
            print("--count must be positive", file=sys.stderr)
            return 2
        count = seed_library(config, args.count)
        payload = {"seeded": count, "home": str(config.home)}
        if args.as_json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"Seeded {count} benchmark Items in {config.home}")
        return 0

    if args.bench_command == "pipeline":
        try:
            payload = run_pipeline_benchmark(config, args.url)
        except Exception as exc:  # noqa: BLE001 - benchmark reports the failure
            print(f"Pipeline benchmark failed: {exc}", file=sys.stderr)
            return 1
        if args.as_json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"Item: {payload['title']}")
            print(f"Elapsed: {payload['elapsed_sec']} s")
            print(f"State: {payload['state']}")
            if payload["error_code"]:
                print(f"Error: {payload['error_code']}")
        return 0 if payload["state"] == "completed" else 1

    if args.bench_command == "asr":
        audio = Path(args.audio).expanduser()
        if not audio.is_file():
            print(f"Audio file not found: {audio}", file=sys.stderr)
            return 2
        try:
            payload = run_asr_benchmark(config, audio, model=args.model)
        except Exception as exc:  # noqa: BLE001 - benchmark reports the failure
            print(f"ASR benchmark failed: {exc}", file=sys.stderr)
            return 1
        if args.as_json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"ASR model: {payload['model']}")
            print(f"Audio: {payload['duration_sec']} s")
            print(f"Elapsed: {payload['elapsed_sec']} s")
            print(f"Realtime factor: {payload['realtime_factor']}")
            print(f"Language: {payload['language']} · segments: {payload['segments']}")
        return 0

    if args.repeat < 1 or args.limit < 1:
        print("--repeat and --limit must be positive", file=sys.stderr)
        return 2
    query_path = Path(args.queries).expanduser()
    if not query_path.is_file():
        print(f"Query file not found: {query_path}", file=sys.stderr)
        return 2
    try:
        queries = read_queries(query_path)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    runtime = build_runtime(config)
    ensure_migrated(runtime)
    payload = run_search_benchmark(
        runtime, queries, repeat=args.repeat, limit=args.limit
    )
    if args.as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    summary = payload["summary"]
    print(
        f"{payload['queries']} queries × {payload['repeat']} · "
        f"p50 {summary['p50_ms']} ms · p95 {summary['p95_ms']} ms"
    )
    for row in payload["results"]:
        print(
            f"{row['timings']['p50_ms']:8.2f} ms  "
            f"{row['results']:3d} results  {row['query']}"
        )
    return 0


@dataclass(slots=True)
class _DoctorTools:
    ffmpeg_path: str | None
    ffmpeg_version: str | None
    ffprobe_path: str | None
    ffprobe_version: str | None
    ytdlp_version: str | None


def _doctor_check(
    name: str, status: str, message: str, fix: str = ""
) -> dict[str, str]:
    return {"name": name, "status": status, "message": message, "fix": fix}


def _doctor(config, *, as_json: bool) -> int:
    checks, versions = _doctor_checks(config)
    ok = all(entry["status"] != "fail" for entry in checks)
    if as_json:
        print(
            json.dumps(
                {"ok": ok, "checks": checks, "versions": versions},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0 if ok else 1

    _print_doctor_checks(config, checks)
    failures = [entry for entry in checks if entry["status"] == "fail"]
    if failures:
        print("\nProblems to fix:")
        for entry in failures:
            print(f"  - {entry['message']}")
        return 1
    print("\nHost check passed.")
    return 0


def _doctor_checks(config) -> tuple[list[dict[str, str]], dict[str, str | None]]:
    tools = _doctor_tools()
    checks = [
        _doctor_permissions(config),
        *_doctor_database(config),
        _doctor_password(config),
        _doctor_port(config),
        *_doctor_tool_checks(tools),
        _doctor_asr(config),
        _doctor_packages(config),
        _doctor_worker(config),
        _doctor_disk(config),
    ]
    versions = {
        "trove": __version__,
        "python": platform.python_version(),
        "ffmpeg": tools.ffmpeg_version,
        "ffprobe": tools.ffprobe_version,
        "yt_dlp": tools.ytdlp_version,
        "sqlite": sqlite3.sqlite_version,
        "asr_model": config.asr_model,
    }
    return checks, versions


def _doctor_tools() -> _DoctorTools:
    ffmpeg_path = shutil.which("ffmpeg")
    ffprobe_path = shutil.which("ffprobe")
    return _DoctorTools(
        ffmpeg_path=ffmpeg_path,
        ffmpeg_version=(
            _command_version([ffmpeg_path, "-version"]) if ffmpeg_path else None
        ),
        ffprobe_path=ffprobe_path,
        ffprobe_version=(
            _command_version([ffprobe_path, "-version"]) if ffprobe_path else None
        ),
        ytdlp_version=_ytdlp_version(shutil.which("yt-dlp")),
    )


def _doctor_permissions(config) -> dict[str, str]:
    directories = (config.home, config.library_dir, config.cache_dir, config.logs_dir)
    broad_directories = [
        path for path in directories if path.stat().st_mode & 0o077
    ]
    broad_files = (
        [config.config_path]
        if config.config_path.exists()
        and config.config_path.stat().st_mode & 0o077
        else []
    )
    if not broad_directories and not broad_files:
        return _doctor_check(
            "permissions",
            "ok",
            f"Data directory: {config.home} (0700); library/cache/logs 0700; "
            "config 0600",
        )
    message = "Permissions are too broad: " + ", ".join(
        str(path) for path in (*broad_directories, *broad_files)
    )
    fixes = []
    if broad_directories:
        fixes.append("chmod 700 " + " ".join(str(path) for path in broad_directories))
    if broad_files:
        fixes.append("chmod 600 " + " ".join(str(path) for path in broad_files))
    return _doctor_check("permissions", "fail", message, "; ".join(fixes))


def _doctor_database(config) -> list[dict[str, str]]:
    engine = _engine(config)
    head = head_revision(config)
    current = current_revision(engine)
    if current == head:
        revision = _doctor_check(
            "database_revision", "ok", f"Database migration: {current}"
        )
    else:
        revision = _doctor_check(
            "database_revision",
            "fail",
            f"Database is not migrated (current {current or 'empty'}, target {head})",
            "uv run trove db upgrade",
        )
    if fts5_available(engine):
        fts5 = _doctor_check("fts5", "ok", "SQLite FTS5: OK")
    else:
        fts5 = _doctor_check(
            "fts5", "fail", "SQLite lacks FTS5 support", "uv python install 3.12"
        )
    return [revision, fts5]


def _doctor_password(config) -> dict[str, str]:
    if config.password_configured():
        return _doctor_check("password", "ok", "Password: configured")
    return _doctor_check(
        "password",
        "fail",
        "Password is not configured; run: uv run trove auth set-password",
        "uv run trove auth set-password",
    )


def _doctor_port(config) -> dict[str, str]:
    problem, message = _port_status(config.host, config.port)
    return _doctor_check(
        "port",
        "fail" if problem else "ok",
        message,
        "docs/deployment.md#troubleshooting" if problem else "",
    )


def _doctor_tool_checks(tools: _DoctorTools) -> list[dict[str, str]]:
    checks = []
    for key, name, path, version in (
        ("ffmpeg", "FFmpeg", tools.ffmpeg_path, tools.ffmpeg_version),
        ("ffprobe", "ffprobe", tools.ffprobe_path, tools.ffprobe_version),
    ):
        if path is None:
            checks.append(
                _doctor_check(
                    key,
                    "fail",
                    f"Missing {name}; install with: brew install ffmpeg",
                    "brew install ffmpeg",
                )
            )
        else:
            checks.append(_doctor_check(key, "ok", f"{name}: {version} ({path})"))
    if tools.ytdlp_version is None:
        checks.append(
            _doctor_check(
                "yt_dlp", "fail", "yt-dlp is missing; run: uv sync", "uv sync"
            )
        )
    else:
        checks.append(_doctor_check("yt_dlp", "ok", f"yt-dlp: {tools.ytdlp_version}"))
    return checks


def _doctor_asr(config) -> dict[str, str]:
    # Optional ASR adapter; keep unrelated CLI commands free of the ASR stack.
    from trove.adapters.asr import funasr_installed, model_cached

    if not funasr_installed():
        return _doctor_check(
            "asr", "fail", ASR_NOT_INSTALLED_HINT, "uv sync --extra asr"
        )
    if not model_cached(config.asr_model):
        return _doctor_check("asr", "fail", ASR_MODEL_MISSING_HINT, "uv run trove setup")
    return _doctor_check("asr", "ok", f"funasr: OK; ASR model: {config.asr_model}")


def _doctor_packages(config) -> dict[str, str]:
    from trove.content_package import ContentPackage

    unsupported = ContentPackage(config).incompatible_manifests()
    if unsupported:
        return _doctor_check(
            "content_packages",
            "fail",
            "Unsupported content package schema: " + "; ".join(unsupported),
            "docs/deployment.md#upgrade-backup-and-rollback",
        )
    return _doctor_check("content_packages", "ok", "Content packages: supported")


def _doctor_worker(config) -> dict[str, str]:
    from trove.worker import heartbeat_is_fresh, read_heartbeat, read_heartbeats

    heartbeat = read_heartbeat(config)
    entries = read_heartbeats(config)
    state = heartbeat.get("state") if heartbeat is not None else None
    alive = any(
        heartbeat_is_fresh(entry) and _heartbeat_process_alive(entry)
        for entry in entries
    )
    if heartbeat_is_fresh(heartbeat) and alive:
        return _doctor_check("worker", "ok", f"Worker heartbeat: fresh (state={state})")
    if heartbeat_is_fresh(heartbeat):
        return _doctor_check(
            "worker",
            "warn",
            f"Worker heartbeat: fresh but the process is not running (state={state})",
            "uv run trove worker",
        )
    if heartbeat is not None:
        return _doctor_check(
            "worker",
            "warn",
            f"Worker heartbeat: stale (state={state})",
            "uv run trove worker",
        )
    return _doctor_check(
        "worker", "warn", "Worker heartbeat: not running", "uv run trove worker"
    )


def _doctor_disk(config) -> dict[str, str]:
    free_bytes = shutil.disk_usage(config.home).free
    free_gb = free_bytes / (1024**3)
    if free_bytes < 100 * 1024 * 1024:
        status = "fail"
    elif free_bytes < 1024 * 1024 * 1024:
        status = "warn"
    else:
        status = "ok"
    return _doctor_check(
        "disk",
        status,
        f"Disk: {free_gb:.1f} GB free",
        "docs/deployment.md#backups",
    )


def _print_doctor_checks(config, checks: list[dict[str, str]]) -> None:
    print(f"Trove {__version__}")
    for entry in checks:
        if entry["name"] == "permissions":
            print(
                f"Data directory: {config.home} "
                f"({oct(config.home.stat().st_mode & 0o777)})"
            )
            for path in (config.library_dir, config.cache_dir, config.logs_dir):
                print(f"  {path.name}/ {oct(path.stat().st_mode & 0o777)}")
            continue
        print(entry["message"])


def _ytdlp_version(path: str | None) -> str | None:
    if path is not None:
        return _command_version([path, "--version"])
    try:
        result = subprocess.run(
            [sys.executable, "-m", "yt_dlp", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _setup(config) -> int:
    config.ensure_layout()
    problems: list[str] = []
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        problems.append("Missing FFmpeg/ffprobe; install with: brew install ffmpeg")
    # Optional ASR check; imported only by setup.
    from trove.adapters.asr import funasr_installed

    if not funasr_installed():
        problems.append(ASR_NOT_INSTALLED_HINT)
    if importlib.util.find_spec("yt_dlp") is None:
        problems.append("yt-dlp is missing; run: uv sync")
    if not fts5_available(_engine(config)):
        problems.append("SQLite lacks FTS5 support")
    port_problem, port_message = _port_status(config.host, config.port)
    if port_problem:
        problems.append(port_message)
    if problems:
        print("Problems to fix:")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    # Optional ASR download; imported only when setup reaches the model step.
    from trove.adapters.asr import download_model

    print(f"Downloading transcription model {config.asr_model} …")
    try:
        path = download_model(config.asr_model)
    except Exception as exc:  # noqa: BLE001 - setup reports the download failure
        print(f"Model download failed: {exc}", file=sys.stderr)
        return 1
    print(f"Model ready: {path}")
    return 0


def _service(config, args) -> int:
    from trove import deploy
    from trove.config import Config

    root = Path(args.root).expanduser().resolve() if args.root else Path.cwd().resolve()
    home = Path(args.home).expanduser().resolve() if args.home else config.home
    agents_dir = (
        Path(args.agents_dir).expanduser().resolve()
        if args.agents_dir
        else deploy.default_agents_dir()
    )
    try:
        if args.service_command == "install":
            if not args.dry_run:
                target = config if home == config.home else Config(home=home)
                target.ensure_layout()
                upgrade_database(target)
            paths = deploy.install(
                repo_root=root,
                home=home,
                agents_dir=agents_dir,
                worker_pools=args.pool or (ALL_POOL,),
                dry_run=args.dry_run,
            )
            verb = "Rendered" if args.dry_run else "Installed"
            for path in paths:
                print(f"{verb} {path}")
            if not args.dry_run:
                print("Start: launchctl kickstart -k gui/$(id -u)/com.trove.api")
            return 0
        paths = deploy.uninstall(
            agents_dir=agents_dir,
            worker_pools=args.pool or None,
            dry_run=args.dry_run,
        )
        verb = "Would remove" if args.dry_run else "Removed"
        for path in paths:
            print(f"{verb} {path}")
        print(f"Data in {home} was left untouched.")
        return 0
    except deploy.DeployError as exc:
        print(f"Deployment error: {exc}", file=sys.stderr)
        return 1
    except DatabaseUpgradeError as exc:
        print(str(exc), file=sys.stderr)
        if exc.backup_path is not None:
            print(f"Pre-upgrade backup: {exc.backup_path}", file=sys.stderr)
        return 1


def _port_status(host: str, port: int) -> tuple[bool, str]:
    if _port_available(host, port):
        return False, f"Port: {host}:{port} available"
    probe_host = {"0.0.0.0": "127.0.0.1", "::": "::1"}.get(host, host)
    try:
        connection = http.client.HTTPConnection(probe_host, port, timeout=1)
        connection.request("GET", "/api/health")
        response = connection.getresponse()
        payload = json.loads(response.read())
        if isinstance(payload, dict) and {"host", "database", "worker"} <= set(payload):
            return False, f"Port: {host}:{port} in use by Trove (running)"
    except (OSError, http.client.HTTPException, json.JSONDecodeError):
        pass
    return True, f"Port {host}:{port} is already in use; stop the other process"


def _port_available(host: str, port: int) -> bool:
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def _command_version(command: list[str]) -> str:
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=10, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    first = (result.stdout or result.stderr).splitlines()
    return first[0].strip() if first else "unknown"


def _auth(config, args) -> int:
    if args.auth_command != "set-password":
        return 2
    if os.environ.get(PASSWORD_ENV) or os.environ.get(PASSWORD_FILE_ENV):
        print(
            f"Warning: {PASSWORD_ENV}/{PASSWORD_FILE_ENV} is set and will "
            "override this password on the next start.",
            file=sys.stderr,
        )
    if args.password_stdin or not sys.stdin.isatty():
        password = sys.stdin.readline().rstrip("\n")
        confirm = password
    else:
        password = getpass.getpass("New password: ")
        confirm = getpass.getpass("Enter it again: ")
    if password != confirm:
        print("Passwords do not match.", file=sys.stderr)
        return 1
    if not password:
        print("Password cannot be empty.", file=sys.stderr)
        return 1
    config.set_password(password)
    config.config_path.chmod(0o600)
    print(f"Password written to {config.config_path} (mode 0600).")
    return 0


def _device(config, args) -> int:
    from trove.composition import build_runtime
    from trove.worker import ensure_migrated

    runtime = build_runtime(config)
    ensure_migrated(runtime)
    if args.device_command == "list":
        devices = runtime.devices.list()
        payload = {
            "devices": [
                {
                    "device_id": device.device_id,
                    "name": device.name,
                    "created_at": device.created_at,
                    "last_used_at": device.last_used_at,
                    "revoked_at": device.revoked_at,
                }
                for device in devices
            ]
        }
        if args.as_json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0
        if not devices:
            print("No authorized devices.")
            return 0
        for device in devices:
            status = "revoked" if device.revoked_at else "active"
            print(f"{device.device_id}  {device.name}  {status}")
        return 0
    revoked = runtime.devices.revoke(args.device_id)
    if revoked is None:
        print("Device not found.", file=sys.stderr)
        return 1
    print(f"Revoked {revoked.name} ({revoked.device_id}).")
    return 0


def _sync(config, args) -> int:
    from trove.composition import build_runtime
    from trove.db.sequences import reset_epoch
    from trove.worker import ensure_migrated

    runtime = build_runtime(config)
    ensure_migrated(runtime)
    with runtime.sessions() as session:
        epoch = reset_epoch(session)
    print(f"Sync epoch rotated: {epoch}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
