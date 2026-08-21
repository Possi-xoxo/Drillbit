import pytest
from PIL import Image

from app.exporter import export_png
from app.models import ConversionSettings
from app.palette_optimizer import optimize_palette
from app.palette_system import load_dmc_palette
from app.pattern_converter import convert_to_pattern
from app.pdf_exporter import export_pattern_pdf


@pytest.fixture(scope="module")
def dmc(): return load_dmc_palette()


def striped_image(palette,codes,stripe_width=10,height=40):
    image=Image.new("RGB",(stripe_width*len(codes),height));pixels=image.load()
    for y in range(height):
        for x in range(image.width):pixels[x,y]=palette.by_code[codes[x//stripe_width]].rgb
    return image


def test_colorful_image_reaches_eight_color_target(dmc):
    source=striped_image(dmc,["310","B5200","666","550","995","703","741","208"])
    _ids,diagnostics=optimize_palette(source,8,dmc)
    assert diagnostics["colors_used"]==8


def test_simple_image_does_not_invent_colors(dmc):
    source=striped_image(dmc,["310","B5200"],stripe_width=40)
    _ids,diagnostics=optimize_palette(source,16,dmc)
    assert diagnostics["colors_used"]==2


def test_resized_two_color_logo_does_not_promote_antialias_bands(dmc):
    source=striped_image(dmc,["310","B5200"],stripe_width=40)
    pattern=convert_to_pattern(
        source,
        ConversionSettings(width=100,height=50,max_colors=16),
        dmc,
    )
    assert len(pattern.usage)==2


@pytest.mark.parametrize("maximum",[2,4,8,16])
def test_never_exceeds_requested_maximum(dmc,maximum):
    source=striped_image(dmc,["310","B5200","666","550","995","703","741","208"])
    ids,diagnostics=optimize_palette(source,maximum,dmc)
    assert len(set(ids))==diagnostics["colors_used"]<=maximum


def coherent_and_confetti_image(dmc):
    image=Image.new("RGB",(50,40),dmc.by_code["939"].rgb);pixels=image.load()
    for y in range(10,30):
        for x in range(5,15):pixels[x,y]=dmc.by_code["550"].rgb
    spots=0
    for y in range(0,40,2):
        for x in range(20+(y%4)//2,50,3):
            if spots<200:pixels[x,y]=dmc.by_code["718"].rgb;spots+=1
    return image


def test_coherent_meaningful_region_beats_equal_coverage_confetti(dmc):
    _ids,diagnostics=optimize_palette(coherent_and_confetti_image(dmc),2,dmc)
    assert "550" in diagnostics["selected_codes"]
    assert "718" not in diagnostics["selected_codes"]
    by_confetti=sorted(diagnostics["candidates"],key=lambda item:item["confetti_ratio"])
    assert by_confetti[-1]["confetti_ratio"]>by_confetti[1]["confetti_ratio"]


def test_small_high_contrast_detail_survives(dmc):
    source=Image.new("RGB",(40,40),dmc.by_code["310"].rgb);pixels=source.load()
    pixels[20,20]=pixels[21,20]=dmc.by_code["B5200"].rgb
    _ids,diagnostics=optimize_palette(source,2,dmc)
    assert set(diagnostics["selected_codes"])=={"310","B5200"}


def test_duplicate_nearest_dmc_uses_reasonable_alternative(dmc):
    first=(0,0,0);second=(18,15,15)
    assert dmc.nearest(first).code==dmc.nearest(second).code=="310"
    source=Image.new("RGB",(40,20));pixels=source.load()
    for y in range(20):
        for x in range(40):pixels[x,y]=first if x<20 else second
    _ids,diagnostics=optimize_palette(source,2,dmc)
    assert diagnostics["colors_used"]==2 and "310" in diagnostics["selected_codes"]


def test_optimizer_is_deterministic(dmc):
    source=coherent_and_confetti_image(dmc)
    first_ids,first=optimize_palette(source,4,dmc);second_ids,second=optimize_palette(source,4,dmc)
    assert first["selected_codes"]==second["selected_codes"] and first_ids==second_ids


def test_result_remains_editor_and_export_compatible(dmc,tmp_path):
    source=striped_image(dmc,["310","B5200","666","550"])
    pattern=convert_to_pattern(source,ConversionSettings(width=40,height=40,max_colors=4),dmc)
    assert set(pattern.cell_ids)<=set(dmc.by_code) and len(pattern.usage)==4
    png=export_png(pattern,tmp_path/"optimized.png",3);pdf,_layout=export_pattern_pdf(pattern,tmp_path/"optimized.pdf",2.5)
    assert png.exists() and pdf.exists()
