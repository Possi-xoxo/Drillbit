from io import BytesIO
import os
from pathlib import Path
from time import perf_counter

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.colors import Color, black, white
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.units import inch, mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas
import logging
from .image_processor import palette_statistics
from .physical import Orientation, calculate_page_layout, finished_size_mm, mm_to_inches, tile_ranges
from .symbols import ensure_pattern_symbols, symbol_text_rgb

LOG=logging.getLogger(__name__)
CHART_RASTER_DPI=600
_FONT_CACHE={}

def _page_size(layout):
    return letter if layout.orientation == Orientation.PORTRAIT else landscape(letter)

def export_pattern_pdf(logical, destination, drill_mm=2.5, orientation=Orientation.AUTO,
                       margin_in=0.25, overlap_in=0.25,include_symbols=True,include_legend=True,
                       raster_dpi=CHART_RASTER_DPI):
    export_started=perf_counter()
    path = Path(destination)
    if path.suffix.lower() != ".pdf": path = path.with_suffix(".pdf")
    pattern=logical if hasattr(logical,"to_image") else None
    if pattern is not None: logical=pattern.to_image()
    layout = calculate_page_layout(logical.width, logical.height, drill_mm, orientation, margin_in, overlap_in)
    page_size = _page_size(layout); canvas = Canvas(str(path), pagesize=page_size, pageCompression=1);canvas.setTitle(path.stem);canvas.setCreator("Drillbit");canvas.setSubject("Diamond art pattern")
    palette = pattern.used_colors() if pattern is not None else palette_statistics(logical); width_mm, height_mm = finished_size_mm(logical.width, logical.height, drill_mm)
    symbols=ensure_pattern_symbols(pattern) if pattern is not None else {};LOG.info("Assigned %s printable symbols",len(symbols))
    drills=pattern.total_drills if pattern is not None else sum(1 for pixel in logical.get_flattened_data() if len(pixel)<4 or pixel[3]>0)
    LOG.info("PDF export started: pattern=%sx%s drills=%s colors=%s chart_pages=%s symbols=%s raster_dpi=%s",
             logical.width,logical.height,drills,len(palette),layout.tile_count,include_symbols,raster_dpi)
    if include_legend:
        legend_started=perf_counter();legend_pages=_draw_legend_pages(canvas,page_size,logical,palette,drill_mm,width_mm,height_mm,layout,symbols);LOG.info("Legend pages: %s generated in %.2f s",legend_pages,perf_counter()-legend_started)
    total = layout.tile_count
    LOG.info("Rendering %s chart pages symbols=%s",total,include_symbols)
    for number, (row, col, bounds) in enumerate(tile_ranges(logical.width, logical.height, layout), start=1):
        _draw_tile(canvas, page_size, logical, drill_mm, margin_in, bounds, number, total, row, col, pattern,symbols if include_symbols else {},raster_dpi)
        canvas.showPage()
    save_started=perf_counter();canvas.save();LOG.info("Final PDF save completed in %.2f s",perf_counter()-save_started)
    LOG.info("PDF export completed in %.2f s: %s",perf_counter()-export_started,path)
    return path, layout

