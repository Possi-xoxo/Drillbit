from pathlib import Path
from PIL import Image, ImageDraw

def render_reference(logical: Image.Image, cell_size: int = 10, show_grid: bool = False) -> Image.Image:
    if hasattr(logical,"to_image"): logical=logical.to_image()
    if not 1 <= cell_size <= 100:
        raise ValueError("Cell size must be between 1 and 100 pixels.")
    result = logical.convert("RGB").resize((logical.width * cell_size, logical.height * cell_size), Image.Resampling.NEAREST)
    if show_grid and cell_size > 1:
        draw = ImageDraw.Draw(result)
        for x in range(0, result.width, cell_size):
            draw.line((x, 0, x, result.height - 1), fill=(80, 80, 80))
        for y in range(0, result.height, cell_size):
            draw.line((0, y, result.width - 1, y), fill=(80, 80, 80))
    return result

def export_png(logical: Image.Image, destination: str | Path, cell_size: int = 1, show_grid: bool = False) -> Path:
    path = Path(destination)
    if path.suffix.lower() != ".png":
        path = path.with_suffix(".png")
    render_reference(logical, cell_size, show_grid).save(path, format="PNG", optimize=True)
    return path
