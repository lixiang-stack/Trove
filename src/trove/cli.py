from __future__ import annotations

import argparse
import getpass
import importlib.util
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time

from trove import __version__
from trove.app import create_app
from trove.composition import build_runtime
from trove.config import ConfigError, load_config
from trove.db.engine import (
    current_revision,
    fts5_available,
    head_revision,
    upgrade_database,
)
from trove.domain.items import ASR_MODEL_MISSING_HINT, ASR_NOT_INSTALLED_HINT
from trove.logging_setup import configure_logging
from trove.web.urls import locate_url
from trove.worker import ensure_migrated, run_worker


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

    subparsers.add_parser("worker", help="run the processing worker")

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

    index = subparsers.add_parser("index", help="search index commands")
    index_sub = index.add_subparsers(dest="index_command", required=True)
    index_sub.add_parser("rebuild", help="rebuild the search index")
    status = index_sub.add_parser("status", help="show search index coverage")
    status.add_argument("--json", action="store_true", dest="as_json")

    subparsers.add_parser("doctor", help="check Host dependencies and layout")
    subparsers.add_parser("setup", help="download the ASR model and check dependencies")

    auth = subparsers.add_parser("auth", help="authentication commands")
    auth_sub = auth.add_subparsers(dest="auth_command", required=True)
    set_password = auth_sub.add_parser("set-password", help="set the single-user password")
    set_password.add_argument(
        "--password-stdin", action="store_true", help="read the password from stdin"
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
        configure_logging(config)
        runtime = build_runtime(config)
        stop_event = threading.Event()

        def stop_worker(_signum, _frame) -> None:
            stop_event.set()

        signal.signal(signal.SIGINT, stop_worker)
        signal.signal(signal.SIGTERM, stop_worker)
        run_worker(runtime, stop_event)
        return 0
    if args.command == "db":
        return _db(config)
    if args.command == "search":
        return _search(config, args)
    if args.command == "index":
        return _index(config, args)
    if args.command == "doctor":
        return _doctor(config)
    if args.command == "setup":
        return _setup(config)
    if args.command == "auth":
        return _auth(config, args)
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
    upgrade_database(config)
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


def _doctor(config) -> int:
    config.ensure_layout()
    problems: list[str] = []
    print(f"Trove {__version__}")
    print(f"Data directory: {config.home} ({oct(config.home.stat().st_mode & 0o777)})")

    for path in (config.library_dir, config.cache_dir, config.logs_dir):
        mode = oct(path.stat().st_mode & 0o777)
        print(f"  {path.name}/ {mode}")
        if path.stat().st_mode & 0o077:
            problems.append(f"{path} permissions are too broad; expected 0700")
    for path in (config.config_path, config.env_path):
        if not path.exists():
            problems.append(f"Missing {path}")
        elif path.stat().st_mode & 0o077:
            problems.append(f"{path} permissions are too broad; expected 0600")

    engine = _engine(config)
    if not fts5_available(engine):
        problems.append("SQLite lacks FTS5 support")
    else:
        print("SQLite FTS5: OK")
    head = head_revision(config)
    current = current_revision(engine)
    if current != head:
        problems.append(f"Database is not migrated (current {current or 'empty'}, target {head})")
    else:
        print(f"Database migration: {current}")

    if config.password_configured():
        print("Password: configured")
    else:
        problems.append("Password is not configured; run: uv run trove auth set-password")

    for name, binary, args_ in (
        ("FFmpeg", "ffmpeg", ["-version"]),
        ("ffprobe", "ffprobe", ["-version"]),
    ):
        path = shutil.which(binary)
        if path is None:
            problems.append(f"Missing {name}; install with: brew install ffmpeg")
            print(f"{name}: missing")
            continue
        output = _command_version([path, *args_])
        print(f"{name}: {output} ({path})")

    ytdlp = shutil.which("yt-dlp")
    if ytdlp:
        print(f"yt-dlp: {_command_version([ytdlp, '--version'])} ({ytdlp})")
    else:
        ytdlp_result: subprocess.CompletedProcess[str] | None
        try:
            ytdlp_result = subprocess.run(
                [sys.executable, "-m", "yt_dlp", "--version"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            ytdlp_result = None
        if ytdlp_result is None or ytdlp_result.returncode != 0:
            problems.append("yt-dlp is missing; run: uv sync")
            print("yt-dlp: missing")
        else:
            print(f"yt-dlp: {ytdlp_result.stdout.strip()}")

    _doctor_asr(config, problems)

    if problems:
        print("\nProblems to fix:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("\nHost check passed.")
    return 0


def _doctor_asr(config, problems: list[str]) -> None:
    if importlib.util.find_spec("mlx_whisper") is None:
        problems.append(ASR_NOT_INSTALLED_HINT)
        print("mlx-whisper: missing")
        return
    print("mlx-whisper: OK")
    from trove.adapters.asr import model_cached

    if model_cached(config.asr_model):
        print(f"ASR model: {config.asr_model}")
    else:
        problems.append(ASR_MODEL_MISSING_HINT)
        print("ASR model: missing")


def _setup(config) -> int:
    config.ensure_layout()
    problems: list[str] = []
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        problems.append("Missing FFmpeg/ffprobe; install with: brew install ffmpeg")
    if importlib.util.find_spec("mlx_whisper") is None:
        problems.append(ASR_NOT_INSTALLED_HINT)
    if problems:
        print("Problems to fix:")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    from trove.adapters.asr import download_model

    print(f"Downloading transcription model {config.asr_model} …")
    try:
        path = download_model(config.asr_model)
    except Exception as exc:  # noqa: BLE001 - setup reports the download failure
        print(f"Model download failed: {exc}", file=sys.stderr)
        return 1
    print(f"Model ready: {path}")
    return 0


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


if __name__ == "__main__":
    raise SystemExit(main())
