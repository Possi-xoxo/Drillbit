import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.palette_system import PaletteColor, ReferencePalette
from app.pattern_model import PatternModel
from app.widgets.editor_panel import EditorPanel


def make_panel():
    app=QApplication.instance() or QApplication([])
    palette=ReferencePalette("Test",[PaletteColor("A","Black",(0,0,0)),PaletteColor("B","White",(255,255,255))])
    panel=EditorPanel();panel.set_pattern(PatternModel(3,2,["A"]*6,palette));panel.show();app.processEvents();return app,panel


def checked_tools(panel):return [name for name,button in panel.tool_buttons.items() if button.isChecked()]


def test_pencil_is_the_only_default_tool():
    _app,panel=make_panel();assert checked_tools(panel)==["Pencil"] and panel.canvas.tool=="Pencil";panel.close()


def test_tool_buttons_are_exclusive_and_update_canvas_state():
    app,panel=make_panel()
    for name in ("Eyedropper","Flood Fill","Pencil"):
        QTest.mouseClick(panel.tool_buttons[name],Qt.MouseButton.LeftButton);app.processEvents()
        assert checked_tools(panel)==[name] and panel.canvas.tool==name
    panel.close()


def test_switching_tools_preserves_undo_history():
    app,panel=make_panel();pattern=panel.pattern
    changes=pattern.set_cell(0,0,"B");panel.undo_stack.push("Pencil Stroke",changes)
    assert panel.undo_stack.count==1 and panel.undo.isEnabled()
    for name in ("Eyedropper","Flood Fill","Pencil"):
        QTest.mouseClick(panel.tool_buttons[name],Qt.MouseButton.LeftButton);app.processEvents()
        assert panel.undo_stack.count==1 and panel.undo.isEnabled()
    panel.undo.click();assert pattern.get(0,0)=="A";panel.close()
