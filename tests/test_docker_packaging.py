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
    assert "ARG INSTALL_ASR=true" in dockerfile
    assert "uv sync" in dockerfile and "--extra asr" in dockerfile
    assert "--no-editable" not in dockerfile
    assert "COPY --chmod=0755 docker/entrypoint.sh" in dockerfile
    assert "COPY --chmod=0755 docker/trove" in dockerfile
    assert "COPY src /app/src" in dockerfile
    assert "PYTHONPATH=/app/src" in dockerfile
    assert "chown -R" not in dockerfile
    assert "USER trove" in dockerfile
    assert "TROVE_HOME=" not in dockerfile
    assert "build-essential" not in dockerfile
    assert "curl" in dockerfile
    assert "ca-certificates" not in dockerfile
    assert "urllib.request" not in dockerfile
    assert 'VOLUME ["/home/trove/Trove"]' in dockerfile
    assert "HEALTHCHECK" in dockerfile
    assert "EXPOSE 8765" in dockerfile


def test_dockerfile_keeps_build_metadata_out_of_cached_layers():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    # Build metadata changes on every release; keep it after apt and the app
    # copy so those layers stay cached.
    assert dockerfile.index("RUN apt-get update") < dockerfile.index(
        "ARG TROVE_BUILD_COMMIT"
    )
    assert dockerfile.index("RUN apt-get update") < dockerfile.index(
        "ENV PYTHONPATH"
    )
    assert dockerfile.index("COPY --from=builder") < dockerfile.index(
        "ARG TROVE_BUILD_COMMIT"
    )
    assert dockerfile.index("ARG TROVE_BUILD_COMMIT") < dockerfile.index(
        "MODELSCOPE_CACHE"
    )


def test_docker_trove_wrapper_runs_the_module_from_the_source_layer():
    wrapper = (ROOT / "docker" / "trove").read_text(encoding="utf-8")

    assert "exec /app/.venv/bin/python -m trove.cli" in wrapper
    assert wrapper.startswith("#!/bin/sh\n")


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
    assert "api_key" not in compose
    assert "trove-config:" not in compose
    assert "TROVE_PASSWORD" not in compose
    assert "curl" in compose
    assert "urllib.request" not in compose
    assert "stop_grace_period: 45s" in compose


def test_entrypoint_dispatches_init_and_trove_commands(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "calls.log"
    (bin_dir / "trove").write_text(
        "#!/bin/sh\n"
        f"printf '%s\\n' \"$*\" >> {log}\n"
        'if [ "$1" = "config" ] && [ "$2" = "init" ]; then\n'
        '  mkdir -p "$HOME/Trove"\n'
        '  printf \'[server]\\nhost = "0.0.0.0"\\n\' > "$HOME/Trove/config.toml"\n'
        "fi\n",
        encoding="utf-8",
    )
    (bin_dir / "python").write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    for name in ("trove", "python"):
        (bin_dir / name).chmod(0o755)
    entrypoint = ROOT / "docker" / "entrypoint.sh"
    subprocess.run(["sh", "-n", str(entrypoint)], check=True)
    home = tmp_path / "home"
    home.mkdir()
    environment = {
        "PATH": f"{bin_dir}:/usr/bin:/bin",
        "HOME": str(home),
    }

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
        "config init --host 0.0.0.0",
        "db upgrade",
        "config init --host 0.0.0.0",
        "doctor --json",
    ]
    assert (home / "Trove" / "config.toml").read_text(encoding="utf-8") == (
        '[server]\nhost = "0.0.0.0"\n'
    )
    assert not (home / ".config" / "trove").exists()


def test_entrypoint_defaults_legacy_config_to_container_host(tmp_path):
    trove = shutil.which("trove")
    if trove is None:
        pytest.skip("trove console script is not installed")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "trove").symlink_to(trove)
    (bin_dir / "python").write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    (bin_dir / "python").chmod(0o755)

    home = tmp_path / "home"
    data = home / "Trove"
    data.mkdir(parents=True)
    (data / "config.toml").write_text(
        'password_hash = "legacy-hash"\n'
        'session_secret = "legacy-secret"\n'
        "session_epoch = 0\n",
        encoding="utf-8",
    )

    subprocess.run(
        ["/bin/sh", str(ROOT / "docker" / "entrypoint.sh"), "init"],
        env={"PATH": f"{bin_dir}:/usr/bin:/bin", "HOME": str(home)},
        check=True,
        capture_output=True,
        text=True,
    )

    config = (data / "config.toml").read_text(encoding="utf-8")
    assert 'host = "0.0.0.0"' in config
    assert 'host = "127.0.0.1"' not in config
    assert (data / "state.toml").is_file()


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
    assert "/home/trove/Trove" in {
        volume["target"] for volume in services["api"]["volumes"]
    }
    assert "TROVE_PASSWORD" not in services["api"]["environment"]
    assert "trove-config" not in config["volumes"]
