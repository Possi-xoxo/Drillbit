from pathlib import Path
from PIL import Image, ImageEnhance, ImageOps, UnidentifiedImageError
from .models import ConversionSettings, DitherMode, FitMode, PaletteEntry

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
MAX_SOURCE_PIXELS = 100_000_000

class ImageLoadError(ValueError):
    pass

def load_image(path: str | Path) -> Image.Image:
    path = Path(path)
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ImageLoadError("Choose a JPG, JPEG, PNG, WEBP, or BMP image.")
    try:
        with Image.open(path) as source:
            if source.width * source.height > MAX_SOURCE_PIXELS:
                raise ImageLoadError("This image is too large (maximum 100 megapixels).")
            source.load()
            rgba = ImageOps.exif_transpose(source).convert("RGBA")
            background = Image.new("RGB", rgba.size, "white")
            background.paste(rgba, mask=rgba.getchannel("A"))
            return background
    except ImageLoadError:
        raise
    except (OSError, UnidentifiedImageError, ValueError) as exc:
        raise ImageLoadError("The image could not be opened. It may be corrupt or unsupported.") from exc

def aspect_height(width: int, source_width: int, source_height: int) -> int:
    if source_width <= 0 or source_height <= 0:
        raise ValueError("Source dimensions must be positive.")
    return max(10, min(1000, round(width * source_height / source_width)))

def aspect_width(height: int, source_width: int, source_height: int) -> int:
    if source_width <= 0 or source_height <= 0:
        raise ValueError("Source dimensions must be positive.")
    return max(10, min(1000, round(height * source_width / source_height)))

def _fit(source: Image.Image, size: tuple[int, int], mode: FitMode) -> Image.Image:
    if mode == FitMode.FILL:
        return ImageOps.fit(source, size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
    contained = ImageOps.contain(source, size, method=Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", size, "white")
    canvas.paste(contained, ((size[0] - contained.width) // 2, (size[1] - contained.height) // 2))
    return canvas

def normalized_crop_box(box, image_size):
    """Convert a normalized crop rectangle to safe integer source coordinates."""
    if box is None:
        return (0, 0, image_size[0], image_size[1])
    left, top, right, bottom = box
    left, right = sorted((max(0.0, min(1.0, left)), max(0.0, min(1.0, right))))
    top, bottom = sorted((max(0.0, min(1.0, top)), max(0.0, min(1.0, bottom))))
    if right - left < 1 / image_size[0] or bottom - top < 1 / image_size[1]:
        raise ValueError("Crop area is too small.")
    x0 = max(0, min(image_size[0] - 1, round(left * image_size[0])))
    y0 = max(0, min(image_size[1] - 1, round(top * image_size[1])))
    x1 = max(x0 + 1, min(image_size[0], round(right * image_size[0])))
    y1 = max(y0 + 1, min(image_size[1], round(bottom * image_size[1])))
    return x0, y0, x1, y1

def _factor(value: int) -> float:
    return max(0.0, 1.0 + value / 100.0)

def palette_statistics(image: Image.Image) -> list[PaletteEntry]:
    colors = image.convert("RGB").getcolors(maxcolors=image.width * image.height)
    return [] if colors is None else [PaletteEntry(rgb=rgb, count=count) for count, rgb in sorted(colors, reverse=True)]

def convert_image(source: Image.Image, settings: ConversionSettings) -> tuple[Image.Image, list[PaletteEntry]]:
    settings.validate()
    image = source.convert("RGB").crop(normalized_crop_box(settings.crop_box, source.size))
    image = ImageEnhance.Brightness(image).enhance(_factor(settings.brightness))
    image = ImageEnhance.Contrast(image).enhance(_factor(settings.contrast))
    image = ImageEnhance.Color(image).enhance(_factor(settings.saturation))
    image = _fit(image, (settings.width, settings.height), settings.fit_mode)
    dither = Image.Dither.NONE if settings.dither == DitherMode.OFF else Image.Dither.FLOYDSTEINBERG
    result = image.quantize(colors=settings.max_colors, method=Image.Quantize.MEDIANCUT, dither=dither).convert("RGB")
    return result, palette_statistics(result)
