import io
import zipfile

from PIL import Image

from app.exporter import export_png
from app.models import ConversionSettings
from app.palette_system import load_dmc_palette
from app.pattern_converter import convert_to_pattern
from app.pattern_model import PatternModel, UndoStack
from app.project_io import load_project, save_project
from app.widgets.editor_panel import EditorPanel
from PySide6.QtWidgets import QApplication


def rgba_fixture():
    image=Image.new("RGBA",(10,10),(255,0,0,255))
    for y in range(5):
        for x in range(5):image.putpixel((x,y),(12,34,56,0))
    return image


def settings(preserve):return ConversionSettings(width=10,height=10,max_colors=8,preserve_transparency=preserve)


def test_alpha_preserved_and_drill_count():
    pattern=convert_to_pattern(rgba_fixture(),settings(True),load_dmc_palette())
    assert pattern.empty_cells==25 and pattern.total_drills==75 and len(pattern.cell_ids)==100


def test_transparency_disabled_flattens_hidden_rgb_to_white():
    palette=load_dmc_palette();pattern=convert_to_pattern(rgba_fixture(),settings(False),palette)
    assert pattern.empty_cells==0 and pattern.total_drills==100
    assert pattern.get(0,0)==palette.nearest((255,255,255)).code


def test_transparent_cells_are_excluded_from_palette_and_maximum():
    pattern=convert_to_pattern(rgba_fixture(),settings(True),load_dmc_palette())
    assert len(pattern.usage)==1 and None not in pattern.usage and len(pattern.usage)<=8


def test_paint_transparent_cell_and_undo_redo():
    palette=load_dmc_palette();pattern=convert_to_pattern(rgba_fixture(),settings(True),palette);stack=UndoStack()
    changes=pattern.set_cell(0,0,"310");stack.push("Pencil Stroke",changes)
    assert pattern.total_drills==76 and pattern.get(0,0)=="310"
    stack.undo(pattern);assert pattern.total_drills==75 and pattern.get(0,0) is None
    stack.redo(pattern);assert pattern.total_drills==76 and pattern.get(0,0)=="310"


def test_eraser_and_stroke_are_one_undo_action():
    palette=load_dmc_palette();pattern=PatternModel(10,10,["310"]*100,palette,{"preserve_transparency":True});stack=UndoStack()
    changes=pattern.paint([(0,0),(1,0),(2,0)],None);stack.push("Erase Stroke",changes)
    assert pattern.total_drills==97 and stack.count==1
    stack.undo(pattern);assert pattern.total_drills==100 and all(pattern.get(x,0)=="310" for x in range(3))


def test_project_round_trip_preserves_transparency(tmp_path):
    palette=load_dmc_palette();source=rgba_fixture();pattern=convert_to_pattern(source,settings(True),palette)
    path=save_project(tmp_path/"transparent",pattern,source,{"preserve_transparency":True,"alpha_threshold":128})
    loaded,loaded_source,loaded_settings,_=load_project(path,palette)
    assert loaded.cell_ids==pattern.cell_ids and loaded_source.mode=="RGBA"
    assert loaded_settings["preserve_transparency"] is True and loaded_settings["alpha_threshold"]==128


def test_png_export_has_real_alpha(tmp_path):
    pattern=convert_to_pattern(rgba_fixture(),settings(True),load_dmc_palette());path=export_png(pattern,tmp_path/"alpha.png",3)
    exported=Image.open(path);assert exported.mode=="RGBA" and exported.getpixel((0,0))[3]==0 and exported.getpixel((29,29))[3]==255


def test_rgb_source_is_equivalent_with_preserve_on_or_off():
    palette=load_dmc_palette();source=Image.new("RGB",(10,10),(20,80,160))
    assert convert_to_pattern(source,settings(True),palette).cell_ids==convert_to_pattern(source,settings(False),palette).cell_ids


def test_fully_transparent_source_is_valid_and_exports(tmp_path):
    source=Image.new("RGBA",(10,10),(99,88,77,0));pattern=convert_to_pattern(source,settings(True),load_dmc_palette())
    assert pattern.total_drills==0 and len(pattern.usage)==0 and pattern.metadata["colors_used"]==0
    result=Image.open(export_png(pattern,tmp_path/"empty.png"));assert result.mode=="RGBA" and result.getextrema()[3]==(0,0)


def test_eraser_tool_is_enabled_only_for_transparent_patterns():
    app=QApplication.instance() or QApplication([]);palette=load_dmc_palette();panel=EditorPanel()
    panel.set_pattern(PatternModel(10,10,["310"]*100,palette));assert not panel.tool_buttons["Eraser"].isEnabled()
    panel.set_pattern(PatternModel(10,10,[None]+["310"]*99,palette,{"preserve_transparency":True}));assert panel.tool_buttons["Eraser"].isEnabled()
    panel.select_tool("Eraser");assert panel.canvas.tool=="Eraser" and panel.tool_buttons["Eraser"].isChecked();panel.close()
