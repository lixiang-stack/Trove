from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "android" / "sdk-properties.sh"


def _env(**overrides: str) -> dict[str, str]:
    environment = {
        key: value
        for key, value in os.environ.items()
        if key not in {"ANDROID_HOME", "ANDROID_SDK_ROOT"}
    }
    environment.update(overrides)
    return environment


def test_sdk_properties_writes_the_resolved_sdk_dir(tmp_path):
    sdk = tmp_path / "Android SDK"
    sdk.mkdir()
    output = tmp_path / "android" / "local.properties"

    subprocess.run(
        [str(SCRIPT), "--output", str(output)],
        env=_env(ANDROID_HOME=str(sdk), HOME=str(tmp_path)),
        check=True,
        capture_output=True,
        text=True,
    )

    assert output.read_text(encoding="utf-8") == f"sdk.dir={sdk.resolve()}\n"


def test_sdk_properties_explains_a_missing_sdk(tmp_path):
    result = subprocess.run(
        [str(SCRIPT), "--output", str(tmp_path / "local.properties")],
        env=_env(HOME=str(tmp_path)),
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "Android SDK not found" in result.stderr
    assert "ANDROID_HOME" in result.stderr
