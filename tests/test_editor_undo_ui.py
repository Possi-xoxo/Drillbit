import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.palette_system import PaletteColor, ReferencePalette
from app.pattern_model import PatternModel
from app.widgets.editor_panel import EditorPanel


def make_panel():
    app = QApplication.instance() or QApplication([])
    palette = ReferencePalette("Test", [PaletteColor("A", "Black", (0, 0, 0)), PaletteColor("B", "White", (255, 255, 255))])
    pattern = PatternModel(8, 5, ["A"] * 40, palette)
    panel = EditorPanel(); panel.resize(900, 600); panel.show(); panel.set_pattern(pattern); panel.select_code("B")
    app.processEvents()
    return app, panel, pattern


def cell_point(canvas,x,y):return QPoint(round(canvas.offset.x()+(x+.5)*canvas.cell_size),round(canvas.offset.y()+(y+.5)*canvas.cell_size))


def test_pencil_click_enables_undo_on_mouse_release_and_shortcuts_work():
    app, panel, pattern = make_panel(); canvas = panel.canvas
    assert not panel.undo.isEnabled()
    QTest.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=cell_point(canvas,0,0)); app.processEvents()
    assert pattern.get(0, 0) == "B" and panel.undo.isEnabled() and panel.undo_stack.count == 1
    canvas.setFocus(); QTest.keyClick(canvas, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier); app.processEvents()
    assert pattern.get(0, 0) == "A" and panel.redo.isEnabled()
    QTest.keyClick(canvas, Qt.Key.Key_Y, Qt.KeyboardModifier.ControlModifier); app.processEvents()
    assert pattern.get(0, 0) == "B"
    panel.close()


def test_drag_commits_once_and_non_editing_actions_keep_history():
    app, panel, pattern = make_panel(); canvas = panel.canvas
    QTest.mousePress(canvas, Qt.MouseButton.LeftButton, pos=cell_point(canvas,0,0))
    QTest.mouseMove(canvas, cell_point(canvas,4,0)); QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=cell_point(canvas,4,0)); app.processEvents()
    assert panel.undo_stack.count == 1 and panel.undo.isEnabled()
    panel.select_code("A"); panel.highlight.setChecked(True); canvas.cell_size += 1; canvas.update(); app.processEvents()
    assert panel.undo_stack.count == 1 and panel.undo.isEnabled()
    panel.undo.click(); app.processEvents()
    assert all(pattern.get(x, 0) == "A" for x in range(5))
    panel.close()


def test_flood_fill_and_sequential_actions_follow_history_order():
    app, panel, pattern = make_panel(); canvas = panel.canvas
    panel.select_tool("Flood Fill")
    QTest.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=cell_point(canvas,0,0)); app.processEvents()
    assert all(code == "B" for code in pattern.cell_ids) and panel.undo_stack.count == 1
    canvas.setFocus(); QTest.keyClick(canvas, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier); app.processEvents()
    assert all(code == "A" for code in pattern.cell_ids)

    panel.select_tool("Pencil")
    QTest.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=cell_point(canvas,0,0))
    QTest.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=cell_point(canvas,1,0)); app.processEvents()
    assert panel.undo_stack.count == 2 and pattern.get(0, 0) == pattern.get(1, 0) == "B"
    panel.undo.click(); assert pattern.get(0, 0) == "B" and pattern.get(1, 0) == "A"
    panel.undo.click(); assert pattern.get(0, 0) == pattern.get(1, 0) == "A"
    panel.redo.click(); assert pattern.get(0, 0) == "B" and pattern.get(1, 0) == "A"
    panel.redo.click(); assert pattern.get(0, 0) == pattern.get(1, 0) == "B"
    panel.close()
