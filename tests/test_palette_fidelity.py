import numpy as np

from PIL import Image

from app.models import ConversionSettings, DitherMode
from app.palette_fidelity import optimize_palette
from app.palette_system import load_dmc_palette
from app.pattern_converter import convert_to_pattern


def distinct_dmc_codes(palette,count):
    labs=np.asarray([palette._labs[color.code] for color in palette.colors]);selected=[next(i for i,color in enumerate(palette.colors) if color.code=="310")]
    nearest=np.full(len(labs),np.inf)
    while len(selected)<count:
        nearest=np.minimum(nearest,np.sqrt(np.sum((labs-labs[selected[-1]])**2,axis=1)));nearest[selected]=-1;selected.append(int(np.argmax(nearest)))
    return [palette.colors[index].code for index in selected]


def colorful_regions(count=64,block=12,palette=None):
    palette=palette or load_dmc_palette();codes=distinct_dmc_codes(palette,count)
    image=Image.new("RGB",(block*count,block))
    pixels=image.load()
    for index in range(count):
        rgb=palette.by_code[codes[index]].rgb
        for y in range(block):
            for x in range(index*block,(index+1)*block):pixels[x,y]=rgb
    return image


def test_colorful_image_uses_palette_budget_and_error_improves_monotonically():
    palette=load_dmc_palette();image=colorful_regions(palette=palette);results=[]
    for maximum in (8,16,32,64):
        pattern=convert_to_pattern(image,ConversionSettings(width=768,height=12,max_colors=maximum),palette)
        results.append((len(pattern.usage),pattern.metadata["mean_delta_e"]))
    assert results[0][0]>=7 and results[1][0]>=14 and results[2][0]>=27 and results[3][0]>=48
    assert all(right[1]<=left[1]+1e-6 for left,right in zip(results,results[1:]))


def test_thirty_two_distinct_regions_do_not_collapse():
    palette=load_dmc_palette();pattern=convert_to_pattern(colorful_regions(32,palette=palette),ConversionSettings(width=384,height=12,max_colors=32),palette)
    assert len(pattern.usage)>=27


def test_related_gradient_gains_meaningful_shades_and_fidelity():
    palette=load_dmc_palette();image=Image.new("RGB",(256,16));pixels=image.load()
    stops=[palette.by_code[code].rgb for code in ("939","550","3804","3608")]
    for x in range(256):
        scaled=x/255*3;section=min(2,int(scaled));amount=scaled-section
        rgb=tuple(round(stops[section][i]*(1-amount)+stops[section+1][i]*amount) for i in range(3))
        for y in range(16):pixels[x,y]=rgb
    patterns=[convert_to_pattern(image,ConversionSettings(width=256,height=16,max_colors=n),palette) for n in (4,8,16)]
    assert [len(pattern.usage) for pattern in patterns[:2]]==[4,8] and len(patterns[2].usage)>=12
    assert patterns[2].metadata["mean_delta_e"]<patterns[1].metadata["mean_delta_e"]<patterns[0].metadata["mean_delta_e"]


def test_dominant_background_does_not_hide_smaller_color_families():
    image=Image.new("RGB",(100,40),(35,8,70));pixels=image.load();accents=[(220,20,150),(245,45,45),(255,130,10),(0,220,235),(20,100,220),(30,200,150)]
    for index,rgb in enumerate(accents):
        x0=70+index*5
        for y in range(40):
            for x in range(x0,x0+5):pixels[x,y]=rgb
    pattern=convert_to_pattern(image,ConversionSettings(width=100,height=40,max_colors=8),load_dmc_palette())
    assert len(pattern.usage)>=7 and pattern.metadata["p90_delta_e"]<25


def test_fragmentation_is_measured_after_selection_not_rejected():
    palette=load_dmc_palette();image=Image.new("RGB",(60,40),palette.by_code["939"].rgb);pixels=image.load()
    for y in range(2,40,5):
        for x in range(2,60,5):
            for dy in (0,1):
                for dx in (0,1):pixels[x+dx,y+dy]=palette.by_code["666"].rgb
    ids,diagnostics=optimize_palette(image,2,palette)
    assert "666" in diagnostics["selected_codes"] and diagnostics["confetti"]["per_color"]["666"]["components"]>20
    assert diagnostics["confetti"]["per_color"]["666"]["single_cells"]==0


def test_transparency_remains_excluded_from_error_and_usage():
    image=colorful_regions(16).convert("RGBA")
    for y in range(image.height):
        for x in range(image.width//2):image.putpixel((x,y),(255,255,255,0))
    pattern=convert_to_pattern(image,ConversionSettings(width=image.width,height=image.height,max_colors=16,preserve_transparency=True),load_dmc_palette())
    assert pattern.empty_cells==image.width*image.height//2 and None not in pattern.usage and pattern.total_drills==image.width*image.height//2


def test_floyd_steinberg_assignment_stays_within_selected_palette():
    palette=load_dmc_palette();pattern=convert_to_pattern(colorful_regions(16,palette=palette),ConversionSettings(width=192,height=12,max_colors=8,dither=DitherMode.FLOYD_STEINBERG),palette)
    assert set(pattern.cell_ids)<=set(pattern.metadata["selected_codes"]) and len(pattern.usage)<=8
