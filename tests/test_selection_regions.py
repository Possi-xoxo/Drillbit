import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.palette_system import PaletteColor, ReferencePalette
from app.pattern_analysis import analyze_confetti
from app.pattern_model import PatternModel, UndoStack
from app.widgets.editor_panel import EditorPanel


def palette():
    return ReferencePalette("Test", [
        PaletteColor("A", "Gray", (100, 100, 100)),
        PaletteColor("B", "Near Gray", (108, 108, 108)),
        PaletteColor("C", "White", (255, 255, 255)),
    ])


def model(width=8, height=7, transparent=True):
    cells = ["A" if (x + y) % 3 else "B" for y in range(height) for x in range(width)]
    return PatternModel(width, height, cells, palette(), {"preserve_transparency": transparent})


def test_selection_geometry_normalizes_backwards_and_clamps():
    app = QApplication.instance() or QApplication([]);panel = EditorPanel();panel.set_pattern(model(10, 10));canvas = panel.canvas
    assert canvas.normalized_selection((2, 3), (7, 9)) == (2, 3, 8, 10)
    assert canvas.normalized_selection((7, 9), (2, 3)) == (2, 3, 8, 10)
    canvas.set_selection((-4, -2, 20, 30));assert canvas.selection == (0, 0, 10, 10)
    panel.close()


def test_mouse_drag_selects_logical_cells_in_either_direction():
    app = QApplication.instance() or QApplication([]);panel = EditorPanel();panel.set_pattern(model(10, 10));panel.show();app.processEvents();canvas = panel.canvas;canvas.cell_size = 20;canvas.offset = QPoint(10, 10);panel.select_tool("Select")
    QTest.mousePress(canvas, Qt.MouseButton.LeftButton, pos=QPoint(2*20+15,3*20+15));QTest.mouseMove(canvas,QPoint(7*20+15,9*20+15));QTest.mouseRelease(canvas,Qt.MouseButton.LeftButton,pos=QPoint(7*20+15,9*20+15))
    assert canvas.selection == (2, 3, 8, 10)
    QTest.mousePress(canvas,Qt.MouseButton.LeftButton,pos=QPoint(9*20+15,8*20+15));QTest.mouseMove(canvas,QPoint(5*20+15,4*20+15));QTest.mouseRelease(canvas,Qt.MouseButton.LeftButton,pos=QPoint(5*20+15,4*20+15))
    assert canvas.selection == (5, 4, 10, 9)
    panel.close()


def test_fill_clear_and_replace_are_exact_single_undo_operations():
    pattern=model();stack=UndoStack();bounds=(1,1,4,4);original=list(pattern.cell_ids)
    fill=pattern.fill_region(bounds,"C");assert stack.push("Fill Selection",fill) and stack.count==1
    assert all(pattern.get(x,y)=="C" for y in range(1,4) for x in range(1,4));stack.undo(pattern);assert pattern.cell_ids==original;stack.redo(pattern);assert all(pattern.get(x,y)=="C" for y in range(1,4) for x in range(1,4))
    clear=pattern.fill_region(bounds,None);stack.push("Clear Selection",clear);assert pattern.empty_cells==9;stack.undo(pattern);assert pattern.empty_cells==0
    outside=pattern.get(0,0);changes=pattern.replace_color_in_region(bounds,"C","B");stack.push("Replace Color in Selection",changes)
    assert all(pattern.get(x,y)=="B" for y in range(1,4) for x in range(1,4));assert pattern.get(0,0)==outside


def test_copy_paste_preserves_mixed_colors_transparency_and_destination_undo():
    pattern=model();pattern.set_cell(1,1,None);clip=pattern.copy_region((0,0,3,3));before=list(pattern.cell_ids);stack=UndoStack()
    changes=pattern.paste_region(clip,4,3);stack.push("Paste Selection",changes)
    assert pattern.copy_region((4,3,7,6)).cells==clip.cells
    stack.undo(pattern);assert pattern.cell_ids==before;stack.redo(pattern);assert pattern.copy_region((4,3,7,6)).cells==clip.cells
    with pytest.raises(ValueError):pattern.paste_region(clip,7,6)


