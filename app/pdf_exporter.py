from pathlib import Path
from reportlab.lib.colors import Color, black, white
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.units import inch, mm
from reportlab.pdfgen.canvas import Canvas
from .image_processor import palette_statistics
from .physical import Orientation, calculate_page_layout, finished_size_mm, mm_to_inches, tile_ranges

def _page_size(layout):
    return letter if layout.orientation == Orientation.PORTRAIT else landscape(letter)

def export_pattern_pdf(logical, destination, drill_mm=2.5, orientation=Orientation.AUTO,
                       margin_in=0.25, overlap_in=0.25):
    path = Path(destination)
    if path.suffix.lower() != ".pdf": path = path.with_suffix(".pdf")
    pattern=logical if hasattr(logical,"to_image") else None
    if pattern is not None: logical=pattern.to_image()
    layout = calculate_page_layout(logical.width, logical.height, drill_mm, orientation, margin_in, overlap_in)
    page_size = _page_size(layout); canvas = Canvas(str(path), pagesize=page_size, pageCompression=1)
    palette = pattern.used_colors() if pattern is not None else palette_statistics(logical); width_mm, height_mm = finished_size_mm(logical.width, logical.height, drill_mm)
    _draw_legend(canvas, page_size, logical, palette, drill_mm, width_mm, height_mm, layout)
    canvas.showPage()
    total = layout.tile_count
    for number, (row, col, bounds) in enumerate(tile_ranges(logical.width, logical.height, layout), start=1):
        _draw_tile(canvas, page_size, logical, drill_mm, margin_in, bounds, number, total, row, col)
        canvas.showPage()
    canvas.save()
    return path, layout

def _draw_legend(c, page_size, logical, palette, drill_mm, width_mm, height_mm, layout):
    page_w, page_h = page_size
    c.setFont("Helvetica-Bold", 20); c.drawString(0.6*inch, page_h-0.7*inch, "Diamond Art Pattern")
    c.setFont("Helvetica", 10)
    lines = [f"Pattern: {logical.width} x {logical.height} drills ({logical.width*logical.height:,} total)",
             f"Drill size: {drill_mm:g} mm", f"Finished size: {width_mm:g} x {height_mm:g} mm",
             f"Finished size: {mm_to_inches(width_mm):.2f} x {mm_to_inches(height_mm):.2f} in",
             f"Colors used: {len(palette)}", f"Chart pages: {layout.tile_count} ({layout.rows} rows x {layout.columns} columns)",
             f"Paper orientation: {layout.orientation.value}", "Print at 100% / Actual Size. Do not use Fit to Page."]
    y = page_h-1.05*inch
    for line in lines: c.drawString(0.6*inch, y, line); y -= 0.2*inch
    c.setFont("Helvetica-Bold", 11); c.drawString(0.6*inch, y-0.1*inch, "Scale calibration")
    y -= 1.25*inch; c.setLineWidth(0.8); c.rect(0.6*inch, y, 25*mm, 25*mm)
    c.setFont("Helvetica", 8); c.drawString(0.6*inch, y-0.13*inch, "25 mm square")
    c.rect(2.2*inch, y, inch, inch); c.drawString(2.2*inch, y-0.13*inch, "1 inch square")
    y -= 0.5*inch; c.setFont("Helvetica-Bold", 11); c.drawString(0.6*inch, y, "Color legend")
    y -= 0.22*inch; column_x = [0.6*inch, 4.4*inch]; col = 0
    for item in palette:
        entry,count=(item if isinstance(item,tuple) else (item,item.count))
        if y < 0.55*inch: col += 1; y = page_h-4.0*inch
        if col >= len(column_x): break
        x = column_x[col]; c.setFillColor(Color(*(v/255 for v in entry.rgb))); c.rect(x, y-2, 12, 12, fill=1, stroke=1)
        label=f"DMC {entry.code} - {entry.name} - {count:,} drills" if hasattr(entry,"code") else f"{entry.hex} - {count:,} drills"
        c.setFillColor(black); c.setFont("Helvetica", 8); c.drawString(x+18, y, label); y -= 0.19*inch

def _draw_tile(c, page_size, logical, drill_mm, margin_in, bounds, number, total, row, col):
    page_w, page_h = page_size; x0, y0, x1, y1 = bounds; pitch = drill_mm*mm
    origin_x = margin_in*inch; origin_y = page_h-margin_in*inch-(y1-y0)*pitch
    pixels = logical.load(); c.setLineWidth(0.15)
    for gy in range(y0, y1):
        py = origin_y+(y1-gy-1)*pitch
        for gx in range(x0, x1):
            rgb = pixels[gx, gy]; c.setFillColorRGB(*(v/255 for v in rgb)); c.rect(origin_x+(gx-x0)*pitch, py, pitch, pitch, fill=1, stroke=0)
    c.setStrokeColorRGB(0.35, 0.35, 0.35)
    for gx in range(x1-x0+1):
        x = origin_x+gx*pitch; c.line(x, origin_y, x, origin_y+(y1-y0)*pitch)
    for gy in range(y1-y0+1):
        y = origin_y+gy*pitch; c.line(origin_x, y, origin_x+(x1-x0)*pitch, y)
    c.setFillColor(black); c.setFont("Helvetica", 7)
    c.drawString(origin_x, 0.08*inch, f"Page {number} of {total} - Row {row+1}, Column {col+1} - Print at 100% / Actual Size")
    mark = 7
    for x, y in ((origin_x, origin_y), (origin_x+(x1-x0)*pitch, origin_y),
                 (origin_x, origin_y+(y1-y0)*pitch), (origin_x+(x1-x0)*pitch, origin_y+(y1-y0)*pitch)):
        c.setStrokeColor(black); c.line(x-mark, y, x+mark, y); c.line(x, y-mark, x, y+mark)
