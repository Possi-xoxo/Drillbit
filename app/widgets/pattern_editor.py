from PySide6.QtCore import QLineF, QPoint, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget
from PIL.ImageQt import ImageQt

FIT_MARGIN_RATIO=.80
MIN_RENDER_CELL_SIZE=.10
INITIAL_FIT_CELL_SIZE_CEILING=20.0
MAX_CELL_SIZE=40.0
ZOOM_EPSILON=1e-6


def calculate_minimum_cell_size(viewport_width,viewport_height,pattern_width,pattern_height,fit_margin_ratio=FIT_MARGIN_RATIO):
    """Return the per-cell display size that comfortably fits the full pattern."""
    if viewport_width<=0 or viewport_height<=0 or pattern_width<=0 or pattern_height<=0:return MIN_RENDER_CELL_SIZE
    fit=min(viewport_width*fit_margin_ratio/pattern_width,viewport_height*fit_margin_ratio/pattern_height)
    return max(MIN_RENDER_CELL_SIZE,min(INITIAL_FIT_CELL_SIZE_CEILING,fit))

class PatternCanvas(QWidget):
    patternChanged=Signal()
    selectedColorChanged=Signal(object)
    inspectorChanged=Signal(str)
    toolChanged=Signal(str)
    confettiRegionClicked=Signal(int)
    selectionChanged=Signal(object)
    moveSelectionRequested=Signal(object,object)

    def __init__(self,parent=None):
        super().__init__(parent);self.pattern=None;self.undo_stack=None;self.selected_code=None;self.tool="Pencil"
        self.cell_size=10.0;self._minimum_cell_size=MIN_RENDER_CELL_SIZE;self.offset=QPoint(20,20);self.highlight=False;self.show_initial=False;self._image=QImage();self._source_reference=QImage();self.show_source_overlay=False;self.source_overlay_opacity=.4;self.replacement_preview=None;self._stroke=[];self._painting=False;self._pan=None;self._last_cell=None
        self.confetti_analysis=None;self.confetti_confidences={"High"};self.confetti_cells={};self.selected_confetti_id=None;self.show_confetti=False;self.inspection_mode=False
        self.selection=None;self._selection_anchor=None;self._selection_press=None;self._selection_had_existing=False;self._selection_before_drag=None;self._move_origin=None;self._move_grab=None;self._move_preview=None;self.allow_selection_move=False;self.last_mouse_cell=None
        self.setMouseTracking(True);self.setFocusPolicy(Qt.FocusPolicy.StrongFocus);self.setMinimumSize(400,350)

    def set_pattern(self,pattern,undo_stack):
        self.pattern=pattern;self.undo_stack=undo_stack;self.selected_code=next(iter(pattern.usage),None);self.replacement_preview=None;self._minimum_cell_size=self.calculate_minimum_zoom();self.cell_size=self._minimum_cell_size;self._center_pattern();self.clear_selection();self.refresh()

    def calculate_minimum_zoom(self):
        return calculate_minimum_cell_size(self.width(),self.height(),self.pattern.width,self.pattern.height) if self.pattern else MIN_RENDER_CELL_SIZE

    def _at_minimum_zoom(self):return abs(self.cell_size-self._minimum_cell_size)<=ZOOM_EPSILON
    def _center_pattern(self):
        if self.pattern:self.offset=QPoint(round((self.width()-self.pattern.width*self.cell_size)/2),round((self.height()-self.pattern.height*self.cell_size)/2))
    def fit_pattern(self):
        if not self.pattern:return
        self._minimum_cell_size=self.calculate_minimum_zoom();self.cell_size=self._minimum_cell_size;self._center_pattern();self.update()

    def resizeEvent(self,event):
        was_at_minimum=self._at_minimum_zoom();self._minimum_cell_size=self.calculate_minimum_zoom()
        if self.pattern and (was_at_minimum or self.cell_size<self._minimum_cell_size-ZOOM_EPSILON):self.cell_size=self._minimum_cell_size;self._center_pattern()
        super().resizeEvent(event)

    def refresh(self):
        if not self.pattern:return
        image=self.pattern.to_image(self.show_initial)
        if self.replacement_preview and not self.show_initial:
            source,destination=self.replacement_preview;replacement=self.pattern.palette.by_code[destination].rgb;pixels=[]
            for code,rgb in zip(self.pattern.cell_ids,image.get_flattened_data()):
                pixels.append((*replacement,rgb[3]) if code==source and len(rgb)==4 else replacement if code==source else rgb)
            image.putdata(pixels)
        if self.highlight and self.selected_code:
            pixels=[]
            for code,rgb in zip(self.pattern.initial_ids if self.show_initial else self.pattern.cell_ids,image.get_flattened_data()):
                pixels.append(rgb if code==self.selected_code or code is None else tuple(round(v*.2+205) for v in rgb[:3])+(rgb[3],) if len(rgb)==4 else tuple(round(v*.2+205) for v in rgb))
            image.putdata(pixels)
        self._image=QImage(ImageQt(image)).copy();self.update()

    def set_replacement_preview(self,source=None,destination=None):
        self.replacement_preview=(source,destination) if source and destination and source!=destination else None;self.refresh()

    def set_source_reference(self,image):
        self._source_reference=QImage(ImageQt(image)).copy() if image is not None else QImage();self.show_source_overlay=False;self.update()

    @property
    def source_reference_available(self):return not self._source_reference.isNull()

    def paintEvent(self,_event):
        painter=QPainter(self);painter.fillRect(self.rect(),QColor(45,45,48))
        if not self.pattern:return
        target=QRectF(self.offset.x(),self.offset.y(),self.pattern.width*self.cell_size,self.pattern.height*self.cell_size)
        if self.pattern.supports_transparency:
            tile=QPixmap(16,16);tile.fill(QColor(225,225,225));tile_painter=QPainter(tile);tile_painter.fillRect(8,0,8,8,QColor(180,180,180));tile_painter.fillRect(0,8,8,8,QColor(180,180,180));tile_painter.end();painter.drawTiledPixmap(target,tile)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform,False);painter.drawImage(target,self._image)
        if self.show_source_overlay and self.source_reference_available and self.source_overlay_opacity>0:
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform,True);painter.setOpacity(self.source_overlay_opacity);painter.drawImage(target,self._source_reference);painter.setOpacity(1.0);painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform,False)
        if self.show_confetti and self.confetti_analysis and not self.confetti_analysis.stale:
            colors={"High":QColor(255,0,170,90),"Medium":QColor(255,145,0,85),"Low":QColor(0,200,255,70)}
            for region in self.confetti_analysis.suspects:
                if region.confidence not in self.confetti_confidences:continue
                fill=colors[region.confidence];pen=QPen(QColor(fill.red(),fill.green(),fill.blue(),230),2 if region.region_id==self.selected_confetti_id else 1);painter.setPen(pen);painter.setBrush(fill)
                for index in region.cells:
                    x=index%self.pattern.width;y=index//self.pattern.width;painter.drawRect(QRectF(self.offset.x()+x*self.cell_size,self.offset.y()+y*self.cell_size,self.cell_size,self.cell_size))
        if self.cell_size>=5:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            for x in range(self.pattern.width+1):
                strong=x%10==0;painter.setPen(QPen(QColor(20,20,20,210 if strong else 90),2 if strong else 1));px=self.offset.x()+x*self.cell_size;painter.drawLine(QLineF(px,self.offset.y(),px,self.offset.y()+self.pattern.height*self.cell_size))
            for y in range(self.pattern.height+1):
                strong=y%10==0;painter.setPen(QPen(QColor(20,20,20,210 if strong else 90),2 if strong else 1));py=self.offset.y()+y*self.cell_size;painter.drawLine(QLineF(self.offset.x(),py,self.offset.x()+self.pattern.width*self.cell_size,py))
        if self.selection:
            left,top,right,bottom=self._move_preview or self.selection;rect=QRectF(self.offset.x()+left*self.cell_size,self.offset.y()+top*self.cell_size,(right-left)*self.cell_size,(bottom-top)*self.cell_size)
            if self._move_preview:painter.fillRect(rect,QColor(0,170,255,45))
            pen=QPen(QColor(0,190,255),2);pen.setStyle(Qt.PenStyle.DashLine);painter.setPen(pen);painter.setBrush(Qt.BrushStyle.NoBrush);painter.drawRect(rect.adjusted(1,1,-1,-1))

    def grid_cell(self,pos,clamp=False):
        if not self.pattern:return None
        x=int((pos.x()-self.offset.x())//self.cell_size);y=int((pos.y()-self.offset.y())//self.cell_size)
        if clamp:x=max(0,min(self.pattern.width-1,x));y=max(0,min(self.pattern.height-1,y))
        return (x,y) if 0<=x<self.pattern.width and 0<=y<self.pattern.height else None

    def _cell(self,pos):return self.grid_cell(pos)

    def normalized_selection(self,first,last):
        left=min(first[0],last[0]);top=min(first[1],last[1]);right=max(first[0],last[0])+1;bottom=max(first[1],last[1])+1
        return max(0,left),max(0,top),min(self.pattern.width,right),min(self.pattern.height,bottom)

    def set_selection(self,bounds):
        if bounds:
            left,top,right,bottom=bounds;left=max(0,min(self.pattern.width,left));right=max(left,min(self.pattern.width,right));top=max(0,min(self.pattern.height,top));bottom=max(top,min(self.pattern.height,bottom));bounds=(left,top,right,bottom) if right>left and bottom>top else None
        self.selection=bounds;self._move_preview=None;self.selectionChanged.emit(bounds);self.update()

    def clear_selection(self):self.set_selection(None)

    def select_all(self):
        if self.pattern:self.set_selection((0,0,self.pattern.width,self.pattern.height))

    def selection_contains(self,cell):
        if not self.selection:return False
        left,top,right,bottom=self.selection;return left<=cell[0]<right and top<=cell[1]<bottom

    def view_center_cell(self):return self.grid_cell(self.rect().center(),True) if self.pattern else None

    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.MiddleButton:self._pan=event.position();return
        if event.button()!=Qt.MouseButton.LeftButton or self.show_initial:return
        cell=self._cell(event.position())
        if cell is None:return
        self.setFocus(Qt.FocusReason.MouseFocusReason);self.last_mouse_cell=cell
        if self.tool=="Select":
            self._selection_press=cell;self._selection_had_existing=self.selection is not None;self._selection_before_drag=self.selection
            if self.allow_selection_move and self.selection_contains(cell):
                self._move_origin=self.selection;self._move_grab=(cell[0]-self.selection[0],cell[1]-self.selection[1]);self._move_preview=self.selection
            else:self._selection_anchor=cell
            self.update();return
        index=cell[1]*self.pattern.width+cell[0]
        if self.inspection_mode:
            if index in self.confetti_cells:
                self.selected_confetti_id=self.confetti_cells[index];self.confettiRegionClicked.emit(self.selected_confetti_id);self.update()
            return
        if self.tool=="Eyedropper":
            picked=self.pattern.get(*cell)
            if picked is None:self.tool="Eraser";self.toolChanged.emit("Eraser");self.inspectorChanged.emit(f"Cell: {cell[0]+1}, {cell[1]+1} | Transparent / Empty")
            else:self.selected_code=picked;self.selectedColorChanged.emit(picked)
            self.refresh()
        elif self.tool=="Flood Fill":
            changes=self.pattern.flood_fill(*cell,self.selected_code);self.undo_stack.push("Flood Fill",changes);self.refresh();self.patternChanged.emit()
        else:self._painting=True;self._stroke=[];self._last_cell=None;self._paint_cell(cell)

    def mouseMoveEvent(self,event):
        if self._pan is not None:
            delta=event.position()-self._pan;self.offset+=QPoint(round(delta.x()),round(delta.y()));self._pan=event.position()
            if self._at_minimum_zoom():self._center_pattern()
            self.update();return
        cell=self.grid_cell(event.position(),self.tool=="Select" and self._selection_press is not None)
        if cell:
            self.last_mouse_cell=cell
            if self.tool=="Select" and self._selection_press is not None:
                if self._move_origin:
                    width=self._move_origin[2]-self._move_origin[0];height=self._move_origin[3]-self._move_origin[1];left=max(0,min(self.pattern.width-width,cell[0]-self._move_grab[0]));top=max(0,min(self.pattern.height-height,cell[1]-self._move_grab[1]));self._move_preview=(left,top,left+width,top+height);self.update()
                elif self._selection_anchor:self.set_selection(self.normalized_selection(self._selection_anchor,cell))
                return
            code=self.pattern.get(*cell)
            if code is None:self.inspectorChanged.emit(f"Cell: {cell[0]+1}, {cell[1]+1} | Transparent / Empty")
            else:
                color=self.pattern.palette.by_code[code];self.inspectorChanged.emit(f"Cell: {cell[0]+1}, {cell[1]+1} | DMC {code} - {color.name} | {color.hex} | Used: {self.pattern.usage[code]:,}")
            if self._painting:self._paint_cell(cell)

    def _paint_cell(self,cell):
        cells=[cell]
        if self._last_cell and self._last_cell!=cell:
            x0,y0=self._last_cell;x1,y1=cell;dx=abs(x1-x0);dy=-abs(y1-y0);sx=1 if x0<x1 else -1;sy=1 if y0<y1 else -1;error=dx+dy;cells=[]
            while True:
                cells.append((x0,y0))
                if (x0,y0)==(x1,y1):break
                twice=2*error
                if twice>=dy:error+=dy;x0+=sx
                if twice<=dx:error+=dx;y0+=sy
        changes=self.pattern.paint(cells,None if self.tool=="Eraser" else self.selected_code);self._last_cell=cell
        if changes:self._stroke.extend(changes);self.refresh();self.patternChanged.emit()

    def mouseReleaseEvent(self,event):
        if event.button()==Qt.MouseButton.MiddleButton:self._pan=None
        if event.button()==Qt.MouseButton.LeftButton and self._painting:
            self._painting=False;self.undo_stack.push("Erase Stroke" if self.tool=="Eraser" else "Pencil Stroke",self._stroke);self._stroke=[];self._last_cell=None
        if event.button()==Qt.MouseButton.LeftButton and self.tool=="Select" and self._selection_press is not None:
            cell=self.grid_cell(event.position(),True)
            if self._move_origin:
                destination=self._move_preview or self._move_origin
                if destination[:2]!=self._move_origin[:2]:self.moveSelectionRequested.emit(self._move_origin,destination[:2])
                self._move_origin=None;self._move_grab=None;self._move_preview=None
            elif self._selection_anchor:
                if self._selection_had_existing and cell==self._selection_press and not self.selection_contains(cell):self.clear_selection()
                elif self._selection_had_existing and cell==self._selection_press and self._selection_before_drag and not (self._selection_before_drag[0]<=cell[0]<self._selection_before_drag[2] and self._selection_before_drag[1]<=cell[1]<self._selection_before_drag[3]):self.clear_selection()
                elif not self._selection_had_existing or cell!=self._selection_press:self.set_selection(self.normalized_selection(self._selection_anchor,cell))
            self._selection_anchor=None;self._selection_press=None;self._selection_had_existing=False;self._selection_before_drag=None;self.update()

    def wheelEvent(self,event):
        self._minimum_cell_size=self.calculate_minimum_zoom();old=self.cell_size;self.cell_size=max(self._minimum_cell_size,min(MAX_CELL_SIZE,self.cell_size+(1 if event.angleDelta().y()>0 else -1)))
        if old!=self.cell_size:
            if self._at_minimum_zoom():self._center_pattern()
            else:
                pos=event.position();ratio=self.cell_size/old;self.offset=QPoint(round(pos.x()-(pos.x()-self.offset.x())*ratio),round(pos.y()-(pos.y()-self.offset.y())*ratio))
            self.update()

    def leaveEvent(self,_event):self.inspectorChanged.emit("")

    def set_confetti_analysis(self,analysis,confidences=None):
        self.confetti_analysis=analysis;self.confetti_confidences=set(confidences or {"High"});self.confetti_cells={};self.selected_confetti_id=None
        if analysis and not analysis.stale:
            for region in analysis.suspects:
                if region.confidence in self.confetti_confidences:
                    for index in region.cells:self.confetti_cells[index]=region.region_id
        self.update()

    def set_confetti_filter(self,confidences):
        selected=self.selected_confetti_id;self.confetti_confidences=set(confidences);self.set_confetti_analysis(self.confetti_analysis,self.confetti_confidences);self.selected_confetti_id=selected;self.update()

    def set_inspection_mode(self,active):
        self.inspection_mode=bool(active)
        if not active:self.selected_confetti_id=None
        self.update()

    def select_confetti_region(self,region_id):self.selected_confetti_id=region_id;self.update()

    def center_on_cell(self,index):
        if not self.pattern:return
        self._minimum_cell_size=self.calculate_minimum_zoom();self.cell_size=min(MAX_CELL_SIZE,max(10.0,self._minimum_cell_size,self.cell_size));x=index%self.pattern.width;y=index//self.pattern.width
        self.offset=QPoint(round(self.width()/2-(x+.5)*self.cell_size),round(self.height()/2-(y+.5)*self.cell_size));self.update()