def test_move_over_populated_destination_restores_source_and_destination_on_undo():
    pattern=model();pattern.set_cell(1,1,None);before=list(pattern.cell_ids);source=pattern.copy_region((0,0,3,3));stack=UndoStack()
    changes=pattern.move_region((0,0,3,3),4,3);stack.push("Move Selection",changes)
    assert pattern.copy_region((4,3,7,6)).cells==source.cells
    assert all(pattern.get(x,y) is None for y in range(3) for x in range(3))
    stack.undo(pattern);assert pattern.cell_ids==before;stack.redo(pattern);assert pattern.copy_region((4,3,7,6)).cells==source.cells
    with pytest.raises(ValueError):pattern.move_region((4,3,7,6),7,6)


def test_region_statistics_remain_exact():
    pattern=model();initial_total=pattern.total_drills
    pattern.fill_region((0,0,2,2),None);assert pattern.total_drills==initial_total-4 and pattern.empty_cells==4
    pattern.fill_region((0,0,2,2),"C");assert pattern.total_drills==initial_total and pattern.empty_cells==0 and pattern.usage["C"]==4
    clip=pattern.copy_region((0,0,2,2));pattern.paste_region(clip,3,3);assert sum(pattern.usage.values())==pattern.total_drills


def test_selection_state_does_not_dirty_history_or_stale_confetti_but_edit_does():
    app=QApplication.instance() or QApplication([]);panel=EditorPanel();panel.set_pattern(model());panel.confetti_analysis=analyze_confetti(panel.pattern);analysis=panel.confetti_analysis
    panel.canvas.set_selection((1,1,4,4));panel.canvas.clear_selection();assert panel.undo_stack.count==0 and not analysis.stale
    panel.canvas.set_selection((1,1,4,4));panel.canvas.selected_code="C";panel._fill_selection()
    assert panel.undo_stack.count==1 and analysis.stale
    panel.close()


def test_nontransparent_patterns_disable_destructive_clear_and_move():
    app=QApplication.instance() or QApplication([]);panel=EditorPanel();panel.set_pattern(model(transparent=False));panel.canvas.set_selection((0,0,2,2))
    assert not panel.clear_selection_cells.isEnabled() and not panel.canvas.allow_selection_move
    with pytest.raises(ValueError):panel.pattern.move_region((0,0,2,2),2,2)
    panel.close()


def test_move_drag_commits_once_and_preserves_destination_for_undo():
    app=QApplication.instance() or QApplication([]);panel=EditorPanel();panel.set_pattern(model(10,10));panel.show();app.processEvents();canvas=panel.canvas;canvas.cell_size=20;canvas.offset=QPoint(10,10);panel.select_tool("Select");canvas.set_selection((1,1,3,3));before=list(panel.pattern.cell_ids)
    QTest.mousePress(canvas,Qt.MouseButton.LeftButton,pos=QPoint(1*20+15,1*20+15));QTest.mouseMove(canvas,QPoint(5*20+15,4*20+15));QTest.mouseRelease(canvas,Qt.MouseButton.LeftButton,pos=QPoint(5*20+15,4*20+15));app.processEvents()
    assert canvas.selection==(5,4,7,6) and panel.undo_stack.count==1
    panel._undo();assert panel.pattern.cell_ids==before
    panel.close()


def test_canvas_shortcuts_select_all_copy_paste_and_delete():
    app=QApplication.instance() or QApplication([]);panel=EditorPanel();panel.set_pattern(model(6,5));panel.show();canvas=panel.canvas;canvas.setFocus();app.processEvents()
    QTest.keyClick(canvas,Qt.Key.Key_A,Qt.KeyboardModifier.ControlModifier);app.processEvents();assert canvas.selection==(0,0,6,5) and panel.undo_stack.count==0
    QTest.keyClick(canvas,Qt.Key.Key_C,Qt.KeyboardModifier.ControlModifier);app.processEvents();assert panel.pattern_clipboard.width==6 and panel.pattern_clipboard.height==5
    canvas.set_selection((0,0,2,2));QTest.keyClick(canvas,Qt.Key.Key_Delete);app.processEvents();assert panel.pattern.empty_cells==4 and panel.undo_stack.count==1
    panel._undo();assert panel.pattern.empty_cells==0
    panel.close()
