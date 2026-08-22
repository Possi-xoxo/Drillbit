import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from app.palette_system import PaletteColor, ReferencePalette
from app.pattern_model import PatternModel
from app.widgets.editor_panel import EditorPanel


def make_panel():
    app = QApplication.instance() or QApplication([])
    palette = ReferencePalette("Test", [
        PaletteColor("A", "Soft Gray", (100, 100, 100)),
        PaletteColor("B", "Near Gray", (108, 108, 108)),
        PaletteColor("C", "White", (255, 255, 255)),
    ])
    cells = ["A"] * 25
    cells[12] = "B"
    panel = EditorPanel();panel.set_pattern(PatternModel(5, 5, cells, palette));panel.resize(1100, 760);panel.show();app.processEvents()
    return app, panel


def item_for(widget, code):
    return next(widget.item(row) for row in range(widget.count()) if widget.item(row).data(Qt.ItemDataRole.UserRole) == code)


def test_sidebar_prioritizes_used_colors_and_keeps_one_active_color():
    _app, panel = make_panel();layout = panel.side_layout
    assert layout.indexOf(panel.used_heading) < layout.indexOf(panel.palette_heading)
    assert layout.stretch(layout.indexOf(panel.used_list)) > layout.stretch(layout.indexOf(panel.palette_list))
    assert layout.indexOf(panel.replacement_group) == layout.indexOf(panel.used_list) + 1
    panel._select_item(item_for(panel.used_list, "B"));assert panel.canvas.selected_code == "B" and "DMC B - Near Gray" in panel.selected.text()
    panel._select_item(item_for(panel.palette_list, "C"));assert panel.canvas.selected_code == "C" and "DMC C - White" in panel.selected.text()
    assert panel.palette_list.currentItem().data(Qt.ItemDataRole.UserRole) == "C"
    panel.close()


def test_inspector_starts_inactive_and_checked_state_activates_mode():
    app, panel = make_panel()
    assert not panel.inspect_confetti.isChecked() and not panel.confetti_content.isVisible()
    assert not panel.canvas.inspection_mode and not panel.canvas.show_confetti
    panel.inspect_confetti.setChecked(True);app.processEvents()
    assert panel.inspect_confetti.isChecked() and panel.confetti_content.isVisible()
    assert panel.canvas.inspection_mode and panel.canvas.show_confetti
    assert panel.confetti_analysis is not None and panel.confetti_list.count() == 1
    panel.close()


def test_off_on_reuses_cache_preserves_tool_and_does_not_touch_history(monkeypatch):
    app, panel = make_panel();module = __import__("app.widgets.editor_panel", fromlist=["analyze_confetti"]);original = module.analyze_confetti;calls = []
    def counted(pattern):calls.append(pattern);return original(pattern)
    monkeypatch.setattr(module, "analyze_confetti", counted)
    tool = panel.canvas.tool;history = (panel.undo_stack.count, panel.undo_stack.position)
    panel.inspect_confetti.setChecked(True);analysis = panel.confetti_analysis
    panel.inspect_confetti.setChecked(False)
    assert not panel.canvas.inspection_mode and not panel.canvas.show_confetti and panel.canvas.tool == tool
    panel.inspect_confetti.setChecked(True);app.processEvents()
    assert panel.confetti_analysis is analysis and len(calls) == 1
    assert (panel.undo_stack.count, panel.undo_stack.position) == history
    panel.close()


def test_escape_exits_inspection_and_stale_result_is_never_restored():
    app, panel = make_panel();panel.inspect_confetti.setChecked(True);old = panel.confetti_analysis
    panel._escape_confetti();assert not panel.inspect_confetti.isChecked() and panel.canvas.tool == "Pencil"
    changes = panel.pattern.set_cell(2, 2, "A");panel.undo_stack.push("Pencil Stroke", changes);panel._pattern_changed();app.processEvents()
    assert old.stale and panel.canvas.confetti_analysis is None
    panel.inspect_confetti.setChecked(True)
    assert panel.confetti_analysis is not old and not panel.confetti_analysis.stale
    panel.close()
