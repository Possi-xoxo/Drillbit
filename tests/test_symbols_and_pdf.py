import io
import json
import math
import re
import zipfile

import numpy as np
from pypdf import PdfReader

from app.palette_system import load_dmc_palette
from app.pattern_model import PatternModel
from app.pdf_exporter import export_pattern_pdf,render_chart_tile
from app.physical import Orientation
from app.project_io import load_project,save_project
from app.symbols import SYMBOL_POOL,assign_symbols,ensure_pattern_symbols,symbol_text_rgb


def pattern_with_colors(count,width=None):
    palette=load_dmc_palette();codes=[color.code for color in palette.colors[:count]];width=width or count
    ids=[codes[index%count] for index in range(width*10)]
    return PatternModel(width,10,ids,palette)


def test_unique_and_deterministic_symbols_for_twenty_colors():
    pattern=pattern_with_colors(20);first=assign_symbols(pattern.usage);second=assign_symbols(reversed(list(pattern.usage)))
    assert first==second and len(first)==20 and len(set(first.values()))==20


def test_transparency_has_no_symbol():
    pattern=pattern_with_colors(3);pattern.set_cell(0,0,None);mapping=ensure_pattern_symbols(pattern)
    assert None not in mapping and set(mapping)==set(pattern.usage)


def test_symbol_capacity_for_64_and_100_colors():
    for count in (64,100):
        mapping=ensure_pattern_symbols(pattern_with_colors(count));assert len(mapping)==count and len(set(mapping.values()))==count
    assert len(SYMBOL_POOL)>=100


def test_project_symbol_mapping_round_trip_and_old_project_compatibility(tmp_path):
    palette=load_dmc_palette();pattern=pattern_with_colors(20);mapping=dict(pattern.metadata["symbol_mapping"])
    path=save_project(tmp_path/"symbols",pattern);loaded,_source,_settings,_editor=load_project(path,palette);assert loaded.metadata["symbol_mapping"]==mapping
    payload={"format":"Diamond Art Converter Project","version":1,"palette":palette.name,"width":2,"height":1,"cell_ids":["310","B5200"],"initial_ids":["310","B5200"],"metadata":{},"settings":{},"editor_state":{},"source_embedded":False}
    old=tmp_path/"old.diamond"
    with zipfile.ZipFile(old,"w") as archive:archive.writestr("project.json",json.dumps(payload))
    restored,*_=load_project(old,palette);assert len(restored.metadata["symbol_mapping"])==2


def test_symbol_contrast_uses_best_black_or_white():
    assert symbol_text_rgb((0,0,0))==(255,255,255) and symbol_text_rgb((10,20,55))==(255,255,255)
    assert symbol_text_rgb((255,255,255))==(0,0,0) and symbol_text_rgb((250,230,120))==(0,0,0)


def test_pdf_chart_and_legend_contain_symbols_and_current_counts(tmp_path):
    pattern=pattern_with_colors(3,width=12);pattern.set_cell(0,0,None);mapping=ensure_pattern_symbols(pattern)
    path,_=export_pattern_pdf(pattern,tmp_path/"symbols.pdf",2.5,Orientation.PORTRAIT)
    reader=PdfReader(path);legend=reader.pages[0].extract_text()
    for color,count in pattern.used_colors():
        assert mapping[color.code] in legend and f"DMC {color.code} - {color.name} - {count:,} drills" in legend
    assert all(len(page.images)==1 for page in reader.pages[1:])
    assert "DMC 310" not in legend or "310" in pattern.usage


def test_transparent_chart_cell_is_white_and_has_no_symbol():
    pattern=pattern_with_colors(1,width=10);pattern.set_cell(0,0,None);mapping=ensure_pattern_symbols(pattern)
    raster,stats=render_chart_tile(pattern.to_image(),(0,0,10,10),2.5,pattern,mapping,dpi=254)
    assert stats["symbols"]==99
    # Cell interiors are sampled away from the grid; the transparent cell is white.
    assert raster.getpixel((5,5))==(255,255,255)
    assert raster.getpixel((30,5))==pattern.palette.by_code[pattern.get(1,0)].rgb


