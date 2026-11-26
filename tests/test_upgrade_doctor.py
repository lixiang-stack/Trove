from __future__ import annotations

import contextlib
import json
import shutil
import socket
import subprocess
import threading
from io import StringIO
from pathlib import Path

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from trove import __version__
from trove.app import create_app
from trove.cli import main
from trove.composition import build_runtime
from trove.config import Config
from trove.content_package import ContentPackage
from trove.db.engine import (
    _alembic_config,
    current_revision,
    head_revision,
    upgrade_database,
)
from trove.errors import PackageVersionError
from trove.worker import run_worker

from .fakes import FakeStack

PASSWORD = "test-password"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _configured_home(tmp_path, monkeypatch, *, migrate: bool = True) -> Config:
    config = Config(home=tmp_path / "Trove", port=_free_port())
    config.ensure_layout()
    if migrate:
        upgrade_database(config)
    config.set_password(PASSWORD)
    monkeypatch.setenv("TROVE_HOME", str(config.home))
    monkeypatch.setenv("TROVE_PORT", str(config.port))
    return config


def _doctor_payload(capsys) -> tuple[int, dict]:
    code = main(["doctor", "--json"])
    return code, json.loads(capsys.readouterr().out)


def test_doctor_json_has_a_stable_schema(tmp_path, monkeypatch, capsys):
    _configured_home(tmp_path, monkeypatch)

    code, payload = _doctor_payload(capsys)

    assert set(payload) == {"ok", "checks", "versions"}
    assert isinstance(payload["ok"], bool)
    assert code == (0 if payload["ok"] else 1)
    for entry in payload["checks"]:
        assert set(entry) == {"name", "status", "message", "fix"}
        assert entry["status"] in {"ok", "warn", "fail"}
    assert {
        "permissions",
        "database_revision",
        "fts5",
        "password",
        "port",
        "ffmpeg",
        "ffprobe",
        "yt_dlp",
        "asr",
        "content_packages",
        "worker",
        "disk",
    } <= {entry["name"] for entry in payload["checks"]}
    assert set(payload["versions"]) == {
        "trove",
        "python",
        "ffmpeg",
        "ffprobe",
        "yt_dlp",
        "sqlite",
        "asr_model",
    }
    assert payload["versions"]["trove"] == __version__


def test_doctor_json_completes_when_tools_and_model_are_missing(
    tmp_path, monkeypatch, capsys
):
    _configured_home(tmp_path, monkeypatch)
    monkeypatch.setattr("shutil.which", lambda name: None)
    monkeypatch.setattr("trove.cli._ytdlp_version", lambda path: None)
    monkeypatch.setattr("trove.adapters.asr.funasr_installed", lambda: False)

    code, payload = _doctor_payload(capsys)

    assert code == 1
    assert payload["ok"] is False
    checks = {entry["name"]: entry for entry in payload["checks"]}
    for name in ("ffmpeg", "ffprobe", "yt_dlp", "asr"):
        assert checks[name]["status"] == "fail"
        assert checks[name]["fix"]
    assert payload["versions"]["ffmpeg"] is None
    assert "password" in checks and checks["password"]["status"] == "ok"


def test_doctor_json_reports_an_unmigrated_database(tmp_path, monkeypatch, capsys):
    _configured_home(tmp_path, monkeypatch, migrate=False)

    code, payload = _doctor_payload(capsys)

    checks = {entry["name"]: entry for entry in payload["checks"]}
    assert code == 1
    assert payload["ok"] is False
    assert checks["database_revision"]["status"] == "fail"
    assert checks["database_revision"]["fix"] == "uv run trove db upgrade"


