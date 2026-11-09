from __future__ import annotations

import argparse
import getpass
import importlib.util
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
from trove.domain.items import ASR_MODEL_MISSING_HINT
from trove.logging_setup import configure_logging
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

    index = subparsers.add_parser("index", help="search index commands")
    index_sub = index.add_subparsers(dest="index_command", required=True)
    index_sub.add_parser("rebuild", help="rebuild the search index")

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
        print(f"配置错误: {exc}", file=sys.stderr)
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
    if args.command == "index":
        return _index(config)
    if args.command == "doctor":
        return _doctor(config)
    if args.command == "setup":
        return _setup(config)
    if args.command == "auth":
        return _auth(config, args)
    parser.error("未知命令")
    return 2


def _serve(config, args) -> int:
    import uvicorn

    host = args.host or config.host
    if args.lan:
        host = "0.0.0.0"
    port = args.port or config.port
    if host not in {"127.0.0.1", "::1", "localhost"} and not args.lan:
        print("提示：非本机访问建议使用 Tailscale Serve 或 HTTPS。", file=sys.stderr)
    if args.lan:
        print("警告：--lan 会绑定 0.0.0.0，仅建议在受信任局域网使用。", file=sys.stderr)
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
        print("检测到已有 worker，跳过启动内置 worker。", file=sys.stderr)
        return None
    print("启动内置 processing worker（使用 --no-worker 可关闭）。", file=sys.stderr)
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
                "内置 worker 启动失败；请检查数据库迁移并运行 uv run trove doctor。",
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
    print(f"数据库已迁移到 {current}")
    return 0


def _engine(config):
    from sqlalchemy import create_engine

    return create_engine(f"sqlite:///{config.db_path}")


def _index(config) -> int:
    runtime = build_runtime(config)
    ensure_migrated(runtime)
    count = runtime.search_index.rebuild()
    print(f"搜索索引已重建: {count} 个 Item")
    return 0


def _doctor(config) -> int:
    config.ensure_layout()
    problems: list[str] = []
    print(f"Trove {__version__}")
    print(f"数据目录: {config.home} ({oct(config.home.stat().st_mode & 0o777)})")

    for path in (config.library_dir, config.cache_dir, config.logs_dir):
        mode = oct(path.stat().st_mode & 0o777)
        print(f"  {path.name}/ {mode}")
        if path.stat().st_mode & 0o077:
            problems.append(f"{path} 权限过宽，应为 0700")
    for path in (config.config_path, config.env_path):
        if not path.exists():
            problems.append(f"缺少 {path}")
        elif path.stat().st_mode & 0o077:
            problems.append(f"{path} 权限过宽，应为 0600")

    engine = _engine(config)
    if not fts5_available(engine):
        problems.append("SQLite 缺少 FTS5 支持")
    else:
        print("SQLite FTS5: OK")
    head = head_revision(config)
    current = current_revision(engine)
    if current != head:
        problems.append(f"数据库未迁移（当前 {current or '空'}，目标 {head}）")
    else:
        print(f"数据库迁移: {current}")

    if config.password_configured():
        print("密码: 已设置")
    else:
        problems.append("尚未设置密码，请运行: uv run trove auth set-password")

    for name, binary, args_ in (
        ("FFmpeg", "ffmpeg", ["-version"]),
        ("ffprobe", "ffprobe", ["-version"]),
    ):
        path = shutil.which(binary)
        if path is None:
            problems.append(f"缺少 {name}，请安装: brew install ffmpeg")
            print(f"{name}: 缺失")
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
            problems.append("缺少 yt-dlp，请运行: uv sync")
            print("yt-dlp: 缺失")
        else:
            print(f"yt-dlp: {ytdlp_result.stdout.strip()}")

    _doctor_asr(config, problems)

    if problems:
        print("\n需要处理：")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("\nHost 检查通过。")
    return 0


def _doctor_asr(config, problems: list[str]) -> None:
    if importlib.util.find_spec("mlx_whisper") is None:
        problems.append("缺少 mlx-whisper，请运行: uv sync")
        print("mlx-whisper: 缺失")
        return
    print("mlx-whisper: OK")
    from trove.adapters.asr import model_cached

    if model_cached(config.asr_model):
        print(f"ASR 模型: {config.asr_model}")
    else:
        problems.append(ASR_MODEL_MISSING_HINT)
        print("ASR 模型: 缺失")


def _setup(config) -> int:
    config.ensure_layout()
    problems: list[str] = []
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        problems.append("缺少 FFmpeg/ffprobe，请安装: brew install ffmpeg")
    if importlib.util.find_spec("mlx_whisper") is None:
        problems.append("缺少 mlx-whisper，请运行: uv sync")
    if problems:
        print("需要处理：")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    from trove.adapters.asr import download_model

    print(f"下载转写模型 {config.asr_model} …")
    try:
        path = download_model(config.asr_model)
    except Exception as exc:  # noqa: BLE001 - setup reports the download failure
        print(f"模型下载失败: {exc}", file=sys.stderr)
        return 1
    print(f"模型已就绪: {path}")
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
        password = getpass.getpass("新密码: ")
        confirm = getpass.getpass("再输入一次: ")
    if password != confirm:
        print("两次输入的密码不一致。", file=sys.stderr)
        return 1
    if not password:
        print("密码不能为空。", file=sys.stderr)
        return 1
    config.set_password(password)
    config.config_path.chmod(0o600)
    print(f"密码已写入 {config.config_path}（权限 0600）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
