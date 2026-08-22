from app.palette_system import PaletteColor,ReferencePalette
from app.pattern_analysis import analyze_confetti,connected_components,size_category
from app.pattern_model import PatternModel


def palette():return ReferencePalette("Test",[
    PaletteColor("A","Gray",(100,100,100)),PaletteColor("B","Nearby Gray",(105,102,100)),PaletteColor("C","White",(255,255,255)),PaletteColor("D","Black",(0,0,0))])


def model(width,height,ids):return PatternModel(width,height,ids,palette())


def test_single_cell_and_three_connected_cells_and_diagonals():
    single=model(3,3,["A"]*4+["B"]+["A"]*4);assert [len(cells) for code,cells in connected_components(single,"B")]==[1]
    connected=model(3,3,["B","B","A","A","B","A","A","A","A"]);assert [len(cells) for code,cells in connected_components(connected,"B")]==[3]
    diagonal=model(3,3,["B","A","A","A","B","A","A","A","B"]);assert [len(cells) for code,cells in connected_components(diagonal,"B")]==[1,1,1]


def center_island(code="B",size=1):
    ids=["A"]*49
    for index in ((24,) if size==1 else (24,25)):ids[index]=code
    return model(7,7,ids)


def suspect_for(pattern,code):return next(region for region in analyze_confetti(pattern).suspects if region.code==code)


def test_similar_isolated_cell_is_high_with_suggested_neighbor():
    region=suspect_for(center_island(),"B")
    assert region.size==1 and region.confidence=="High" and region.dominant_neighbor=="A" and region.suggested_replacement=="A"
    assert region.dominant_share==1.0 and region.dominant_delta_e<10


def test_high_contrast_detail_scores_lower_than_similar_confetti():
    similar=suspect_for(center_island("B"),"B");contrast=suspect_for(center_island("C"),"C")
    assert contrast.score<similar.score and contrast.confidence!="High"


def test_boundary_cell_between_strong_regions_is_not_high():
    ids=[]
    for y in range(7):
        for x in range(7):ids.append("A" if x<3 else "C")
    ids[3+3*7]="B";region=suspect_for(model(7,7,ids),"B")
    assert region.edge_protection>0 and region.confidence!="High"


def test_two_cell_similar_island_is_medium_or_high():
    region=suspect_for(center_island(size=2),"B");assert region.size==2 and region.confidence in {"Medium","High"}


def test_transparency_is_not_a_neighbor_or_replacement_and_protects_edge():
    ids=[None]*25
    for y in range(3):
        for x in range(3):ids[y*5+x]="A"
    ids[0]="B";region=suspect_for(model(5,5,ids),"B")
    assert None not in region.neighbor_counts and region.suggested_replacement in {None,"A"} and region.transparent_boundary+region.outside_boundary>0
    assert region.confidence!="High"


def test_metrics_categories_per_color_and_determinism():
    pattern=center_island();first=analyze_confetti(pattern);second=analyze_confetti(pattern)
    assert [(r.code,r.cells,r.score,r.confidence,r.suggested_replacement) for r in first.regions]==[(r.code,r.cells,r.score,r.confidence,r.suggested_replacement) for r in second.regions]
    assert first.metrics["single_cell_regions"]==1 and first.metrics["high_cells"]==1 and first.metrics["high_percentage"]>0
    assert first.per_color["B"]["high_cells"]==1 and size_category(1)=="1 cell" and size_category(5)=="4-5 cells" and size_category(11)=="11+ cells"
