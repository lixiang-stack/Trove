from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from trove.errors import ProcessingCancelled, ProcessingError
from trove.ports import StageContext

POLL_INTERVAL = 0.1
TERMINATE_GRACE = 3.0


@dataclass(slots=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


def run_command(
    context: StageContext,
    command: list[str],
    *,
    timeout: float | None = None,
    cwd: Path | None = None,
    error_code: str = "internal.error",
) -> CommandResult:
    context.check_cancelled()
    with (
        tempfile.TemporaryFile(mode="w+", encoding="utf-8") as stdout_file,
        tempfile.TemporaryFile(mode="w+", encoding="utf-8") as stderr_file,
    ):
        try:
            process = subprocess.Popen(
                command,
                cwd=cwd,
                stdout=stdout_file,
                stderr=stderr_file,
                text=True,
                start_new_session=True,
            )
        except FileNotFoundError as exc:
            raise ProcessingError(error_code, f"Command not found: {command[0]}") from exc
        started = time.monotonic()
        while process.poll() is None:
            if context.should_cancel():
                _terminate(process)
                raise ProcessingCancelled("cancelled")
            if timeout is not None and time.monotonic() - started > timeout:
                _terminate(process)
                raise ProcessingError(error_code, "External command timed out")
            time.sleep(POLL_INTERVAL)
        stdout_file.seek(0)
        stderr_file.seek(0)
        return CommandResult(
            returncode=process.returncode or 0,
            stdout=stdout_file.read(),
            stderr=stderr_file.read(),
        )


def _terminate(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=TERMINATE_GRACE)
    except subprocess.TimeoutExpired:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        process.wait(timeout=TERMINATE_GRACE)
