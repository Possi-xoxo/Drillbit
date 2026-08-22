# Diamond Art Converter

An offline Windows desktop app that turns photos into controlled diamond-art grids. One logical output pixel equals one physical drill. It supports JPG/JPEG, PNG, WEBP, and BMP; exact dimensions; fit/crop; median-cut color reduction; optional dithering and grids; adjustments; palette counts; and lossless PNG export.

Version 0.2 adds physical drill sizing, finished dimensions in metric and imperial units, size entry by diamonds or finished size, interactive drag/wheel cropping, and true-scale tiled US Letter PDF patterns with overlap, registration marks, calibration squares, and a color legend.

Version 0.3 makes the logical DMC-code grid authoritative and adds a searchable manual pattern editor. Automatic conversion is constrained to the built-in DMC Reference Palette. The editor supports zoom, middle-button pan, pencil strokes, eyedropper, four-direction flood fill, selected-color highlighting, global color replacement, undo/redo, used-color statistics, before/edited comparison, and self-contained `.diamond` project files.

Version 0.3.1 makes edit history transactional and observable: completed pencil strokes, flood fills, and replacements synchronously update Undo/Redo state, while no-op edits create no history.

Version 0.3.2 replaces the editor tool dropdown with an exclusive, clearly highlighted Pencil / Eyedropper / Flood Fill button group.

Version 0.4 treats Maximum Colors as a meaningful target. Palette optimization now analyzes candidate regions at logical drill resolution, balances coverage, CIELAB distinctiveness, spatial coherence, local contrast, and four-connected confetti metrics, considers close alternative DMC matches to avoid duplicate collapse, and remains deterministic.

Version 0.5 adds optional source-alpha preservation. Enable **Preserve Transparency** to convert low-coverage cells to empty/no-drill cells, exclude them from DMC selection and drill totals, edit them over a checkerboard with Pencil/Flood Fill/Eraser, preserve them in projects and PNG exports, and leave them empty in printable PDFs. The option defaults off, which composites source alpha onto pure white for backward-compatible conversion.

Version 0.6 makes initial palette construction fidelity-first. It analyzes a fixed 4-bit-per-channel histogram of up to 4,096 weighted source colors, unions multiple nearby DMC candidates for every source color, and grows the palette by the reduction in remaining CIELAB reconstruction error. Dominant cluster weights use a 0.72 power so large areas remain important without suppressing smaller color families. Confetti is measured after assignment and does not reject colors during palette construction.

Version 0.7 adds local crash diagnostics. Drillbit writes INFO-level rotating logs to `%LOCALAPPDATA%\Drillbit\logs\drillbit.log` and native Python fault output to `drillbit_fault.log`. Use **Help > Diagnostics > Open Latest Log** or **Open Log Folder** to retrieve them, then provide the latest log when investigating a crash. Logs include environment details, conversion settings and timings, memory-shape estimates, significant actions, and exception tracebacks; they do not contain source-image pixels, telemetry, or uploads. Python exception hooks and `faulthandler` improve coverage, but a sufficiently abrupt operating-system or native-library failure can still terminate the process before diagnostics are flushed.

Version 0.8 adds printable PDF symbols and dedicated legends without changing the on-screen editor. Every currently used DMC color receives a deterministic project-persisted ASCII symbol. Printable chart cells combine color and a high-contrast symbol, while transparent cells remain empty. PDF options allow symbols and legends to be disabled independently, and large legends automatically continue across pages.

Version 0.8.1 makes symbolized PDFs responsive in common viewers. Each chart tile is rendered once as a lossless 600-DPI image and embedded at the exact physical size dictated by the drill pitch. The searchable legend, calibration squares, footer, and registration marks remain vector PDF content. Export logging records per-tile raster, symbol, encoding, embedding, and final-save timings without logging individual cells.

## Run from source

Python 3.11–3.13 is recommended for packaging. A project-local portable Python 3.13 runtime is included for reproducible builds because Python 3.14 currently has a Qt/PyInstaller DLL packaging incompatibility.

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

