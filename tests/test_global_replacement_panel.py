import os

os.environ.setdefault("QT_QPA_PLATFORM","offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication

from app.palette_optimizer import delta_e
from app.palette_system import PaletteColor,ReferencePalette
from app.pattern_model import PatternModel
from app.widgets.editor_panel import EditorPanel


def make_panel():
    app=QApplication.instance() or QApplication([])
    palette=ReferencePalette("Test",[
        PaletteColor("A","Warm Gray",(100,100,100)),
        PaletteColor("B","Near Gray",(108,108,108)),
        PaletteColor("C","Cool Gray",(130,132,140)),
        PaletteColor("D","Bright Red",(240,20,20)),
    ])
    panel=EditorPanel();panel.set_pattern(PatternModel(3,2,["A","A","B","A","B",None],palette,{"preserve_transparency":True}));panel.resize(1200,900);panel.show();app.processEvents();return app,panel


def used_item(panel,code):return next(panel.used_list.item(row) for row in range(panel.used_list.count()) if panel.used_list.item(row).data(Qt.ItemDataRole.UserRole)==code)


def visible_codes(widget):return [widget.item(row).data(Qt.ItemDataRole.UserRole) for row in range(widget.count())]


def test_used_color_selection_opens_explicit_global_source_and_ordered_suggestions():
    _app,panel=make_panel();panel._used_color_clicked(used_item(panel,"A"))
    assert panel.replacement_group.isVisible() and panel.replacement_source_code=="A"
    assert "From: DMC A - Warm Gray" in panel.replacement_from.text()
    assert "3 drills (60.0%)" in panel.replacement_scope.text() and "every occurrence" in panel.replacement_scope.text()
    suggestions=visible_codes(panel.replacement_suggestions);assert "A" not in suggestions and set(suggestions)<=set(panel.pattern.palette.by_code)
    distances=[delta_e(panel.pattern.palette._labs["A"],panel.pattern.palette._labs[code]) for code in suggestions]
    assert distances==sorted(distances)
    panel.close()


def test_destination_search_and_owned_filter_are_replacement_specific():
    _app,panel=make_panel();panel.set_owned_codes({"B","D"});panel._used_color_clicked(used_item(panel,"A"));panel.replacement_search.setText("red")
    assert visible_codes(panel.replacement_candidates)==["D"]
    panel.replacement_search.clear();panel.replacement_owned_only.setChecked(True)
    assert set(visible_codes(panel.replacement_candidates))=={"B","D"} and set(visible_codes(panel.replacement_suggestions))=={"B","D"}
    assert "DMC B" in panel.closest_owned.text()
    panel.close()


def test_preview_and_cancel_are_non_destructive_and_keep_analysis_valid():
    app,panel=make_panel();panel.inspect_confetti.setChecked(True);analysis=panel.confetti_analysis;before=list(panel.pattern.cell_ids);usage=panel.pattern.usage.copy();history=panel.undo_stack.count;changed=QSignalSpy(panel.changed)
    panel._used_color_clicked(used_item(panel,"A"));panel._select_replacement_code("C");app.processEvents()
    assert panel.canvas.replacement_preview==("A","C") and list(panel.pattern.cell_ids)==before and panel.pattern.usage==usage
    assert panel.canvas._image.pixelColor(0,0).getRgb()[:3]==(130,132,140)
    panel.replacement_preview.setChecked(False);assert panel.canvas._image.pixelColor(0,0).getRgb()[:3]==(100,100,100)
    panel.replacement_preview.setChecked(True);assert panel.canvas._image.pixelColor(0,0).getRgb()[:3]==(130,132,140)
    assert panel.undo_stack.count==history and changed.count()==0 and not analysis.stale
    panel._cancel_global_replacement();assert panel.canvas.replacement_preview is None and list(panel.pattern.cell_ids)==before and panel.undo_stack.count==history
    panel.close()


def test_apply_is_one_undoable_global_change_updates_usage_and_stales_confetti():
    app,panel=make_panel();panel.inspect_confetti.setChecked(True);analysis=panel.confetti_analysis;before=list(panel.pattern.cell_ids)
    panel._used_color_clicked(used_item(panel,"A"));panel._select_replacement_code("C");panel._apply_global_replacement();app.processEvents()
    assert panel.pattern.cell_ids==["C","C","B","C","B",None]
    assert panel.pattern.usage=={"B":2,"C":3} and panel.undo_stack.count==1 and panel.canvas.selected_code=="C"
    assert "A" not in visible_codes(panel.used_list) and "C" in visible_codes(panel.used_list) and analysis.stale
    panel._undo();assert panel.pattern.cell_ids==before and panel.pattern.usage=={"A":3,"B":2}
    panel._redo();assert panel.pattern.cell_ids==["C","C","B","C","B",None] and panel.pattern.usage=={"B":2,"C":3}
    panel.close()


def test_existing_destination_merges_counts_and_same_color_is_not_a_candidate():
    _app,panel=make_panel();panel._used_color_clicked(used_item(panel,"A"));history=panel.undo_stack.count;panel._select_replacement_code("A")
    assert panel.replacement_destination_code!="A" and panel.undo_stack.count==history
    panel._select_replacement_code("B");panel._apply_global_replacement()
    assert panel.pattern.usage=={"B":5} and panel.undo_stack.count==1
    panel.close()