def _draw_legend_pages(c,page_size,logical,palette,drill_mm,width_mm,height_mm,layout,symbols):
    ordered=sorted(palette,key=lambda item:list(symbols).index(item[0].code)) if symbols else list(palette);page=0;offset=0
    while offset<len(ordered) or page==0:
        page+=1;page_w,page_h=page_size;c.setFillColor(black);c.setFont("Helvetica-Bold",18);c.drawString(.55*inch,page_h-.55*inch,f"Diamond Art Pattern - Legend {page}")
        if page==1:
            drills=sum(1 for pixel in logical.get_flattened_data() if len(pixel)<4 or pixel[3]>0);empty=logical.width*logical.height-drills;c.setFont("Helvetica",9)
            lines=[f"Pattern grid: {logical.width} x {logical.height} cells",f"Total drills: {drills:,}    Empty cells: {empty:,}    Colors: {len(palette)}",
                   f"Drill size: {drill_mm:g} mm    Finished size: {width_mm:g} x {height_mm:g} mm ({mm_to_inches(width_mm):.2f} x {mm_to_inches(height_mm):.2f} in)",
                   f"Chart pages: {layout.tile_count}    Orientation: {layout.orientation.value}","Print at 100% / Actual Size. Do not use Fit to Page."]
            y=page_h-.85*inch
            for line in lines:c.drawString(.55*inch,y,line);y-=.17*inch
            c.setFont("Helvetica-Bold",9);c.drawString(.55*inch,y-.03*inch,"Scale calibration")
            y-=1.08*inch;c.setLineWidth(.8);c.rect(.55*inch,y,25*mm,25*mm);c.setFont("Helvetica",7);c.drawString(.55*inch,y-.12*inch,"25 mm square");c.rect(2.05*inch,y,inch,inch);c.drawString(2.05*inch,y-.12*inch,"1 inch square")
            top=y-.38*inch
        else:top=page_h-.95*inch
        bottom=.45*inch;row_height=.19*inch;rows=max(1,int((top-bottom)/row_height));capacity=rows*2;items=ordered[offset:offset+capacity]
        for column in range(2):
            x=.55*inch+column*(page_w/2);c.setFont("Helvetica-Bold",8);c.drawString(x,top,"Symbol   Color   DMC / Name / Drills")
            for row,item in enumerate(items[column*rows:(column+1)*rows],start=1):
                entry,count=(item if isinstance(item,tuple) else (item,item.count));symbol=symbols.get(getattr(entry,"code",None),"");y=top-row*row_height;c.setFillColor(black);c.setFont("Helvetica-Bold",8);c.drawCentredString(x+14,y,symbol)
                c.setFillColor(Color(*(value/255 for value in entry.rgb)));c.rect(x+29,y-2,11,11,fill=1,stroke=1);c.setFillColor(black);c.setFont("Helvetica",7.5)
                label=f"DMC {entry.code} - {entry.name} - {count:,} drills" if hasattr(entry,"code") else f"{entry.hex} - {count:,} drills";c.drawString(x+46,y,label)
        offset+=len(items);c.setFillColor(black);c.setFont("Helvetica",7);c.drawRightString(page_w-.45*inch,.2*inch,f"Legend page {page}");c.showPage()
        if not items:break
    return page

