"""Capture the throwaway collections/ebooks prototype screens.

Usage:
    .venv/bin/python .scratch/collections-ebooks/prototype/capture.py

Requires the repo's Playwright Chromium. Writes PNGs next to this file in
``screenshots/``. This script is prototype tooling, not production code.
"""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "screenshots"


def main() -> None:
    OUT.mkdir(exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1700, "height": 1200}, device_scale_factor=2)

        for filename in ("android.html", "host-console.html"):
            page.goto((ROOT / filename).as_uri())
            page.wait_for_timeout(400)
            page.evaluate("document.fonts.ready")
            for frame in page.locator("[data-shot]").all():
                name = frame.get_attribute("data-shot")
                if not name:
                    continue
                frame.scroll_into_view_if_needed()
                frame.screenshot(path=str(OUT / f"{name}.png"))
                print(f"wrote {OUT / f'{name}.png'}")

            page.screenshot(path=str(OUT / f"_overview-{filename.removesuffix('.html')}.png"), full_page=True)
            print(f"wrote overview for {filename}")

        browser.close()


if __name__ == "__main__":
    main()
