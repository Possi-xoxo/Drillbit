import os

os.environ.setdefault("QT_QPA_PLATFORM","offscreen")

from PIL import Image
from PySide6.QtCore import QPoint,QPointF,Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.palette_system import PaletteColor,ReferencePalette
from app.pattern_model import PatternModel,UndoStack
from app.widgets.pattern_editor import FIT_MARGIN_RATIO,MAX_CELL_SIZE,PatternCanvas,calculate_minimum_cell_size


def palette():return ReferencePalette("Test",[PaletteColor("A","Black",(0,0,0)),PaletteColor("B","White",(255,255,255))])


def model(width,height):return PatternModel(width,height,["A"]*(width*height),palette())


def canvas_for(width,height,viewport=(1200,800)):
    app=QApplication.instance() or QApplication([]);canvas=PatternCanvas();canvas.resize(*viewport);canvas.show();app.processEvents();pattern=model(width,height);stack=UndoStack();canvas.set_pattern(pattern,stack);app.processEvents();return app,canvas,pattern,stack


def wheel(canvas,delta,pos=None):
    point=pos or canvas.rect().center();event=QWheelEvent(QPointF(point),QPointF(canvas.mapToGlobal(point)),QPoint(),QPoint(0,delta),Qt.MouseButton.NoButton,Qt.KeyboardModifier.NoModifier,Qt.ScrollPhase.NoScrollPhase,False);QApplication.sendEvent(canvas,event);QApplication.processEvents()


def centered(canvas):
    return QPoint(round((canvas.width()-canvas.pattern.width*canvas.cell_size)/2),round((canvas.height()-canvas.pattern.height*canvas.cell_size)/2))


def test_fit_calculation_uses_padded_viewport_and_limiting_axis():
    assert calculate_minimum_cell_size(1200,800,1000,600)==.96
    assert calculate_minimum_cell_size(1200,800,300,100)==3.2
    assert calculate_minimum_cell_size(1200,800,100,300)==800*FIT_MARGIN_RATIO/300
    assert calculate_minimum_cell_size(1200,800,200,200)==3.2
    assert calculate_minimum_cell_size(1200,800,10,10)==20.0


def test_initial_view_fits_and_centers_near_square_pattern():
    _app,canvas,_pattern,_stack=canvas_for(100,83);expected=calculate_minimum_cell_size(canvas.width(),canvas.height(),100,83)
    assert abs(canvas.cell_size-expected)<1e-9 and canvas.offset==centered(canvas)
    assert canvas.pattern.width*canvas.cell_size<=canvas.width()*FIT_MARGIN_RATIO+1
    assert canvas.pattern.height*canvas.cell_size<=canvas.height()*FIT_MARGIN_RATIO+1
    canvas.close()


def test_repeated_wheel_down_clamps_exactly_and_zoom_in_limit_is_unchanged():
    _app,canvas,pattern,stack=canvas_for(100,83);before=list(pattern.cell_ids);usage=pattern.usage.copy();minimum=canvas.cell_size;initial_offset=QPoint(canvas.offset)
    for _ in range(30):wheel(canvas,-120)
    assert canvas.cell_size==minimum and canvas.offset==initial_offset
    for _ in range(80):wheel(canvas,120)
    assert canvas.cell_size==MAX_CELL_SIZE
    for _ in range(80):wheel(canvas,-120)
    assert canvas.cell_size==minimum and canvas.offset==centered(canvas)
    assert pattern.cell_ids==before and pattern.usage==usage and stack.count==0
    canvas.close()


def test_resize_recalculates_floor_follows_fit_and_preserves_zoomed_view():
    app,canvas,_pattern,_stack=canvas_for(100,83,(800,600));first=canvas.cell_size
    canvas.resize(1000,700);app.processEvents();second=calculate_minimum_cell_size(canvas.width(),canvas.height(),100,83)
    assert second>first and canvas.cell_size==second and canvas.offset==centered(canvas)
    wheel(canvas,120);wheel(canvas,120);zoomed=canvas.cell_size;offset=QPoint(canvas.offset)
    canvas.resize(900,650);app.processEvents();assert canvas.cell_size==zoomed and canvas.offset==offset
    canvas.close()


def test_project_change_recalculates_for_wide_and_tall_patterns():
    app,canvas,_pattern,_stack=canvas_for(300,100);wide=canvas.cell_size;canvas.set_pattern(model(100,300),UndoStack());app.processEvents();tall=canvas.cell_size
    assert wide==calculate_minimum_cell_size(canvas.width(),canvas.height(),300,100)
    assert tall==calculate_minimum_cell_size(canvas.width(),canvas.height(),100,300) and tall!=wide
    canvas.close()


def test_overlay_selection_hit_mapping_and_minimum_pan_remain_aligned():
    app,canvas,pattern,stack=canvas_for(100,83);canvas.set_source_reference(Image.new("RGB",(100,83),(0,0,255)));canvas.show_source_overlay=True;canvas.set_selection((2,3,6,7));before=list(pattern.cell_ids);point=QPoint(round(canvas.offset.x()+3.5*canvas.cell_size),round(canvas.offset.y()+4.5*canvas.cell_size))
    assert canvas.grid_cell(point)==(3,4)
    expected=QPoint(canvas.offset);QTest.mousePress(canvas,Qt.MouseButton.MiddleButton,pos=canvas.rect().center());QTest.mouseMove(canvas,canvas.rect().center()+QPoint(100,60));QTest.mouseRelease(canvas,Qt.MouseButton.MiddleButton,pos=canvas.rect().center()+QPoint(100,60));app.processEvents()
    assert canvas.offset==expected and canvas.selection==(2,3,6,7) and canvas.show_source_overlay
    wheel(canvas,120,pos=point);wheel(canvas,-120,pos=point);assert canvas.cell_size==canvas.calculate_minimum_zoom() and canvas.offset==centered(canvas)
    assert pattern.cell_ids==before and stack.count==0
    canvas.close()
