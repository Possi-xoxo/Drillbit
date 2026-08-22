import math
from PIL import Image
from pypdf import PdfReader
from app.pdf_exporter import export_pattern_pdf
from app.physical import Orientation
from app.palette_system import PaletteColor,ReferencePalette
from app.pattern_model import PatternModel

def test_pdf_is_true_letter_and_cell_pitch_is_physical(tmp_path):
    logical=Image.new("RGB",(10,10),(180,40,70))
    path,layout=export_pattern_pdf(logical,tmp_path/"pattern.pdf",2.5,Orientation.PORTRAIT)
    reader=PdfReader(path)
    assert len(reader.pages)==2  # legend plus one chart page
    width=float(reader.pages[1].mediabox.width); height=float(reader.pages[1].mediabox.height)
    assert math.isclose(width,612,abs_tol=0.01) and math.isclose(height,792,abs_tol=0.01)
    expected_width=10*2.5*72/25.4
    content=reader.pages[1].get_contents().get_data().decode("latin-1")
    assert len(reader.pages[1].images)==1
    assert f"{expected_width:.5f}"[:7] in content
    assert layout.tile_count==1

def test_pdf_legend_uses_dmc_codes_and_names(tmp_path):
    palette=ReferencePalette("DMC Reference Palette",[PaletteColor("310","Black",(0,0,0)),PaletteColor("B5200","Snow White",(255,255,255))])
    pattern=PatternModel(10,10,["310"]*60+["B5200"]*40,palette)
    path,_=export_pattern_pdf(pattern,tmp_path/"dmc.pdf",2.5,Orientation.PORTRAIT)
    text="\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
    assert "DMC 310 - Black - 60 drills" in text
    assert "DMC B5200 - Snow White - 40 drills" in text
