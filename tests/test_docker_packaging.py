from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_dockerfile_builds_a_non_root_runtime_with_optional_asr():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert dockerfile.count("\nFROM ") >= 2
    assert "ARG INSTALL_ASR=false" in dockerfile
    assert "uv sync" in dockerfile and "--extra asr" in dockerfile
    assert "USER trove" in dockerfile
    assert "TROVE_HOME=/data" in dockerfile
    assert "HEALTHCHECK" in dockerfile
    assert "EXPOSE 8765" in dockerfile


def test_dockerignore_excludes_local_and_secret_state():
    patterns = {
        line.strip()
        for line in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
        if line.strip()
    }

    assert {".git", ".worktree", ".venv", ".env", "tests", "models"} <= patterns
    assert "**/__pycache__" in patterns


def test_compose_publishes_only_loopback_and_keeps_named_data():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "trove-data:" in compose
    assert "127.0.0.1" in compose
    assert "worker-asr" in compose and "worker-download" in compose
    assert "profiles:" in compose
    assert "api_key" not in compose and "password" not in compose
    assert "stop_grace_period: 45s" in compose


def test_entrypoint_dispatches_init_and_trove_commands(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "calls.log"
    (bin_dir / "trove").write_text(
        f"#!/bin/sh\nprintf '%s\\n' \"$*\" >> {log}\n", encoding="utf-8"
    )
    (bin_dir / "python").write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    for name in ("trove", "python"):
        (bin_dir / name).chmod(0o755)
    entrypoint = ROOT / "docker" / "entrypoint.sh"
    subprocess.run(["sh", "-n", str(entrypoint)], check=True)
    environment = {"PATH": f"{bin_dir}:/usr/bin:/bin"}

    subprocess.run(
        ["/bin/sh", str(entrypoint), "init"],
        env=environment,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["/bin/sh", str(entrypoint), "doctor", "--json"],
        env=environment,
        check=True,
        capture_output=True,
    )

    assert log.read_text(encoding="utf-8").splitlines() == [
        "db upgrade",
        "doctor --json",
    ]


def _compose_config():
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("docker is not installed")
    result = subprocess.run(
        [
            docker,
            "compose",
            "--profile",
            "pools",
            "--profile",
            "caddy",
            "-f",
            str(ROOT / "docker-compose.yml"),
            "config",
            "--format",
            "json",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.skip(f"docker compose config unavailable: {result.stderr.strip()}")
    return json.loads(result.stdout)


def test_compose_config_declares_the_expected_contract():
    config = _compose_config()
    services = config["services"]

    assert {"init", "api", "worker", "worker-asr", "caddy"} <= set(services)
    assert services["worker-asr"]["command"][-2:] == ["--pool", "asr"]
    assert services["worker-asr"]["profiles"] == ["pools"]
    assert services["api"]["ports"][0]["host_ip"] == "127.0.0.1"
    assert services["api"]["depends_on"]["init"]["condition"] == (
        "service_completed_successfully"
    )
    assert "trove-data" in config["volumes"]
    assert {"/data"} <= {
        volume["target"] for volume in services["api"]["volumes"]
    }
