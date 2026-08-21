from PIL import Image
from app.palette_system import PaletteColor,ReferencePalette
from app.pattern_analysis import connected_components,region_summary
from app.pattern_model import PatternModel
from app.project_io import load_project,save_project

def palette():return ReferencePalette("Test",[PaletteColor("310","Black",(0,0,0)),PaletteColor("B5200","Snow White",(255,255,255))])

def test_project_round_trip_preserves_pattern_and_dmc_ids(tmp_path):
    pal=palette();model=PatternModel(3,2,["310","310","B5200","B5200","310","B5200"],pal,metadata={"note":"edited"})
    source=Image.new("RGB",(8,6),(20,40,60));path=save_project(tmp_path/"sample",model,source,{"drill_mm":2.5,"crop_box":[0,0,1,1]})
    loaded,loaded_source,settings,_=load_project(path,pal)
    assert loaded.cell_ids==model.cell_ids and loaded.initial_ids==model.initial_ids
    assert set(loaded.cell_ids)=={"310","B5200"} and loaded_source.size==(8,6) and settings["drill_mm"]==2.5

def test_connected_components_find_isolated_cells():
    pal=palette();model=PatternModel(3,3,["310","310","B5200","310","B5200","310","B5200","310","310"],pal)
    components=connected_components(model,"B5200")
    assert sorted(len(cells) for _code,cells in components)==[1,1,1]
    assert region_summary(model)["single_cell_regions"]==3