Drop an image on the window or use **Open Image**. Drag within the crop rectangle to reposition the source and use the mouse wheel to zoom; Reset Crop restores the largest centered crop at the pattern aspect ratio. Pattern Pixels exports one pixel per drill; Large Reference Image enlarges each cell with nearest-neighbor scaling. Print Pattern PDF creates a physically scaled, multi-page chart; print it at **100% / Actual Size**, never Fit to Page.

After conversion, open **2. Edit Pattern**. Select a DMC color from the searchable list and use Pencil or Flood Fill, or use Eyedropper to pick from the design. The mouse wheel zooms the pattern and the middle mouse button pans. A continuous pencil drag is one undo action. Select a color in Used Colors, select its replacement in the DMC Palette, then choose Replace Used Color. PNG and PDF export always use the current edited pattern.

Use **Save Project** to create a `.diamond` file. The ZIP-based project format embeds the source as PNG plus JSON containing crop/conversion settings, drill size, DMC IDs, initial automatic grid, and current edited grid. Opening it restores edits without reconversion. An asterisk in the title indicates unsaved changes.

## Test and build

```powershell
.\.venv\Scripts\python.exe -m pytest
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

The build script creates the environment, installs dependencies, tests, and invokes PyInstaller. The standalone, windowed folder build is `dist\Diamond Art Converter\Diamond Art Converter.exe`; keep the `_internal` folder beside the EXE. The destination PC does not need Python. A folder build is used because Qt's DLLs are more reliable when loaded directly than when unpacked by PyInstaller's one-file bootloader.

## Structure

- `main.py` — entry point
- `app/main_window.py` — PySide6 UI
- `app/image_processor.py` — image loading and conversion core
- `app/exporter.py` — PNG rendering/export
- `app/pdf_exporter.py` — true-scale PDF chart and legend rendering
- `app/physical.py` — physical sizing and page-tiling calculations
- `app/palette_system.py` / `palettes/dmc.json` — replaceable named palette subsystem and DMC reference data
- `app/pattern_model.py` — semantic cell-ID grid, incremental statistics, and delta undo/redo
- `app/pattern_converter.py` — adjusted image to DMC logical-pattern conversion
- `app/pattern_analysis.py` — connected-region analysis foundation
- `app/project_io.py` — self-contained `.diamond` save/load
- `app/widgets/pattern_editor.py` / `editor_panel.py` — efficient custom-rendered editor and controls
- `app/models.py` — settings/palette models
- `app/widgets/` — reusable UI
- `tests/` — generated-image core tests

## Processing design

Adjustments are applied before Lanczos reduction to the exact drill grid. Pillow median-cut quantization follows, with optional Floyd–Steinberg dithering. This preserves detail while guaranteeing dimensions and color limits. Fit uses white letterboxing; Fill uses a centered crop.

The logical drill grid is deterministically quantized into a broader candidate pool. Candidates are scored for drill coverage, CIELAB distinctiveness, spatial coherence, local contrast, and four-connected tiny-region/confetti burden. An iterative set optimizer selects distinct DMC colors, allowing a perceptually reasonable second-best DMC match when two useful candidates share the same nearest code. Every candidate region is then assigned through the selected DMC set. The final logical grid stores DMC codes, never arbitrary RGB values, and never exceeds the requested target.

The 489-entry `DMC Reference Palette` was mechanically extracted from the open-source pyxstitch 1.11.1 floss table (`https://github.com/enckse/pyxstitch`, GPL-3.0). Its license is retained at `palettes/LICENSE-pyxstitch-GPL3.txt`. RGB values are screen-reference approximations, not official color-management data. Thread and resin drill appearance varies by display, lighting, material, dye lot, and manufacturer.

## Current limitations

- Extreme 1000 × 1000 patterns and enlarged exports may be slower or memory-heavy.
- Conversion is debounced but currently runs in the GUI process.
- Exported grid lines replace one edge pixel of enlarged cells.
- Printable PDF export runs synchronously and can briefly make the window appear busy on unusually large patterns.
- DMC RGB matching uses Delta E 1976 rather than newer Delta E 2000.
- Project files do not yet preserve undo history; reopening starts a fresh undo stack.
- Automatic confetti cleanup is not implemented; the internal connected-region analysis reports small regions without changing them.
