from __future__ import annotations

import os

from sqlalchemy import text

from trove.cli import main
from trove.config import Config
from trove.db.engine import (
    create_engine_for,
    current_revision,
    head_revision,
    upgrade_database,
)

from .conftest import PASSWORD


def test_layout_permissions_and_idempotence(tmp_path):
    config = Config(home=tmp_path / "Trove")
    config.ensure_layout()
    for directory in (
        config.home,
        config.library_dir,
        config.cache_dir,
        config.logs_dir,
        config.runs_log_dir,
        config.uploads_dir,
    ):
        assert directory.is_dir()
        assert directory.stat().st_mode & 0o777 == 0o700
    assert config.config_path.stat().st_mode & 0o777 == 0o600
    assert config.env_path.stat().st_mode & 0o777 == 0o600
    secret = config.session_secret
    config.ensure_layout()
    assert config.session_secret == secret


def test_db_upgrade_is_repeatable(tmp_path):
    config = Config(home=tmp_path / "Trove")
    config.ensure_layout()
    upgrade_database(config)
    first = current_revision(create_engine_for(config))
    upgrade_database(config)
    second = current_revision(create_engine_for(config))
    assert first == second == head_revision(config)


def test_sqlite_wal_and_foreign_keys(tmp_path):
    config = Config(home=tmp_path / "Trove")
    config.ensure_layout()
    upgrade_database(config)
    engine = create_engine_for(config)
    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA journal_mode")).scalar() == "wal"
        assert connection.execute(text("PRAGMA foreign_keys")).scalar() == 1
        assert connection.execute(text("PRAGMA busy_timeout")).scalar() == 15000


def test_health_reports_host_database_and_worker(api_host):
    response = api_host.client.get("/api/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["host"]["status"] == "ok"
    assert payload["database"]["status"] == "ok"
    assert payload["database"]["migration"]["up_to_date"] is True
    assert payload["database"]["fts5"] is True
    assert "worker" in payload


def test_base_layout_vendors_assets(api_host):
    response = api_host.client.get("/login")
    assert response.status_code == 200
    assert "/static/htmx.min.js?v=" in response.text
    assert "/static/pico.min.css?v=" in response.text
    assert "/static/app.css?v=" in response.text
    assert "/static/player.js?v=" in response.text
    assert "unpkg.com" not in response.text
    assert "cdn.jsdelivr.net" not in response.text


def test_login_and_home_smoke(host):
    assert host.client.get("/library").status_code == 303
    host.login()
    response = host.client.get("/library")
    assert response.status_code == 200
    assert "Library" in response.text
    payload = host.client.get("/api/health").json()
    assert payload["worker"]["status"] == "ok"


def test_doctor_reports_missing_tools(tmp_path, monkeypatch, capsys):
    config = Config(home=tmp_path / "Trove")
    config.ensure_layout()
    upgrade_database(config)
    config.set_password(PASSWORD)
    monkeypatch.setenv("TROVE_HOME", str(config.home))
    monkeypatch.setattr("shutil.which", lambda name: None)
    code = main(["doctor"])
    output = capsys.readouterr().out
    assert code == 1
    assert " brew install ffmpeg" in output
    assert "yt-dlp" in output


def test_logs_do_not_contain_secrets(api_host):
    api_host.login()
    response = api_host.client.post(
        "/login", data={"password": "wrong-password"}, headers={"origin": api_host.base_url}
    )
    assert response.status_code == 401
    log_text = (api_host.config.logs_dir / "trove.log").read_text(encoding="utf-8")
    assert "wrong-password" not in log_text
    assert PASSWORD not in log_text
    assert api_host.config.session_secret not in log_text
    assert "trove_session" not in log_text


def test_env_file_has_restrictive_mode(tmp_path):
    config = Config(home=tmp_path / "Trove")
    config.ensure_layout()
    assert os.stat(config.env_path).st_mode & 0o777 == 0o600


def test_serve_starts_embedded_worker_by_default(tmp_path, monkeypatch):
    config = Config(home=tmp_path / "Trove")
    config.ensure_layout()
    upgrade_database(config)
    monkeypatch.setenv("TROVE_HOME", str(config.home))
    started: list[object] = []

    def fake_start(config):
        started.append(config)
        return None

    monkeypatch.setattr("trove.cli._start_worker_child", fake_start)
    monkeypatch.setattr("uvicorn.run", lambda *args, **kwargs: None)
    assert main(["serve", "--host", "127.0.0.1", "--port", "8765"]) == 0
    assert started
    started.clear()
    assert main(["serve", "--no-worker"]) == 0
    assert started == []


def test_static_assets_are_versioned_and_revalidated(api_host):
    page = api_host.client.get("/login")
    assert page.headers["cache-control"] == "no-store"
    assert "app.css?v=" in page.text
    asset = api_host.client.get("/static/app.css")
    assert asset.status_code == 200
    assert asset.headers["cache-control"] == "no-cache"
