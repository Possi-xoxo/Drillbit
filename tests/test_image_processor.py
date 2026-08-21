from PIL import Image
from app.exporter import export_png
from app.image_processor import aspect_height, aspect_width, convert_image, load_image, normalized_crop_box
from app.models import ConversionSettings

def gradient(size=(240, 180)):
    image = Image.new("RGB", size)
    image.putdata([(x % 256, y % 256, (x + y) % 256) for y in range(size[1]) for x in range(size[0])])
    return image

def test_requested_dimensions_are_exact():
    result, _ = convert_image(gradient(), ConversionSettings(width=100, height=150))
    assert result.size == (100, 150)

def test_total_cell_count():
    assert ConversionSettings(width=100, height=150).total_cells == 15_000

def test_palette_never_exceeds_maximum():
    result, palette = convert_image(gradient(), ConversionSettings(width=100, height=150, max_colors=16))
    assert len(result.getcolors(maxcolors=15_000)) <= 16
    assert len(palette) <= 16

def test_aspect_ratio_calculations():
    assert aspect_height(100, 400, 200) == 50
    assert aspect_width(150, 400, 200) == 300

def test_export_png_dimensions(tmp_path):
    logical, _ = convert_image(gradient(), ConversionSettings(width=20, height=30))
    path = export_png(logical, tmp_path / "pattern.png", cell_size=10, show_grid=True)
    with Image.open(path) as exported:
        assert exported.format == "PNG" and exported.size == (200, 300)

def test_supported_images_can_be_loaded(tmp_path):
    for extension, image_format in {".jpg":"JPEG", ".jpeg":"JPEG", ".png":"PNG", ".webp":"WEBP", ".bmp":"BMP"}.items():
        path = tmp_path / f"sample{extension}"; gradient((20, 10)).save(path, format=image_format)
        assert load_image(path).size == (20, 10)

def test_crop_calculations_stay_inside_source_bounds():
    assert normalized_crop_box((-0.2,0.1,1.4,0.9),(100,80))==(0,8,100,72)
    result,_=convert_image(gradient(),ConversionSettings(width=40,height=30,crop_box=(0.2,0.2,0.8,0.8)))
    assert result.size==(40,30)