def test_doctor_json_is_valid_jq(tmp_path, monkeypatch):
    if shutil.which("jq") is None:
        pytest.skip("jq is not installed")
    _configured_home(tmp_path, monkeypatch)

    result = subprocess.run(
        ["jq", "-e", ".ok and (.checks | length > 0)"],
        input=_doctor_payload_stdout(),
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode in {0, 1}  # jq parsed; .ok may be false on this machine
    assert result.stderr == ""


def _doctor_payload_stdout() -> str:
    buffer = StringIO()
    with contextlib.redirect_stdout(buffer):
        main(["doctor", "--json"])
    return buffer.getvalue()


def test_health_includes_build_information(api_host, monkeypatch):
    monkeypatch.setenv("TROVE_BUILD_COMMIT", "abc123def456")
    monkeypatch.setenv("TROVE_BUILD_TIME", "2026-11-26T00:00:00Z")

    payload = api_host.client.get("/api/health").json()

    assert payload["api_version"] == __version__
    assert payload["build"] == {
        "version": __version__,
        "commit": "abc123def456",
        "build_time": "2026-11-26T00:00:00Z",
    }


def test_db_upgrade_backs_up_and_reports_the_previous_revision(
    tmp_path, monkeypatch, capsys
):
    config = _configured_home(tmp_path, monkeypatch, migrate=False)
    command.upgrade(_alembic_config(config), "0008_run_force")

    code = main(["db", "upgrade"])
    output = capsys.readouterr().out

    assert code == 0
    backup_line = next(line for line in output.splitlines() if "Database backup:" in line)
    backup = Path(backup_line.split(": ", 1)[1])
    assert backup.is_file()
    assert backup.stat().st_mode & 0o777 == 0o600
    backup_engine = create_engine(f"sqlite:///{backup}")
    try:
        assert current_revision(backup_engine) == "0008_run_force"
    finally:
        backup_engine.dispose()
    engine = create_engine(f"sqlite:///{config.db_path}")
    try:
        assert current_revision(engine) == head_revision(config)
    finally:
        engine.dispose()
    assert "Database migrated to" in output


def test_db_upgrade_failure_keeps_the_backup_and_prints_the_restore_command(
    tmp_path, monkeypatch, capsys
):
    config = _configured_home(tmp_path, monkeypatch, migrate=False)
    command.upgrade(_alembic_config(config), "0008_run_force")

    def fail(_config, _revision):
        raise RuntimeError("migration exploded")

    monkeypatch.setattr("trove.db.engine.command.upgrade", fail)

    code = main(["db", "upgrade"])
    error = capsys.readouterr().err

    assert code == 1
    assert "migration exploded" in error
    assert "Restore the pre-upgrade database with:" in error
    assert "cp " in error
    backup = Path(
        next(
            line.split("cp ", 1)[1].split(" ", 1)[0]
            for line in error.splitlines()
            if line.strip().startswith("cp ")
        )
    )
    assert backup.is_file()
    engine = create_engine(f"sqlite:///{config.db_path}")
    try:
        assert current_revision(engine) == "0008_run_force"
    finally:
        engine.dispose()


def test_db_upgrade_skips_backups_for_new_and_current_databases(tmp_path):
    config = Config(home=tmp_path / "Trove")

    assert upgrade_database(config) is None
    assert upgrade_database(config) is None
    assert list((config.home / "backups").glob("trove-*.db")) == []


def test_old_database_upgrades_to_head_and_doctor_passes(
    tmp_path, monkeypatch, capsys
):
    config = _configured_home(tmp_path, monkeypatch, migrate=False)
    command.upgrade(_alembic_config(config), "0008_run_force")
    monkeypatch.setattr("trove.adapters.asr.funasr_installed", lambda: True)
    monkeypatch.setattr("trove.adapters.asr.model_cached", lambda model: True)

    assert main(["db", "upgrade"]) == 0
    capsys.readouterr()
    code, payload = _doctor_payload(capsys)

    assert code == 0
    assert payload["ok"] is True
    checks = {entry["name"]: entry for entry in payload["checks"]}
    assert checks["database_revision"]["status"] == "ok"
    assert str(head_revision(config)) in checks["database_revision"]["message"]


def test_restored_backup_starts_a_worker_and_keeps_packages_readable(tmp_path):
    config = Config(home=tmp_path / "Trove", port=_free_port())
    upgrade_database(config)
    from trove.db.engine import backup_database

    backup = backup_database(config, revision="0009_external_call_cache")
    item_id = "item-restored"
    directory = config.library_dir / item_id
    directory.mkdir(parents=True)
    (directory / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "item_id": item_id,
                "created_at": 1,
                "updated_at": 2,
                "artifacts": [],
            }
        ),
        encoding="utf-8",
    )
    config.db_path.write_bytes(b"not a database")
    shutil.copyfile(backup, config.db_path)
    for suffix in ("-wal", "-shm"):
        Path(f"{config.db_path}{suffix}").unlink(missing_ok=True)

    runtime = build_runtime(config, FakeStack().ports())
    stop = threading.Event()
    stop.set()
    run_worker(runtime, stop)
    assert ContentPackage(config).read_manifest(item_id) is not None


def _unsupported_manifest(config: Config) -> None:
    item_id = "item-unsupported"
    directory = config.library_dir / item_id
    directory.mkdir(parents=True)
    (directory / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 999,
                "item_id": item_id,
                "created_at": 1,
                "updated_at": 2,
                "artifacts": [],
            }
        ),
        encoding="utf-8",
    )


def test_unsupported_manifest_refuses_api_and_worker_startup(tmp_path):
    config = Config(home=tmp_path / "Trove", port=_free_port())
    upgrade_database(config)
    _unsupported_manifest(config)

    with (
        pytest.raises(PackageVersionError, match="Unsupported content package"),
        TestClient(create_app(config, FakeStack().ports())),
    ):
        pass

    runtime = build_runtime(config, FakeStack().ports())
    with pytest.raises(PackageVersionError, match="Unsupported content package"):
        run_worker(runtime, threading.Event())


def test_release_check_script_parses():
    script = Path(__file__).resolve().parents[1] / "scripts" / "release-check.sh"
    subprocess.run(["sh", "-n", str(script)], check=True)
    assert "scripts/check.sh --full" in script.read_text(encoding="utf-8")


def test_unsupported_manifest_is_reported_by_doctor(tmp_path, monkeypatch, capsys):
    config = _configured_home(tmp_path, monkeypatch)
    _unsupported_manifest(config)
    assert ContentPackage(config).incompatible_manifests()

    code, payload = _doctor_payload(capsys)

    checks = {entry["name"]: entry for entry in payload["checks"]}
    assert code == 1
    assert payload["ok"] is False
    assert checks["content_packages"]["status"] == "fail"
    assert "schema_version" in checks["content_packages"]["message"]
