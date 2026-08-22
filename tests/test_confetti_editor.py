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


def test_navigation_geometry_is_stable_for_variable_details_filters_and_resize():
    app=QApplication.instance() or QApplication([])
    palette=ReferencePalette("Variable",[
        PaletteColor("A","Base",(90,90,90)),
        PaletteColor("B","Short",(105,105,105)),
        PaletteColor("C","A deliberately very long DMC color name used to verify wrapped selected-region details",(125,125,125)),
        PaletteColor("D","Another unusually long replacement color name that requires multiple wrapped lines",(145,145,145)),
    ])
    cells=["A"]*81
    for index,code in ((10,"B"),(16,"C"),(46,"D")):cells[index]=code
    panel=EditorPanel();panel.set_pattern(PatternModel(9,9,cells,palette));panel.resize(1150,900);panel.show();panel.inspect_confetti.setChecked(True);panel.confetti_filter.setCurrentText("All suspects");app.processEvents()
    assert panel.confetti_list.count()>=3
    navigation_geometry=panel.confetti_navigation.geometry();previous_geometry=panel.confetti_previous.geometry();next_geometry=panel.confetti_next.geometry()
    for row in range(panel.confetti_list.count()):
        panel.confetti_list.setCurrentRow(row);app.processEvents()
        assert panel.confetti_navigation.geometry()==navigation_geometry
        assert panel.confetti_previous.geometry()==previous_geometry
        assert panel.confetti_next.geometry()==next_geometry
    for confidence_filter in ("High only","High + Medium","All suspects"):
        panel.confetti_filter.setCurrentText(confidence_filter);app.processEvents();assert panel.confetti_navigation.geometry()==navigation_geometry
    panel.confetti_details.setText("\n".join(["Long wrapped detail content"]*30));app.processEvents()
    assert panel.confetti_navigation.geometry()==navigation_geometry
    assert panel.confetti_details_scroll.verticalScrollBar().maximum()>0
    for width in (980,1350):
        panel.resize(width,820);app.processEvents();left=panel.confetti_previous.geometry();right=panel.confetti_next.geometry()
        assert left.height()==right.height()==previous_geometry.height()
        assert abs(left.width()-right.width())<=1 and left.y()==right.y()
    panel.close()
