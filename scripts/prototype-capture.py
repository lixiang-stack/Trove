#!/usr/bin/env python3
"""Capture static prototype frames to PNGs.

Frames are elements marked with ``data-shot="name"`` in a local HTML file.
The script also writes a full-page overview per file.

Usage:
    uv run python scripts/prototype-capture.py path/to/prototype.html
    uv run python scripts/prototype-capture.py .scratch/<feature>/prototype \
        --out .scratch/<feature>/prototype/screenshots

Requires the repo's Playwright Chromium (``uv run playwright install chromium``).
"""

from __future__ import annotations

import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", type=Path, help="HTML file or directory of HTML files")
    parser.add_argument("--out", type=Path, default=None, help="screenshot directory")
    parser.add_argument("--selector", default="[data-shot]", help="frame selector")
    parser.add_argument("--wait-ms", type=int, default=400, help="settle time per page")
    parser.add_argument("--width", type=int, default=1700)
    parser.add_argument("--height", type=int, default=1200)
    parser.add_argument("--scale", type=float, default=2.0)
    args = parser.parse_args()

    if args.target.is_dir():
        targets = sorted(args.target.rglob("*.html"))
    else:
        targets = [args.target]
    if not targets:
        raise SystemExit(f"no HTML files under {args.target}")

    out = args.out or targets[0].parent / "screenshots"
    out.mkdir(parents=True, exist_ok=True)
    used_names: dict[str, Path] = {}

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(
            viewport={"width": args.width, "height": args.height},
            device_scale_factor=args.scale,
        )
        for html in targets:
            page.goto(html.resolve().as_uri(), wait_until="load")
            page.wait_for_timeout(args.wait_ms)
            page.evaluate("document.fonts.ready")
            frames = page.locator(args.selector).all()
            if not frames:
                continue
            for frame in frames:
                name = frame.get_attribute("data-shot")
                if not name:
                    continue
                if name in used_names and used_names[name] != html:
                    name = f"{html.stem}-{name}"
                used_names[name] = html
                frame.scroll_into_view_if_needed()
                path = out / f"{name}.png"
                frame.screenshot(path=str(path))
                print(f"wrote {path}")
            overview = out / f"_overview-{html.stem}.png"
            page.screenshot(path=str(overview), full_page=True)
            print(f"wrote {overview}")
        browser.close()


if __name__ == "__main__":
    main()
