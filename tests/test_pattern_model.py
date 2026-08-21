from app.palette_system import PaletteColor,ReferencePalette
from app.pattern_model import PatternModel,UndoStack

def palette():return ReferencePalette("Test",[PaletteColor("A","Black",(0,0,0)),PaletteColor("B","White",(255,255,255)),PaletteColor("C","Red",(255,0,0))])
def pattern():return PatternModel(4,3,["A","A","B","B","A","B","B","B","C","C","B","A"],palette())

def test_single_cell_edit_only_changes_target_and_stats():
    model=pattern();before=list(model.cell_ids);changes=model.set_cell(1,0,"C")
    assert len(changes)==1 and model.get(1,0)=="C"
    assert sum(a!=b for a,b in zip(before,model.cell_ids))==1
    assert model.usage=={"A":3,"B":6,"C":3}

def test_pencil_stroke_and_undo_redo():
    model=pattern();stack=UndoStack();changes=model.paint([(0,0),(1,0),(0,1)],"C");stack.push("Pencil",changes)
    assert [model.get(0,0),model.get(1,0),model.get(0,1)]==["C"]*3
    assert stack.undo(model) and model.get(0,0)=="A"
    assert stack.redo(model) and model.get(0,0)=="C"

def test_flood_fill_is_four_connected_and_undoable():
    model=pattern();original=list(model.cell_ids);stack=UndoStack();changes=model.flood_fill(0,0,"C");stack.push("Fill",changes)
    assert {c.index for c in changes}=={0,1,4}
    assert model.get(3,2)=="A"
    stack.undo(model);assert model.cell_ids==original

def test_global_replace_and_undo():
    model=pattern();original=list(model.cell_ids);stack=UndoStack();changes=model.replace_color("B","C");stack.push("Replace",changes)
    assert "B" not in model.cell_ids and len(changes)==6
    stack.undo(model);assert model.cell_ids==original
