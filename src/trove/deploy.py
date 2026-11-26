from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from trove.domain.worker_pools import ALL_POOL, POOL_NAMES

API_LABEL = "com.trove.api"
WORKER_LABEL = "com.trove.worker"
DEFAULT_AGENTS_DIR = Path("~/Library/LaunchAgents")


class DeployError(RuntimeError):
    """Raised when a launchd agent cannot be rendered or installed."""


@dataclass(frozen=True, slots=True)
class LaunchdAgent:
    label: str
    path: Path
    payload: dict


def default_agents_dir() -> Path:
    return DEFAULT_AGENTS_DIR.expanduser()


def worker_label(pool: str) -> str:
    return WORKER_LABEL if pool == ALL_POOL else f"{WORKER_LABEL}.{pool}"


def worker_arguments(pool: str) -> list[str]:
    if pool == ALL_POOL:
        return ["worker"]
    return ["worker", "--pool", pool]


def build_agents(
    *,
    repo_root: Path,
    home: Path,
    uv_path: Path,
    agents_dir: Path,
    worker_pools: Sequence[str] = (ALL_POOL,),
) -> list[LaunchdAgent]:
    unknown_pools = set(worker_pools) - set(POOL_NAMES)
    if unknown_pools:
        raise DeployError(
            f"Unknown worker pool: {', '.join(sorted(unknown_pools))}; "
            f"choose from: {', '.join(POOL_NAMES)}"
        )
    repo_root = repo_root.expanduser().resolve()
    home = home.expanduser().resolve()
    logs = home / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    logs.chmod(0o700)
    path_env = os.environ.get("PATH", "/usr/bin:/bin:/usr/sbin:/sbin")

    def common(label: str) -> dict:
        return {
            "WorkingDirectory": str(repo_root),
            "EnvironmentVariables": {"TROVE_HOME": str(home), "PATH": path_env},
            "RunAtLoad": True,
            "KeepAlive": True,
            "ThrottleInterval": 10,
            "ProcessType": "Background",
            "StandardOutPath": str(logs / f"{label}.log"),
            "StandardErrorPath": str(logs / f"{label}.log"),
        }

    agents = [
        LaunchdAgent(
            label=API_LABEL,
            path=agents_dir / f"{API_LABEL}.plist",
            payload={
                "Label": API_LABEL,
                "ProgramArguments": [
                    str(uv_path),
                    "run",
                    "--directory",
                    str(repo_root),
                    "trove",
                    "serve",
                    "--no-worker",
                    "--host",
                    "127.0.0.1",
                ],
                **common(API_LABEL),
            },
        ),
    ]
    for pool in dict.fromkeys(worker_pools or (ALL_POOL,)):
        label = worker_label(pool)
        agents.append(
            LaunchdAgent(
                label=label,
                path=agents_dir / f"{label}.plist",
                payload={
                    "Label": label,
                    "ProgramArguments": [
                        str(uv_path),
                        "run",
                        "--directory",
                        str(repo_root),
                        "trove",
                        *worker_arguments(pool),
                    ],
                    **common(label),
                },
            )
        )
    return agents


def write_agents(agents: list[LaunchdAgent]) -> list[Path]:
    written: list[Path] = []
    for agent in agents:
        agent.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = agent.path.with_name(f".{agent.path.name}.tmp")
        try:
            temporary.write_bytes(plistlib.dumps(agent.payload, sort_keys=False))
            temporary.chmod(0o600)
            os.replace(temporary, agent.path)
            agent.path.chmod(0o600)
        finally:
            temporary.unlink(missing_ok=True)
        written.append(agent.path)
    return written


def lint_agents(agents: list[LaunchdAgent]) -> None:
    if shutil.which("plutil") is None:
        return
    for agent in agents:
        result = subprocess.run(
            ["plutil", "-lint", str(agent.path)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise DeployError(f"Invalid launchd plist {agent.path}: {result.stderr.strip()}")


def install(
    *,
    repo_root: Path,
    home: Path,
    agents_dir: Path,
    uv_path: Path | None = None,
    worker_pools: Sequence[str] = (ALL_POOL,),
    dry_run: bool = False,
) -> list[Path]:
    uv_path = uv_path or _which("uv")
    agents = build_agents(
        repo_root=repo_root,
        home=home,
        uv_path=uv_path,
        agents_dir=agents_dir.expanduser().resolve(),
        worker_pools=worker_pools,
    )
    written = write_agents(agents)
    lint_agents(agents)
    if not dry_run:
        for agent in agents:
            _bootout(agent.label)
            _bootstrap(agent.path)
    return written


def uninstall(
    *,
    agents_dir: Path,
    worker_pools: Sequence[str] | None = None,
    dry_run: bool = False,
) -> list[Path]:
    agents_dir = agents_dir.expanduser().resolve()
    removed: list[Path] = []
    pools = tuple(worker_pools) if worker_pools is not None else POOL_NAMES
    labels = [API_LABEL, *(worker_label(pool) for pool in pools)]
    for label in dict.fromkeys(labels):
        path = agents_dir / f"{label}.plist"
        if not path.exists():
            continue
        if not dry_run:
            _bootout(label)
            path.unlink()
        removed.append(path)
    return removed


def _which(binary: str) -> Path:
    found = shutil.which(binary)
    if found is None:
        raise DeployError(f"{binary} is not installed or not on PATH")
    return Path(found)


def _domain() -> str:
    return f"gui/{os.getuid()}"


def _bootout(label: str) -> None:
    subprocess.run(
        ["launchctl", "bootout", f"{_domain()}/{label}"],
        capture_output=True,
        text=True,
        check=False,
    )


def _bootstrap(plist_path: Path) -> None:
    result = subprocess.run(
        ["launchctl", "bootstrap", _domain(), str(plist_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise DeployError(
            f"launchctl bootstrap failed for {plist_path.name}: {result.stderr.strip()}"
        )
