# Prototype workflow

Use this when an App page or interaction changes and the prototype has not
already been approved. The goal is to agree on layout and interaction **before**
production code, not to build a second product UI.

## Baseline

1. Read `android/AGENTS.md` §5.1 and the existing shell prototype
   `.scratch/trove-mvp/prototype/mobile-shell.html`.
2. Reuse its visual language: paper/ink/accent, serif titles, rounded shapes,
   existing cover placeholders, bottom nav. Do not introduce a second theme.
3. Keep the prototype static: no backend, no persistence, no remote assets.

## Layout

```text
.scratch/<feature>/prototype/
├── index.html          # entry + review checklist
├── android.html        # phone frames
├── host-console.html   # desktop frames, when the Host Console changes
├── *.css
├── README.md
└── screenshots/
```

- One frame per state (empty, detecting, preview, error, result, etc.).
- Mark every frame with `data-shot="unique-name"`.
- Phone frames: 390 × 844. Host Console frames: 1280 × 900.
- Use the same feature slug as `.scratch/<feature>/spec.md`.

## Capture screenshots

```bash
uv run playwright install chromium   # once
uv run python scripts/prototype-capture.py \
  .scratch/<feature>/prototype/android.html \
  --out .scratch/<feature>/prototype/screenshots
```

Pass a directory as the target to capture every HTML file with frames. The
script writes `<data-shot>.png` plus `_overview-<file>.png`; it requires
Playwright Chromium.

## Review and handoff

- Open `index.html` in a browser and review the screenshots with the user.
- Ask for confirmation before writing production code; list explicit changes
  rather than silently choosing a layout.
- After implementation, compare the affected screens to the prototype and list
  every difference or exception. If no physical device is available, say so and
  keep the real-device screenshot check as an open acceptance item.
