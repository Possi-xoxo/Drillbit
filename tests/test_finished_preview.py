import os

os.environ.setdefault("QT_QPA_PLATFORM","offscreen")

from PIL import Image
from PySide6.QtWidgets import QApplication
from pypdf import PdfReader

from app.finished_preview import ROUND_DRILL_DIAMETER_RATIO,FinishedPreviewPanel,render_finished_preview
from app.main_window import MainWindow
from app.palette_system import PaletteColor,ReferencePalette
from app.pattern_analysis import analyze_confetti
from app.pattern_model import PatternModel,UndoStack
from app.pdf_exporter import export_pattern_pdf,render_chart_tile
from app.physical import Orientation,finished_size_mm
from app.project_io import load_project,save_project
from app.widgets.editor_panel import EditorPanel


def palette():return ReferencePalette("Test",[PaletteColor("R","Red",(255,0,0)),PaletteColor("G","Green",(0,255,0))])


def pattern():return PatternModel(2,2,["R","G",None,"R"],palette(),{"preserve_transparency":True})


def test_square_renderer_uses_crisp_cells_and_background_for_no_drill():
    image=render_finished_preview(pattern(),"Square","White",cell_pixels=20)
    assert image.size==(40,40);assert image.getpixel((10,10))==(255,0,0);assert image.getpixel((30,10))==(0,255,0);assert image.getpixel((10,30))==(255,255,255)
    assert image.getpixel((0,0))==(255,0,0)


def test_round_renderer_centers_drills_on_orthogonal_grid_with_visible_gaps():
    image=render_finished_preview(pattern(),"Round","White",cell_pixels=20)
    assert ROUND_DRILL_DIAMETER_RATIO==.92
    assert image.getpixel((10,10))==(255,0,0) and image.getpixel((30,10))==(0,255,0) and image.getpixel((30,30))==(255,0,0)
    assert image.getpixel((0,0))==(255,255,255) and image.getpixel((20,0))==(255,255,255)
    assert image.getpixel((10,30))==(255,255,255)


def test_round_background_changes_only_gaps_and_empty_cells():
    white=render_finished_preview(pattern(),"Round","White",cell_pixels=20);black=render_finished_preview(pattern(),"Round","Black",cell_pixels=20)
    assert white.getpixel((0,0))==(255,255,255) and black.getpixel((0,0))==(0,0,0)
    assert white.getpixel((10,30))==(255,255,255) and black.getpixel((10,30))==(0,0,0)
    assert white.getpixel((10,10))==black.getpixel((10,10))==(255,0,0)


def test_shape_and_preview_preferences_do_not_change_logical_state():
    app=QApplication.instance() or QApplication([]);model=pattern();analysis=analyze_confetti(model);stack=UndoStack();before=list(model.cell_ids);usage=model.usage.copy();panel=FinishedPreviewPanel();panel.set_pattern(model,"Square",2.5);panel.set_pattern(model,"Round",2.5,"Black",False);app.processEvents()
    assert model.cell_ids==before and model.usage==usage and not analysis.stale and stack.count==0
    panel.close()


def test_physical_size_is_shape_independent():
    expected=(250.0,250.0)
    assert finished_size_mm(100,100,2.5)==expected
    for shape in ("Square","Round"):
        panel=FinishedPreviewPanel();panel.set_pattern(PatternModel(100,100,["R"]*10000,palette()),shape,2.5);assert "250 x 250 mm" in panel.info.text();panel.close()


def test_old_project_defaults_square_and_new_preferences_round_trip(tmp_path):
    app=QApplication.instance() or QApplication([]);window=MainWindow();window._apply_project_settings({});assert window.drill_shape.currentText()=="Square";window.close()
    settings={"drill_mm":2.8,"drill_shape":"Round","canvas_background":"Black","finished_preview_grid":True};path=save_project(tmp_path/"round",pattern(),None,settings);_model,_source,loaded,_editor=load_project(path,palette());assert loaded==settings


def test_editor_remains_square_cell_based_and_finished_preview_excludes_overlays():
    app=QApplication.instance() or QApplication([]);model=pattern();editor=EditorPanel();editor.set_pattern(model,Image.new("RGB",(20,20),(0,0,255)));editor.show_source_overlay.setChecked(True);editor.canvas.set_selection((0,0,1,1));editor.inspect_confetti.setChecked(True)
    finished=render_finished_preview(model,"Round","White",cell_pixels=20)
    assert editor.canvas.tool=="Pencil" and editor.canvas.selection==(0,0,1,1)
    assert finished.getpixel((10,10))==(255,0,0) and finished.getpixel((0,0))==(255,255,255)
    editor.close()


def test_round_shape_is_reported_and_pdf_chart_remains_a_rasterized_grid(tmp_path):
    model=PatternModel(10,10,["R"]*100,palette());path,_layout=export_pattern_pdf(model,tmp_path/"round.pdf",2.5,Orientation.PORTRAIT,raster_dpi=72,drill_shape="Round")
    reader=PdfReader(path);legend=reader.pages[0].extract_text();assert "Drill Shape: Round" in legend and "Drill Pitch: 2.5 mm" in legend
    chart=reader.pages[-1].get_contents().get_data().decode("latin-1");assert "/FormXob." in chart


def test_pdf_round_drills_use_preview_ratio_and_leave_printable_white_corners():
    model=PatternModel(2,1,["R","G"],palette());logical=model.to_image()
    square,_=render_chart_tile(logical,(0,0,2,1),2.5,model,{},dpi=254,drill_shape="Square")
    round_tile,_=render_chart_tile(logical,(0,0,2,1),2.5,model,{},dpi=254,drill_shape="Round")
    assert square.size==round_tile.size==(50,25)
    assert square.getpixel((3,3))==(255,0,0) and all(channel>=254 for channel in round_tile.getpixel((3,3)))
    assert round_tile.getpixel((12,12))==(255,0,0) and round_tile.getpixel((37,12))==(0,255,0)
    row=[round_tile.getpixel((x,12))[0]>200 and round_tile.getpixel((x,12))[1]<100 for x in range(1,25)]
    assert 22<=sum(row)<=24


def test_pdf_round_transparency_symbols_and_grid_are_preserved():
    model=pattern();mapping={"R":"A","G":"B"};logical=model.to_image()
    tile,stats=render_chart_tile(logical,(0,0,2,2),2.5,model,mapping,dpi=254,drill_shape="Round")
    assert stats["symbols"]==3
    assert tile.getpixel((37,37))!=(255,255,255)
    assert tile.getpixel((12,37))==(255,255,255)
    assert tile.getpixel((25,12))==(89,89,89)


def test_square_and_round_pdf_layout_and_logical_counts_are_invariant(tmp_path):
    model=PatternModel(100,100,["R"]*10000,palette());layouts=[]
    for shape in ("Square","Round"):
        path,layout=export_pattern_pdf(model,tmp_path/f"{shape}.pdf",2.5,Orientation.AUTO,raster_dpi=72,drill_shape=shape)
        layouts.append(layout)
        text="\n".join((page.extract_text() or "") for page in PdfReader(path).pages)
        assert f"Drill Shape: {shape}" in text and "Finished size: 250 x 250 mm" in text
    assert layouts[0]==layouts[1] and layouts[0].tile_count==layouts[1].tile_count
    assert finished_size_mm(model.width,model.height,2.5)==(250.0,250.0)
