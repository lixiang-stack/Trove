from __future__ import annotations

import os
import subprocess
from functools import lru_cache
from pathlib import Path

from trove import __version__

_REPO_ROOT = Path(__file__).resolve().parent.parent


@lru_cache(maxsize=1)
def _git_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def build_info() -> dict[str, str | None]:
    return {
        "version": __version__,
        "commit": os.environ.get("TROVE_BUILD_COMMIT") or _git_commit(),
        "build_time": os.environ.get("TROVE_BUILD_TIME") or None,
    }
