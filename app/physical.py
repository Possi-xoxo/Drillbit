from dataclasses import dataclass
from enum import Enum
from math import ceil, floor

MM_PER_INCH = 25.4

class Orientation(str, Enum):
    AUTO = "Auto"
    PORTRAIT = "Portrait"
    LANDSCAPE = "Landscape"

def mm_to_inches(value: float) -> float:
    return value / MM_PER_INCH

def inches_to_mm(value: float) -> float:
    return value * MM_PER_INCH

def finished_size_mm(width: int, height: int, drill_mm: float) -> tuple[float, float]:
    if width < 1 or height < 1 or drill_mm <= 0:
        raise ValueError("Grid dimensions and drill size must be positive.")
    return width * drill_mm, height * drill_mm

def drills_from_physical(width: float, height: float, unit: str, drill_mm: float) -> tuple[int, int]:
    factor = 10.0 if unit == "cm" else MM_PER_INCH
    return max(1, round(width * factor / drill_mm)), max(1, round(height * factor / drill_mm))

@dataclass(frozen=True)
class PageLayout:
    orientation: Orientation
    page_width_in: float
    page_height_in: float
    columns: int
    rows: int
    cells_per_page_x: int
    cells_per_page_y: int
    overlap_cells_x: int
    overlap_cells_y: int

    @property
    def tile_count(self): return self.columns * self.rows

def _axis_pages(cells, capacity, overlap):
    if cells <= capacity: return 1
    step = max(1, capacity - overlap)
    return 1 + ceil((cells - capacity) / step)

def _layout(width, height, drill_mm, orientation, margin_in, overlap_in):
    page_w, page_h = ((8.5, 11.0) if orientation == Orientation.PORTRAIT else (11.0, 8.5))
    usable_w_mm = inches_to_mm(page_w - 2 * margin_in)
    usable_h_mm = inches_to_mm(page_h - 2 * margin_in)
    cap_x, cap_y = floor(usable_w_mm / drill_mm), floor(usable_h_mm / drill_mm)
    if cap_x < 1 or cap_y < 1: raise ValueError("Margins leave no printable chart area.")
    overlap_cells = max(0, round(inches_to_mm(overlap_in) / drill_mm))
    ox, oy = min(overlap_cells, cap_x - 1), min(overlap_cells, cap_y - 1)
    cols, rows = _axis_pages(width, cap_x, ox), _axis_pages(height, cap_y, oy)
    return PageLayout(orientation, page_w, page_h, cols, rows, cap_x, cap_y, ox, oy)

def calculate_page_layout(width, height, drill_mm=2.5, orientation=Orientation.AUTO, margin_in=0.25, overlap_in=0.25):
    orientation = Orientation(orientation)
    if orientation != Orientation.AUTO:
        return _layout(width, height, drill_mm, orientation, margin_in, overlap_in)
    portrait = _layout(width, height, drill_mm, Orientation.PORTRAIT, margin_in, overlap_in)
    landscape = _layout(width, height, drill_mm, Orientation.LANDSCAPE, margin_in, overlap_in)
    return min((portrait, landscape), key=lambda item: (item.tile_count, item.rows, item.columns))

def tile_ranges(width, height, layout):
    step_x = layout.cells_per_page_x - layout.overlap_cells_x
    step_y = layout.cells_per_page_y - layout.overlap_cells_y
    for row in range(layout.rows):
        y0 = row * step_y; y1 = min(height, y0 + layout.cells_per_page_y)
        for col in range(layout.columns):
            x0 = col * step_x; x1 = min(width, x0 + layout.cells_per_page_x)
            yield row, col, (x0, y0, x1, y1)
