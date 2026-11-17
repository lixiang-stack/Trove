#!/usr/bin/env python3
"""Dump or drive visible Android UI semantics.

Usage:
  scripts/android/ui-dump.py [--screenshot PATH] [--all] [--json] [--adb PATH]
  scripts/android/ui-dump.py --wait-text TEXT [--timeout SECONDS]
  scripts/android/ui-dump.py --tap-text TEXT [--timeout SECONDS]
  scripts/android/ui-dump.py --wait-desc DESC
  scripts/android/ui-dump.py --tap-desc DESC
  scripts/android/ui-dump.py --wait-id RESOURCE_ID
  scripts/android/ui-dump.py --tap-id RESOURCE_ID

The dump is read from uiautomator; only nodes with text, content-desc, or a
Compose testTag/resource-id are printed by default. Wait/tap options poll until
the node appears, then optionally tap its centre.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
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


def read_hierarchy(adb_path: str) -> ET.Element:
    adb(adb_path, "shell", "uiautomator", "dump", REMOTE_DUMP)
    xml_text = adb(adb_path, "exec-out", "cat", REMOTE_DUMP)
    start = xml_text.find("<hierarchy")
    if start < 0:
        raise SystemExit("uiautomator returned no hierarchy")
    return ET.fromstring(xml_text[start:])


def node_info(node: ET.Element) -> dict:
    return {
        "class": node.get("class", ""),
        "text": (node.get("text") or "").strip(),
        "desc": (node.get("content-desc") or "").strip(),
        "id": (node.get("resource-id") or "").strip(),
        "bounds": node.get("bounds") or "",
        "clickable": node.get("clickable") == "true",
    }


def walk_nodes(hierarchy: ET.Element):
    for node in hierarchy.iter("node"):
        yield node_info(node)


def find_node(hierarchy: ET.Element, *, text: str | None, desc: str | None, resource_id: str | None):
    for info in walk_nodes(hierarchy):
        if text is not None and info["text"] == text:
            return info
        if desc is not None and info["desc"] == desc:
            return info
        if resource_id is not None and info["id"] == resource_id:
            return info
    return None


def parse_bounds(value: str) -> tuple[int, int, int, int] | None:
    try:
        left, top, right, bottom = (
            int(part) for part in value.replace("][", ",").strip("[]").split(",")
        )
    except (ValueError, TypeError):
        return None
    return left, top, right, bottom


def tap(adb_path: str, info: dict) -> None:
    bounds = parse_bounds(info["bounds"])
    if bounds is None:
        raise SystemExit(f"cannot parse bounds: {info['bounds']!r}")
    left, top, right, bottom = bounds
    adb(adb_path, "shell", "input", "tap", str((left + right) // 2), str((top + bottom) // 2))


def print_dump(hierarchy: ET.Element, *, show_all: bool, as_json: bool) -> None:
    if as_json:
        print(json.dumps(list(walk_nodes(hierarchy)), ensure_ascii=False, indent=2))
        return

    def walk(node: ET.Element, depth: int = 0) -> None:
        info = node_info(node)
        if show_all or info["text"] or info["desc"] or info["id"]:
            label = " | ".join(
                part
                for part in (
                    f"text={info['text']!r}" if info["text"] else "",
                    f"desc={info['desc']!r}" if info["desc"] else "",
                    f"id={info['id']}" if info["id"] else "",
                    f"clickable={info['clickable']}" if info["clickable"] else "",
                    info["bounds"],
                )
                if part
            )
            print(f"{'  ' * depth}{info['class'] or '?'}: {label}")
        for child in node:
            walk(child, depth + 1)

    for child in hierarchy:
        walk(child)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--screenshot", type=Path)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--adb")
    parser.add_argument("--timeout", type=float, default=10.0)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--wait-text")
    group.add_argument("--tap-text")
    group.add_argument("--wait-desc")
    group.add_argument("--tap-desc")
    group.add_argument("--wait-id")
    group.add_argument("--tap-id")
    args = parser.parse_args()

    wait_text = args.wait_text or args.tap_text
    wait_desc = args.wait_desc or args.tap_desc
    wait_id = args.wait_id or args.tap_id
    should_tap = bool(args.tap_text or args.tap_desc or args.tap_id)
    waits = wait_text is not None or wait_desc is not None or wait_id is not None

    adb_path = find_adb(args.adb)
    if not waits:
        hierarchy = read_hierarchy(adb_path)
        print_dump(hierarchy, show_all=args.all, as_json=args.json)
    else:
        deadline = time.monotonic() + args.timeout
        found = None
        while time.monotonic() < deadline:
            hierarchy = read_hierarchy(adb_path)
            found = find_node(
                hierarchy,
                text=wait_text,
                desc=wait_desc,
                resource_id=wait_id,
            )
            if found is not None:
                break
            time.sleep(0.5)
        if found is None:
            target = wait_text or wait_desc or wait_id
            print(f"UI node not found within {args.timeout:g}s: {target!r}", file=sys.stderr)
            return 1
        print(json.dumps(found, ensure_ascii=False))
        if should_tap:
            tap(adb_path, found)

    if args.screenshot:
        args.screenshot.parent.mkdir(parents=True, exist_ok=True)
        args.screenshot.write_bytes(adb(adb_path, "exec-out", "screencap", "-p", binary=True))
        print(f"screenshot: {args.screenshot}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
