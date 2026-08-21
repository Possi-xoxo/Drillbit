from PIL import Image
from app.models import ConversionSettings
from app.palette_system import load_dmc_palette
from app.pattern_converter import convert_to_pattern

def test_palette_matching_returns_valid_dmc():
    palette=load_dmc_palette();color=palette.nearest((2,2,2))
    assert color.code in palette.by_code and color.name

def test_generated_cells_are_valid_and_color_limited():
    palette=load_dmc_palette();image=Image.new("RGB",(60,40));image.putdata([((x*7)%256,(y*11)%256,((x+y)*5)%256) for y in range(40) for x in range(60)])
    pattern=convert_to_pattern(image,ConversionSettings(width=30,height=20,max_colors=24),palette)
    assert set(pattern.cell_ids)<=set(palette.by_code)
    assert len(pattern.usage)<=24
