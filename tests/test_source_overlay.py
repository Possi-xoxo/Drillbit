import os

os.environ.setdefault("QT_QPA_PLATFORM","offscreen")

from PIL import Image
from PySide6.QtCore import QPoint,Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.exporter import export_png
from app.image_processor import prepare_source_reference
from app.models import ConversionSettings,FitMode
from app.palette_system import PaletteColor,ReferencePalette
from app.pattern_model import PatternModel
from app.project_io import load_project,save_project
from app.widgets.editor_panel import EditorPanel


def palette():return ReferencePalette("Test",[PaletteColor("R","Red",(255,0,0)),PaletteColor("G","Green",(0,255,0))])


def pattern():return PatternModel(10,10,["R"]*100,palette())


def panel_with_source(source=None):
    app=QApplication.instance() or QApplication([]);panel=EditorPanel();panel.set_pattern(pattern(),source);panel.resize(900,650);panel.show();panel.canvas.cell_size=20;panel.canvas.offset=QPoint(20,20);app.processEvents();return app,panel


def canvas_color(panel,x=5,y=5):
    image=panel.canvas.grab().toImage();return image.pixelColor(panel.canvas.offset.x()+x*panel.canvas.cell_size+panel.canvas.cell_size//2,panel.canvas.offset.y()+y*panel.canvas.cell_size+panel.canvas.cell_size//2)


def cell_point(panel,x=0,y=0):return QPoint(round(panel.canvas.offset.x()+(x+.5)*panel.canvas.cell_size),round(panel.canvas.offset.y()+(y+.5)*panel.canvas.cell_size))


def test_adjusted_crop_reference_preserves_alignment_and_detail():
    source=Image.new("RGB",(400,200));pixels=source.load()
    for y in range(200):
        for x in range(400):pixels[x,y]=(255,0,0) if x<200 else (0,0,255)
    settings=ConversionSettings(width=10,height=10,crop_box=(.5,0,1,1),fit_mode=FitMode.FILL,brightness=0,contrast=0,saturation=0)
    reference=prepare_source_reference(source,settings)
    assert reference.width==reference.height==200
    assert reference.getpixel((20,20))==(0,0,255) and reference.getpixel((180,180))==(0,0,255)


def test_opacity_zero_midpoint_and_full_source_contribution():
    app,panel=panel_with_source(Image.new("RGB",(100,100),(0,0,255)));panel.show_source_overlay.setChecked(True)
    panel.source_opacity.setValue(0);app.processEvents();zero=canvas_color(panel)
    panel.source_opacity.setValue(50);app.processEvents();middle=canvas_color(panel)
    panel.source_opacity.setValue(100);app.processEvents();full=canvas_color(panel)
    assert zero.red()>245 and zero.blue()<10
    assert 115<=middle.red()<=140 and 115<=middle.blue()<=140
    assert full.blue()>245 and full.red()<10
    panel.close()


def test_overlay_controls_do_not_mutate_pattern_history_or_usage():
    app,panel=panel_with_source(Image.new("RGB",(100,100),(0,0,255)));before=list(panel.pattern.cell_ids);usage=panel.pattern.usage.copy();history=(panel.undo_stack.count,panel.undo_stack.position)
    panel.show_source_overlay.setChecked(True);panel.source_opacity.setValue(73);panel.show_source_overlay.setChecked(False);app.processEvents()
    assert panel.pattern.cell_ids==before and panel.pattern.usage==usage
    assert (panel.undo_stack.count,panel.undo_stack.position)==history
    panel.close()


def test_pencil_and_eyedropper_still_use_logical_cells_with_overlay():
    app,panel=panel_with_source(Image.new("RGB",(100,100),(0,0,255)));panel.show_source_overlay.setChecked(True);panel.canvas.selected_code="G"
    point=cell_point(panel);QTest.mouseClick(panel.canvas,Qt.MouseButton.LeftButton,pos=point);app.processEvents();assert panel.pattern.get(0,0)=="G"
    panel.select_tool("Eyedropper");panel.canvas.selected_code="R";QTest.mouseClick(panel.canvas,Qt.MouseButton.LeftButton,pos=cell_point(panel));app.processEvents();assert panel.canvas.selected_code=="G"
    panel.show_source_overlay.setChecked(False);assert panel.pattern.get(0,0)=="G"
    panel.close()


def test_rgba_overlay_respects_transparent_source_areas():
    source=Image.new("RGBA",(100,100),(0,0,255,255))
    for y in range(100):
        for x in range(50):source.putpixel((x,y),(0,0,255,0))
    app,panel=panel_with_source(source);panel.show_source_overlay.setChecked(True);panel.source_opacity.setValue(100);app.processEvents()
    assert canvas_color(panel,2,5).red()>245
    assert canvas_color(panel,7,5).blue()>245
    panel.close()


def test_selection_confetti_and_transform_state_coexist_with_overlay():
    app,panel=panel_with_source(Image.new("RGB",(100,100),(0,0,255)));panel.show_source_overlay.setChecked(True);panel.canvas.set_selection((2,2,5,5));panel.inspect_confetti.setChecked(True);original_ids=list(panel.pattern.cell_ids);original_offset=QPoint(panel.canvas.offset)
    panel.canvas.cell_size=24;panel.canvas.offset+=QPoint(17,11);panel.canvas.update();app.processEvents()
    assert panel.canvas.show_source_overlay and panel.canvas.selection==(2,2,5,5) and panel.canvas.show_confetti
    assert panel.canvas.offset!=original_offset and panel.pattern.cell_ids==original_ids and panel.undo_stack.count==0
    panel.close()


def test_missing_source_disables_overlay_gracefully():
    _app,panel=panel_with_source(None)
    assert not panel.show_source_overlay.isEnabled() and not panel.canvas.source_reference_available and not panel.source_opacity_row.isVisible()
    panel.close()


def test_project_view_preference_round_trip_and_export_remains_pattern_only(tmp_path):
    source=Image.new("RGBA",(20,20),(0,0,255,128));state={"show_source_overlay":True,"source_overlay_opacity":64};path=save_project(tmp_path/"overlay",pattern(),source,{"width":10,"height":10},state)
    loaded,loaded_source,_settings,loaded_state=load_project(path,palette());assert loaded_source.mode=="RGBA" and loaded_state==state
    output=export_png(loaded,tmp_path/"pattern.png",1,False);assert Image.open(output).getpixel((5,5))==(255,0,0)
