from __future__ import annotations

import plistlib
import socket

from trove import deploy
from trove.cli import main


def test_launchd_agents_have_restart_logs_and_home(tmp_path):
    agents = deploy.build_agents(
        repo_root=tmp_path / "repo",
        home=tmp_path / "home",
        uv_path=tmp_path / "bin" / "uv",
        agents_dir=tmp_path / "agents",
    )
    written = deploy.write_agents(agents)

    assert len(written) == 2
    payloads = {
        path.name: plistlib.loads(path.read_bytes()) for path in written
    }
    api = payloads["com.trove.api.plist"]
    worker = payloads["com.trove.worker.plist"]
    for payload, label in (
        (api, "com.trove.api"),
        (worker, "com.trove.worker"),
    ):
        assert payload["Label"] == label
        assert payload["RunAtLoad"] is True
        assert payload["KeepAlive"] is True
        assert payload["EnvironmentVariables"]["TROVE_HOME"] == str(
            (tmp_path / "home").resolve()
        )
        assert payload["EnvironmentVariables"]["PATH"]
        assert payload["WorkingDirectory"] == str((tmp_path / "repo").resolve())
        assert payload["StandardOutPath"].startswith(
            str((tmp_path / "home").resolve() / "logs")
        )
        assert written[0].stat().st_mode & 0o777 == 0o600
    assert api["ProgramArguments"][-2:] == ["serve", "--no-worker"] or (
        "--no-worker" in api["ProgramArguments"]
    )
    assert "serve" in api["ProgramArguments"]
    assert "worker" in worker["ProgramArguments"]
    assert "--host" in api["ProgramArguments"]


def test_service_install_dry_run_renders_plists_and_keeps_data(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    original = home / "user-original.m4a"
    original.write_bytes(b"user-owned")
    agents_dir = tmp_path / "agents"
    monkeypatch.setenv("TROVE_HOME", str(home))
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/uv" if name == "uv" else None)

    code = main(
        [
            "service",
            "install",
            "--root",
            str(tmp_path / "repo"),
            "--home",
            str(home),
            "--agents-dir",
            str(agents_dir),
            "--dry-run",
        ]
    )

    assert code == 0
    assert (agents_dir / "com.trove.api.plist").is_file()
    assert (agents_dir / "com.trove.worker.plist").is_file()
    assert original.read_bytes() == b"user-owned"


def test_service_uninstall_dry_run_keeps_data(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    original = home / "library" / "source.json"
    original.parent.mkdir()
    original.write_text("{}", encoding="utf-8")
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "com.trove.api.plist").write_text("plist", encoding="utf-8")
    monkeypatch.setenv("TROVE_HOME", str(home))

    code = main(
        [
            "service",
            "uninstall",
            "--home",
            str(home),
            "--agents-dir",
            str(agents_dir),
            "--dry-run",
        ]
    )

    assert code == 0
    assert original.exists()
    assert (agents_dir / "com.trove.api.plist").exists()


def test_real_uninstall_removes_plists_but_keeps_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    original = home / "library" / "source.json"
    original.parent.mkdir()
    original.write_text("{}", encoding="utf-8")
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    plist = agents_dir / "com.trove.api.plist"
    plist.write_text("plist", encoding="utf-8")
    monkeypatch.setattr(deploy, "_bootout", lambda label: None)

    removed = deploy.uninstall(agents_dir=agents_dir, dry_run=False)

    assert removed == [plist]
    assert not plist.exists()
    assert original.exists()


def test_doctor_accepts_a_running_trove_port(api_host, monkeypatch, capsys):
    from urllib.parse import urlsplit

    monkeypatch.setenv("TROVE_HOME", str(api_host.config.home))
    monkeypatch.setenv("TROVE_PORT", str(urlsplit(api_host.base_url).port))
    code = main(["doctor"])
    output = capsys.readouterr().out
    assert "in use by Trove (running)" in output
    assert "already in use; stop the other process" not in output
    assert code in {0, 1}  # unrelated ASR/model warnings depend on the machine


def test_doctor_reports_port_in_use(tmp_path, monkeypatch, capsys):
    from trove.config import Config
    from trove.db.engine import upgrade_database

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    config = Config(home=tmp_path / "Trove", port=port)
    config.ensure_layout()
    upgrade_database(config)
    config.set_password("test-password")
    monkeypatch.setenv("TROVE_HOME", str(config.home))
    monkeypatch.setenv("TROVE_PORT", str(port))
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", port))
        sock.listen()
        code = main(["doctor"])
    output = capsys.readouterr().out
    assert code == 1
    assert "already in use" in output
