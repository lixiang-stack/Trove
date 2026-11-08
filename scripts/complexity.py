#!/usr/bin/env python3
"""Incremental complexity gate for Python code.

Usage:
  python3 scripts/complexity.py --changed [BASE]   # default HEAD^; manual comparison
  python3 scripts/complexity.py --staged           # staged files; pre-commit
  python3 scripts/complexity.py --push             # branch changes vs upstream; pre-push
  python3 scripts/complexity.py --audit            # full scan; manual use

Design:
- Compare function-level cyclomatic complexity against the base revision.
- Report only new functions, increased complexity, or crossings above the threshold.
- Exit 1 when findings exist; infrastructure failures print a skip message and exit 0.
- Detailed report: $(git rev-parse --git-dir)/complexity/report.md.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# radon cyclomatic complexity; functions above this threshold block commit/push.
THRESHOLD = 20
SKIP_PARTS = {
    ".git",
    ".worktree",
    "__pycache__",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    "vendor",
    "tests",
    "test",
    "__tests__",
}
SKIP_PREFIXES = (".scratch/", "docs/", "scripts/", "deploy/")


@dataclass
class Finding:
    file: str
    function: str
    base: int | None
    current: int
    threshold: int
    status: str  # new / increased / audit


def run(cmd: list[str], timeout: float | None = None) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            cmd,
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        # A missing or slow tool must not break the hook.
        return subprocess.CompletedProcess(cmd, 127, "", str(exc))


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return run(["git", *args])


def git_dir() -> Path:
    out = git("rev-parse", "--git-dir")
    return ROOT / out.stdout.strip() if out.returncode == 0 else ROOT / ".git"


def relative_path(path: str) -> str:
    try:
        return str(Path(path).resolve().relative_to(ROOT))
    except ValueError:
        return path


def resolve_push_base() -> str:
    for ref in ("@{push}", "origin/main"):
        if git("rev-parse", "--verify", "--quiet", ref).returncode != 0:
            continue
        merge = git("merge-base", ref, "HEAD")
        if merge.returncode == 0:
            return merge.stdout.strip()
    head_parent = git("rev-parse", "--verify", "--quiet", "HEAD^")
    return head_parent.stdout.strip() if head_parent.returncode == 0 else ""


def is_scan_file(path: str) -> bool:
    if any(part in SKIP_PARTS for part in Path(path).parts):
        return False
    if path.startswith(SKIP_PREFIXES):
        return False
    name = Path(path).name
    if name == "conftest.py" or name.startswith("test_") or name.endswith("_test.py"):
        return False
    return path.endswith(".py")


def tracked_files() -> list[str]:
    out = git("ls-files", "--", "*.py")
    return [line for line in out.stdout.splitlines() if is_scan_file(line)]


def changed_files(base: str) -> list[str]:
    if not base:
        return []
    out = git("diff", "--name-only", "--diff-filter=ACMR", base, "HEAD", "--", "*.py")
    return [line for line in out.stdout.splitlines() if is_scan_file(line)]


def staged_files() -> list[str]:
    out = git("diff", "--cached", "--name-only", "--diff-filter=ACMR", "--", "*.py")
    return [line for line in out.stdout.splitlines() if is_scan_file(line)]


def python_cmd() -> list[str] | None:
    if shutil.which("radon"):
        return ["radon", "cc", "-j"]
    if shutil.which("uvx"):
        return ["uvx", "radon", "cc", "-j"]
    if importlib.util.find_spec("radon") is not None:
        return [sys.executable, "-m", "radon", "cc", "-j"]
    return None


def parse_radon(stdout: str, base_by_temp: dict[str, str]) -> dict[tuple[str, str], int]:
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return {}
    out: dict[tuple[str, str], int] = {}
    for path, blocks in data.items():
        file = base_by_temp.get(str(Path(path).resolve()), relative_path(path))
        for block in blocks:
            if block.get("type") not in {"function", "method"}:
                continue
            name = block.get("name", "<anonymous>")
            if block.get("classname"):
                name = f"{block['classname']}.{name}"
            out[(file, name)] = int(block.get("complexity", 0))
    return out


def python_metrics(files: list[str]) -> dict[tuple[str, str], int]:
    cmd = python_cmd()
    if cmd is None or not files:
        return {}
    proc = run([*cmd, *files], timeout=60)
    return parse_radon(proc.stdout, {})


def python_base_metrics(files: list[str], base: str) -> dict[tuple[str, str], int]:
    cmd = python_cmd()
    if cmd is None or not files or not base:
        return {}
    with tempfile.TemporaryDirectory(prefix="complexity-") as tmp:
        temp_by_original: dict[str, str] = {}
        for index, file in enumerate(files):
            shown = git("show", f"{base}:{file}")
            if shown.returncode != 0:
                continue
            target = Path(tmp) / f"{index}-{Path(file).name}"
            target.write_text(shown.stdout, encoding="utf-8")
            temp_by_original[str(target.resolve())] = file
        if not temp_by_original:
            return {}
        proc = run([*cmd, *temp_by_original], timeout=60)
        return parse_radon(proc.stdout, temp_by_original)


def collect(files: list[str], base: str, audit: bool) -> list[Finding]:
    current = python_metrics(files)
    if not current:
        return []
    previous = {} if audit else python_base_metrics(files, base)
    findings: list[Finding] = []
    for (file, name), value in sorted(current.items()):
        if value <= THRESHOLD:
            continue
        old = previous.get((file, name))
        if audit:
            status = "audit"
        elif old is None:
            status = "new"
        elif value > old:
            status = "increased"
        else:
            continue
        findings.append(Finding(file, name, old, value, THRESHOLD, status))
    return findings


def write_report(findings: list[Finding], mode: str, base: str, files: list[str]) -> Path:
    target = git_dir() / "complexity"
    target.mkdir(parents=True, exist_ok=True)
    md = target / "report.md"
    js = target / "report.json"
    lines = [
        "# Complexity gate",
        "",
        f"- mode: `{mode}`",
        f"- base: `{base or 'audit'}`",
        f"- files: {len(files)}",
        f"- findings: {len(findings)}",
        "",
    ]
    if findings:
        lines += [
            "| Function | File | Base | Current | Threshold | Status |",
            "| --- | --- | ---: | ---: | ---: | --- |",
        ]
        for finding in findings:
            lines.append(
                f"| `{finding.function}` | `{finding.file}` | "
                f"{finding.base if finding.base is not None else '-'} | "
                f"{finding.current} | {finding.threshold} | {finding.status} |"
            )
    else:
        lines.append("No new or increased functions above threshold.")
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    js.write_text(
        json.dumps([asdict(finding) for finding in findings], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return md


def main() -> int:
    if os.environ.get("COMPLEXITY", "1") == "0":
        print("[complexity] skipped (COMPLEXITY=0)")
        return 0
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--changed", nargs="?", const="HEAD^", default=None)
    group.add_argument("--staged", action="store_true")
    group.add_argument("--push", action="store_true")
    group.add_argument("--audit", action="store_true")
    args = parser.parse_args()

    findings: list[Finding] = []
    try:
        if args.audit:
            mode, base = "audit", ""
            files = tracked_files()
        elif args.staged:
            mode = "staged"
            base = "HEAD" if git("rev-parse", "--verify", "--quiet", "HEAD").returncode == 0 else ""
            files = staged_files()
        elif args.push:
            mode, base = "push", resolve_push_base()
            files = changed_files(base)
        else:
            mode, base = "changed", args.changed or "HEAD^"
            files = changed_files(base)
        if not files:
            print(f"[complexity] no changed Python files since {base or 'N/A'}")
            return 0
        findings = collect(files, base, args.audit)
        report = write_report(findings, mode, base, files)
        print(
            f"[complexity] {mode} since {base or 'audit'}: "
            f"{len(files)} file(s), {len(findings)} finding(s)"
        )
        for finding in findings[:8]:
            before = "" if finding.base is None else f" ({finding.base}->{finding.current})"
            print(
                f"  {finding.function:32} {finding.file} "
                f"{finding.current}{before} [{finding.status}]"
            )
        if len(findings) > 8:
            print(f"  ... {len(findings) - 8} more")
        print(f"[complexity] detail: {report}")
        if findings:
            print(
                f"[complexity] blocked: {len(findings)} finding(s) above threshold "
                f"{THRESHOLD}; split them or set COMPLEXITY=0."
            )
    except Exception as exc:  # noqa: BLE001 - infrastructure failures must not block
        print(f"[complexity] scan skipped: {exc}")
        return 0
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