def test_large_legend_spans_pages_and_chart_pitch_remains_physical(tmp_path):
    pattern=pattern_with_colors(100,width=100);path,layout=export_pattern_pdf(pattern,tmp_path/"large.pdf",2.5,Orientation.PORTRAIT)
    reader=PdfReader(path);assert len(reader.pages)>layout.tile_count+1
    text="\n".join(page.extract_text() or "" for page in reader.pages[:-layout.tile_count])
    assert all(f"DMC {color.code}" in text for color,_count in pattern.used_colors())


def test_chart_page_complexity_is_one_image_not_per_cell_operators(tmp_path):
    pattern=pattern_with_colors(16,width=90)
    path,layout=export_pattern_pdf(pattern,tmp_path/"complexity.pdf",2.5,Orientation.PORTRAIT,include_legend=False,raster_dpi=120)
    reader=PdfReader(path);assert len(reader.pages)==layout.tile_count
    for page in reader.pages:
        content=page.get_contents().get_data()
        assert len(page.images)==1
        assert content.count(b" re")<10 and content.count(b" Tj")<10


def test_raster_dimensions_change_with_dpi_but_pdf_scale_does_not(tmp_path):
    pattern=pattern_with_colors(2,width=100)
    low,low_stats=render_chart_tile(pattern.to_image(),(0,0,100,10),2.5,pattern,ensure_pattern_symbols(pattern),dpi=100)
    high,high_stats=render_chart_tile(pattern.to_image(),(0,0,100,10),2.5,pattern,ensure_pattern_symbols(pattern),dpi=200)
    assert abs(high_stats["width"]-2*low_stats["width"])<=1 and abs(high_stats["height"]-2*low_stats["height"])<=1
    for dpi in (100,200):
        path,_=export_pattern_pdf(pattern,tmp_path/f"scale-{dpi}.pdf",2.5,Orientation.LANDSCAPE,include_legend=False,raster_dpi=dpi)
        page=PdfReader(path).pages[0];content=page.get_contents().get_data().decode("latin-1")
        assert "708.661" in content  # 100 cells * 2.5 mm in PDF points.


def test_global_ten_cell_guides_align_across_overlapping_tiles():
    pattern=pattern_with_colors(2,width=30);mapping=ensure_pattern_symbols(pattern)
    left,_=render_chart_tile(pattern.to_image(),(0,0,20,10),2.5,pattern,mapping,dpi=254)
    right,_=render_chart_tile(pattern.to_image(),(10,0,30,10),2.5,pattern,mapping,dpi=254)
    # Both tile edges represent global x=10 and therefore use the stronger guide.
    assert left.getpixel((left.width//2,5))==right.getpixel((0,5))==(89,89,89)
    assert np.array_equal(np.asarray(left)[:,left.width//2:],np.asarray(right)[:,:right.width//2])


def test_representative_225_pattern_exports_nine_single_image_chart_pages(tmp_path):
    palette=load_dmc_palette();codes=[color.code for color in palette.colors[:16]]
    ids=[codes[index%16] if index%3 else None for index in range(225*225)]
    pattern=PatternModel(225,225,ids,palette,metadata={"preserve_transparency":True})
    path,layout=export_pattern_pdf(pattern,tmp_path/"representative.pdf",2.5,Orientation.AUTO,include_legend=False,raster_dpi=72)
    reader=PdfReader(path);assert layout.tile_count==9 and len(reader.pages)==9
    assert all(len(page.images)==1 for page in reader.pages)


def test_legend_calibration_rectangles_remain_vector_and_exact(tmp_path):
    pattern=pattern_with_colors(2,width=10);path,_=export_pattern_pdf(pattern,tmp_path/"calibration.pdf",raster_dpi=72)
    content=PdfReader(path).pages[0].get_contents().get_data().decode("latin-1")
    widths=[float(match.group(1)) for match in re.finditer(r"[-.\d]+ [-.\d]+ ([-.\d]+) [-.\d]+ re",content)]
    assert any(math.isclose(value,25*72/25.4,abs_tol=.001) for value in widths)
    assert any(math.isclose(value,72,abs_tol=.001) for value in widths)
