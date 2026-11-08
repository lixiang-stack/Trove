from __future__ import annotations

import argparse
import getpass
import shutil
import subprocess
import sys

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
from trove.logging_setup import configure_logging
from trove.worker import run_worker


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="trove", description="Trove Host")
    parser.add_argument("--version", action="version", version=f"trove {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve = subparsers.add_parser("serve", help="run the API and web shell")
    serve.add_argument("--host", default=None)
    serve.add_argument("--port", type=int, default=None)
    serve.add_argument("--lan", action="store_true", help="bind all interfaces")

    subparsers.add_parser("worker", help="run the processing worker")

    db = subparsers.add_parser("db", help="database commands")
    db_sub = db.add_subparsers(dest="db_command", required=True)
    db_sub.add_parser("upgrade", help="apply migrations")

    subparsers.add_parser("doctor", help="check Host dependencies and layout")

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
        run_worker(runtime)
        return 0
    if args.command == "db":
        return _db(config)
    if args.command == "doctor":
        return _doctor(config)
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
    app = create_app(config)
    uvicorn.run(app, host=host, port=port, log_level="info")
    return 0


def _db(config) -> int:
    config.ensure_layout()
    upgrade_database(config)
    current = current_revision(_engine(config))
    print(f"数据库已迁移到 {current}")
    return 0


def _engine(config):
    from sqlalchemy import create_engine

    return create_engine(f"sqlite:///{config.db_path}")


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

    if problems:
        print("\n需要处理：")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("\nHost 检查通过。")
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
