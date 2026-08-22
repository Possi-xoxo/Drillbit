# Drillbit 1.0.0

Drillbit is an offline Windows desktop application for turning images into editable DMC diamond-art patterns. One logical pattern cell represents one physical drill.

## What Drillbit supports

- JPG/JPEG, PNG, WEBP, and BMP source images
- Exact dimensions, crop/reposition controls, adjustments, and optional dithering
- Conversion to the validated 489-color DMC Reference Palette with 8–64 target colors
- Persistent **Colors I Own** inventory and owned-colors-only conversion
- Optional source transparency and empty/no-drill cells
- Pencil, Eyedropper, Flood Fill, Eraser, selection, copy/paste, move, fill, clear, and color replacement
- Transactional Undo/Redo for logical pattern edits
- Non-destructive Confetti Inspector and aligned Source Image Overlay
- Square or Round Finished Preview without changing the logical grid
- PNG export and physically scaled, tiled PDFs with deterministic symbols and legends
- Native `.drillbit` projects containing the source, settings, logical grid, edits, and project preferences
- Read compatibility with legacy `.diamond` projects
- Per-user single-instance behavior and local rotating crash diagnostics

## Basic workflow

1. Choose **Open Image** or drop a supported image onto Drillbit.
2. Set the dimensions, image fit, maximum colors, and optional adjustments.
3. Use **2. Edit Pattern** for cell-level edits and Undo/Redo.
4. Use **3. Finished Preview** to inspect Square or Round drills.
5. Choose **Save Project** to create a `.drillbit` project.
6. Export a PNG or create a tiled **Print Pattern PDF**. Print at **100% / Actual Size**, never Fit to Page.

View-only controls—including zoom, pan, selection creation, source-overlay controls, color highlighting, confetti navigation, and Finished Preview zoom—do not alter the logical pattern. Exports use the edited grid and never include editor overlays.

## Projects and compatibility

`.drillbit` is the native extension. Projects are self-contained ZIP archives with versioned JSON and an optional embedded PNG source. Version 1.0.0 retains the existing internal schema; the extension migration does not change pattern data.

Legacy `.diamond` projects use the same loader. Drillbit does not rewrite them on open. The first normal Save requests a `.drillbit` destination and leaves the legacy file untouched. Older Drillbit builds are not expected to recognize the new extension.

Future Windows packaging should associate only `.drillbit` with **Drillbit Project** and `Drillbit.exe`. Drillbit does not modify registry associations at runtime and does not claim `.diamond` globally.

## Colors I Own

The global inventory is stored at `%LOCALAPPDATA%\Drillbit\owned_colors.json` and survives executable replacement. Invalid codes are ignored. If the JSON is corrupt, Drillbit preserves it, logs the problem, and starts safely with an empty inventory.

## Diagnostics

Logs are stored under `%LOCALAPPDATA%\Drillbit\logs\`. Use **Help > Diagnostics** to open the latest log, open its folder, or copy a diagnostic summary. Logs rotate at a bounded size and contain runtime details, settings summaries, timings, significant actions, and tracebacks—not source-image pixels or telemetry. Exception hooks, thread exception logging, `faulthandler`, and a session marker provide crash coverage.

## Development and testing

Python 3.11–3.13 is recommended.

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe main.py
```

Build the Windows release with:

```powershell
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

The PyInstaller folder build is `dist\Drillbit\Drillbit.exe`; its adjacent `_internal` folder is required. The packaged Windows target does not require system Python.

## Repository structure

- `main.py` — entry point
- `app/version.py` — authoritative release identity
- `app/main_window.py` — main UI and file-operation boundaries
- `app/project_format.py` / `app/project_io.py` — project routing and persistence
- `app/image_processor.py` / `app/pattern_converter.py` — source preparation and DMC conversion
- `app/palette_system.py` / `palettes/dmc.json` — validated palette resources
- `app/pattern_model.py` — logical grid and exact delta Undo/Redo
- `app/pattern_analysis.py` — deterministic region/confetti analysis
- `app/widgets/` — crop, editor, inventory, and image controls
- `app/finished_preview.py` — cached Square/Round rendering
- `app/exporter.py` / `app/pdf_exporter.py` — PNG and tiled symbolized PDF export
- `app/logging_manager.py` — logs, crash hooks, timings, and session markers
- `tests/` — regression coverage

## Palette data

The DMC palette was mechanically extracted from the open-source pyxstitch 1.11.1 floss table. Its GPL-3.0 license is retained at `palettes/LICENSE-pyxstitch-GPL3.txt`. RGB values are screen-reference approximations; physical appearance varies by display, lighting, material, dye lot, and manufacturer.

## Current limitations

- Very large patterns and high-resolution PDF pages can be memory intensive.
- Conversion, confetti analysis, and PDF export currently run synchronously in the GUI process.
- The portable 1.0 folder build is not yet an installer and does not register file associations.