def _draw_legend(c, page_size, logical, palette, drill_mm, width_mm, height_mm, layout):
    page_w, page_h = page_size
    c.setFont("Helvetica-Bold", 20); c.drawString(0.6*inch, page_h-0.7*inch, "Diamond Art Pattern")
    c.setFont("Helvetica", 10)
    drills=sum(1 for pixel in logical.get_flattened_data() if len(pixel)<4 or pixel[3]>0)
    empty=logical.width*logical.height-drills
    lines = [f"Pattern grid: {logical.width} x {logical.height} cells",f"Total drills: {drills:,}",f"Empty cells: {empty:,}",
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

def _symbol_font(pixel_size):
    pixel_size=max(6,int(pixel_size));cached=_FONT_CACHE.get(pixel_size)
    if cached is not None:return cached
    windows=Path(os.environ.get("WINDIR",r"C:\Windows"));candidates=(windows/"Fonts"/"arialbd.ttf",windows/"Fonts"/"calibrib.ttf")
    for candidate in candidates:
        try:
            font=ImageFont.truetype(str(candidate),pixel_size);_FONT_CACHE[pixel_size]=font;return font
        except OSError:pass
    try:font=ImageFont.truetype("DejaVuSans-Bold.ttf",pixel_size)
    except OSError:font=ImageFont.load_default()
    _FONT_CACHE[pixel_size]=font;return font


def _symbol_stamp(symbol,text_rgb,font):
    probe=ImageDraw.Draw(Image.new("L",(1,1)));bbox=probe.textbbox((0,0),symbol,font=font,stroke_width=0)
    width=max(1,bbox[2]-bbox[0]);height=max(1,bbox[3]-bbox[1]);stamp=Image.new("RGBA",(width,height),(0,0,0,0));draw=ImageDraw.Draw(stamp)
    draw.text((-bbox[0],-bbox[1]),symbol,font=font,fill=(*text_rgb,255));return stamp


def render_chart_tile(logical,bounds,drill_mm,pattern=None,symbols=None,dpi=CHART_RASTER_DPI):
    """Render one logical tile to pixels; PDF placement remains authoritative for scale."""
    x0,y0,x1,y1=bounds;cells_x=x1-x0;cells_y=y1-y0
    pixel_w=max(1,round(cells_x*drill_mm/25.4*dpi));pixel_h=max(1,round(cells_y*drill_mm/25.4*dpi))
    source=np.asarray(logical)
    tile=source[y0:y1,x0:x1]
    if tile.ndim==2:tile=np.repeat(tile[...,None],3,axis=2)
    rgb=np.asarray(tile[...,:3],dtype=np.uint8).copy()
    if tile.shape[2]>=4:rgb[np.asarray(tile[...,3])==0]=(255,255,255)
    raster=Image.fromarray(rgb,"RGB").resize((pixel_w,pixel_h),Image.Resampling.NEAREST)
    x_edges=[round(index*pixel_w/cells_x) for index in range(cells_x+1)];y_edges=[round(index*pixel_h/cells_y) for index in range(cells_y+1)]
    symbols=symbols or {};symbol_started=perf_counter();symbol_count=0
    if pattern is not None and symbols:
        draw_cache={};font_cache={}
        for local_y,gy in enumerate(range(y0,y1)):
            for local_x,gx in enumerate(range(x0,x1)):
                code=pattern.get(gx,gy)
                if code is None:continue
                symbol=symbols.get(code)
                if not symbol:continue
                cell_w=x_edges[local_x+1]-x_edges[local_x];cell_h=y_edges[local_y+1]-y_edges[local_y]
                font_px=max(6,round(min(cell_w,cell_h)*(.62 if len(symbol)==1 else .43)))
                font=font_cache.setdefault(font_px,_symbol_font(font_px));text_rgb=symbol_text_rgb(tuple(int(v) for v in rgb[local_y,local_x]))
                key=(symbol,text_rgb,font_px);stamp=draw_cache.get(key)
                if stamp is None:stamp=draw_cache[key]=_symbol_stamp(symbol,text_rgb,font)
                left=x_edges[local_x]+(cell_w-stamp.width)//2;top=y_edges[local_y]+(cell_h-stamp.height)//2
                raster.paste(stamp,(left,top),stamp);symbol_count+=1
    symbol_seconds=perf_counter()-symbol_started
    draw=ImageDraw.Draw(raster);thin=max(1,round(dpi*.15/72));strong=max(thin+1,round(dpi*.35/72))
    for local_x,x in enumerate(x_edges):
        global_x=x0+local_x;draw.line((x,0,x,pixel_h),fill=(89,89,89),width=strong if global_x%10==0 else thin)
    for local_y,y in enumerate(y_edges):
        global_y=y0+local_y;draw.line((0,y,pixel_w,y),fill=(89,89,89),width=strong if global_y%10==0 else thin)
    return raster,{"width":pixel_w,"height":pixel_h,"bytes":pixel_w*pixel_h*3,"symbols":symbol_count,"symbol_seconds":symbol_seconds}


def _draw_tile(c, page_size, logical, drill_mm, margin_in, bounds, number, total, row, col, pattern=None,symbols=None,raster_dpi=CHART_RASTER_DPI):
    page_w, page_h = page_size; x0, y0, x1, y1 = bounds; pitch = drill_mm*mm
    origin_x = margin_in*inch; origin_y = page_h-margin_in*inch-(y1-y0)*pitch
    raster_started=perf_counter();raster,stats=render_chart_tile(logical,bounds,drill_mm,pattern,symbols,raster_dpi)
    LOG.info("Rasterized tile %s/%s in %.2f s (%sx%s px, %.1f MiB, %s symbols in %.2f s)",number,total,perf_counter()-raster_started,stats["width"],stats["height"],stats["bytes"]/(1024*1024),stats["symbols"],stats["symbol_seconds"])
    encode_started=perf_counter();encoded=BytesIO();raster.save(encoded,format="PNG",optimize=False);encoded.seek(0);encoded_size=encoded.getbuffer().nbytes
    LOG.info("Encoded tile %s/%s losslessly in %.2f s (%.1f MiB PNG)",number,total,perf_counter()-encode_started,encoded_size/(1024*1024))
    embed_started=perf_counter();chart_w=(x1-x0)*pitch;chart_h=(y1-y0)*pitch
    c.drawImage(ImageReader(encoded),origin_x,origin_y,width=chart_w,height=chart_h,preserveAspectRatio=False,mask=None)
    LOG.info("Embedded tile %s/%s in %.2f s at %.3f x %.3f mm",number,total,perf_counter()-embed_started,(x1-x0)*drill_mm,(y1-y0)*drill_mm)
    raster.close();encoded.close()
    c.setFillColor(black); c.setFont("Helvetica", 7)
    c.drawString(origin_x, 0.08*inch, f"Page {number} of {total} - Tile row {row+1}, column {col+1} - Pattern {logical.width} x {logical.height} - {drill_mm:g} mm - Print at 100% / Actual Size")
    mark = 7
    for x, y in ((origin_x, origin_y), (origin_x+(x1-x0)*pitch, origin_y),
                 (origin_x, origin_y+(y1-y0)*pitch), (origin_x+(x1-x0)*pitch, origin_y+(y1-y0)*pitch)):
        c.setStrokeColor(black); c.line(x-mark, y, x+mark, y); c.line(x, y-mark, x, y+mark)
