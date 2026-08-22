import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.palette_system import PaletteColor, ReferencePalette
from app.pattern_model import PatternModel
from app.widgets.editor_panel import EditorPanel


def make_panel():
    app = QApplication.instance() or QApplication([])
    palette = ReferencePalette(
        "Test",
        [
            PaletteColor("A", "Soft Gray", (100, 100, 100)),
            PaletteColor("B", "Near Gray", (108, 108, 108)),
            PaletteColor("C", "White", (255, 255, 255)),
        ],
    )
    cells = ["A"] * 25
    cells[12] = "B"
    panel = EditorPanel()
    panel.set_pattern(PatternModel(5, 5, cells, palette))
    panel.show()
    app.processEvents()
    return app, panel


def test_analysis_populates_overlay_details_and_navigation():
    app, panel = make_panel()
    panel.inspect_confetti.setChecked(True)
    app.processEvents()

    assert panel.confetti_analysis is not None
    assert panel.confetti_list.count() == 1
    assert panel.highlight_confetti.isChecked()
    assert panel.canvas.show_confetti
    assert panel.canvas.confetti_cells[12] >= 0
    assert "DMC B - Near Gray" in panel.confetti_details.text()
    assert "Suggested replacement: DMC A - Soft Gray" in panel.confetti_details.text()

    panel._navigate_confetti(1)
    assert panel.confetti_list.currentRow() == 0
    panel.close()


def test_edit_invalidates_overlay_until_manual_reanalysis():
    app, panel = make_panel()
    panel.inspect_confetti.setChecked(True)
    old_analysis = panel.confetti_analysis

    changes = panel.pattern.set_cell(2, 2, "A")
    panel.undo_stack.push("Pencil Stroke", changes)
    panel._pattern_changed()
    app.processEvents()

    assert old_analysis.stale
    assert not panel.inspect_confetti.isChecked()
    assert not panel.canvas.inspection_mode
    assert not panel.canvas.show_confetti
    assert panel.canvas.confetti_analysis is None

    panel.inspect_confetti.setChecked(True)
    assert panel.confetti_analysis is not old_analysis
    assert panel.confetti_analysis.metrics["high_regions"] == 0
    assert panel.confetti_list.count() == 0
    panel.close()


def test_undo_and_redo_each_invalidate_fresh_results():
    app, panel = make_panel()
    changes = panel.pattern.set_cell(2, 2, "A")
    panel.undo_stack.push("Pencil Stroke", changes)
    panel.inspect_confetti.setChecked(True)
    assert not panel.confetti_analysis.stale

    panel._undo()
    app.processEvents()
    assert panel.confetti_analysis.stale

    panel.inspect_confetti.setChecked(True)
    assert not panel.confetti_analysis.stale
    panel._redo()
    app.processEvents()
    assert panel.confetti_analysis.stale
    panel.close()
