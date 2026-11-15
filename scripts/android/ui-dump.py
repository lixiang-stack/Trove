#!/usr/bin/env python3
"""Dump visible Android UI semantics and optionally take a screenshot.

Usage:
  scripts/android/ui-dump.py [--screenshot PATH] [--all] [--adb PATH]

Large UI trees are noisy; by default only nodes with text, content-desc, or a
Compose testTag (resource-id) are printed.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

REMOTE_DUMP = "/sdcard/trove-window.xml"


def find_adb(explicit: str | None) -> str:
    if explicit:
        return explicit
    if os.environ.get("ADB"):
        return os.environ["ADB"]
    for root in (os.environ.get("ANDROID_HOME"), os.environ.get("ANDROID_SDK_ROOT")):
        if root:
            candidate = Path(root) / "platform-tools" / "adb"
            if candidate.is_file():
                return str(candidate)
    candidate = Path.home() / "Library" / "Android" / "sdk" / "platform-tools" / "adb"
    if candidate.is_file():
        return str(candidate)
    found = shutil.which("adb")
    if found:
        return found
    raise SystemExit("adb not found; set ANDROID_HOME or pass --adb")


def adb(adb_path: str, *args: str, binary: bool = False):
    result = subprocess.run(
        [adb_path, *args],
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        sys.stderr.write(result.stderr.decode("utf-8", "replace"))
        raise SystemExit(result.returncode)
    return result.stdout if binary else result.stdout.decode("utf-8", "replace")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--screenshot", type=Path)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--adb")
    args = parser.parse_args()

    adb_path = find_adb(args.adb)
    adb(adb_path, "shell", "uiautomator", "dump", REMOTE_DUMP)
    xml_text = adb(adb_path, "exec-out", "cat", REMOTE_DUMP)
    start = xml_text.find("<hierarchy")
    if start < 0:
        raise SystemExit("uiautomator returned no hierarchy")
    hierarchy = ET.fromstring(xml_text[start:])

    def walk(node: ET.Element, depth: int = 0) -> None:
        text = (node.get("text") or "").strip()
        desc = (node.get("content-desc") or "").strip()
        resource = (node.get("resource-id") or "").strip()
        bounds = node.get("bounds") or ""
        clickable = node.get("clickable") == "true"
        if args.all or text or desc or resource:
            label = " | ".join(
                part
                for part in (
                    f"text={text!r}" if text else "",
                    f"desc={desc!r}" if desc else "",
                    f"id={resource}" if resource else "",
                    f"clickable={clickable}" if clickable else "",
                    bounds,
                )
                if part
            )
            print(f"{'  ' * depth}{node.get('class', '?')}: {label}")
        for child in node:
            walk(child, depth + 1)

    for child in hierarchy:
        walk(child)

    if args.screenshot:
        args.screenshot.parent.mkdir(parents=True, exist_ok=True)
        args.screenshot.write_bytes(adb(adb_path, "exec-out", "screencap", "-p", binary=True))
        print(f"screenshot: {args.screenshot}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
