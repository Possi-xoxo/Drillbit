from PySide6.QtCore import QPoint, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import QWidget
from PIL.ImageQt import ImageQt

class PatternCanvas(QWidget):
    patternChanged=Signal()
    selectedColorChanged=Signal(str)
    inspectorChanged=Signal(str)

    def __init__(self,parent=None):
        super().__init__(parent);self.pattern=None;self.undo_stack=None;self.selected_code=None;self.tool="Pencil"
        self.cell_size=10;self.offset=QPoint(20,20);self.highlight=False;self.show_initial=False;self._image=QImage();self._stroke=[];self._painting=False;self._pan=None;self._last_cell=None
        self.setMouseTracking(True);self.setMinimumSize(400,350)

    def set_pattern(self,pattern,undo_stack):
        self.pattern=pattern;self.undo_stack=undo_stack;self.selected_code=next(iter(pattern.usage),None);self.offset=QPoint(20,20);self.refresh()

    def refresh(self):
        if not self.pattern:return
        image=self.pattern.to_image(self.show_initial)
        if self.highlight and self.selected_code:
            pixels=[]
            for code,rgb in zip(self.pattern.initial_ids if self.show_initial else self.pattern.cell_ids,image.getdata()):
                pixels.append(rgb if code==self.selected_code else tuple(round(v*.2+205) for v in rgb))
            image.putdata(pixels)
        self._image=QImage(ImageQt(image)).copy();self.update()

    def paintEvent(self,_event):
        painter=QPainter(self);painter.fillRect(self.rect(),QColor(45,45,48))
        if not self.pattern:return
        target=QRectF(self.offset.x(),self.offset.y(),self.pattern.width*self.cell_size,self.pattern.height*self.cell_size)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform,False);painter.drawImage(target,self._image)
        if self.cell_size>=5:
            for x in range(self.pattern.width+1):
                strong=x%10==0;painter.setPen(QPen(QColor(20,20,20,210 if strong else 90),2 if strong else 1));px=self.offset.x()+x*self.cell_size;painter.drawLine(px,self.offset.y(),px,self.offset.y()+self.pattern.height*self.cell_size)
            for y in range(self.pattern.height+1):
                strong=y%10==0;painter.setPen(QPen(QColor(20,20,20,210 if strong else 90),2 if strong else 1));py=self.offset.y()+y*self.cell_size;painter.drawLine(self.offset.x(),py,self.offset.x()+self.pattern.width*self.cell_size,py)

    def _cell(self,pos):
        if not self.pattern:return None
        x=int((pos.x()-self.offset.x())//self.cell_size);y=int((pos.y()-self.offset.y())//self.cell_size)
        return (x,y) if 0<=x<self.pattern.width and 0<=y<self.pattern.height else None

    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.MiddleButton:self._pan=event.position();return
        if event.button()!=Qt.MouseButton.LeftButton or self.show_initial:return
        cell=self._cell(event.position())
        if cell is None:return
        if self.tool=="Eyedropper":self.selected_code=self.pattern.get(*cell);self.selectedColorChanged.emit(self.selected_code);self.refresh()
        elif self.tool=="Flood Fill":
            changes=self.pattern.flood_fill(*cell,self.selected_code);self.undo_stack.push("Flood Fill",changes);self.refresh();self.patternChanged.emit()
        else:self._painting=True;self._stroke=[];self._last_cell=None;self._paint_cell(cell)

    def mouseMoveEvent(self,event):
        if self._pan is not None:
            delta=event.position()-self._pan;self.offset+=QPoint(round(delta.x()),round(delta.y()));self._pan=event.position();self.update();return
        cell=self._cell(event.position())
        if cell:
            code=self.pattern.get(*cell);color=self.pattern.palette.by_code[code]
            self.inspectorChanged.emit(f"Cell: {cell[0]+1}, {cell[1]+1} | DMC {code} - {color.name} | {color.hex} | Used: {self.pattern.usage[code]:,}")
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
        changes=self.pattern.paint(cells,self.selected_code);self._last_cell=cell
        if changes:self._stroke.extend(changes);self.refresh();self.patternChanged.emit()

    def mouseReleaseEvent(self,event):
        if event.button()==Qt.MouseButton.MiddleButton:self._pan=None
        if event.button()==Qt.MouseButton.LeftButton and self._painting:
            self._painting=False;self.undo_stack.push("Pencil Stroke",self._stroke);self._stroke=[];self._last_cell=None

    def wheelEvent(self,event):
        old=self.cell_size;self.cell_size=max(2,min(40,self.cell_size+(1 if event.angleDelta().y()>0 else -1)))
        if old!=self.cell_size:
            pos=event.position();ratio=self.cell_size/old;self.offset=QPoint(round(pos.x()-(pos.x()-self.offset.x())*ratio),round(pos.y()-(pos.y()-self.offset.y())*ratio));self.update()

    def leaveEvent(self,_event):self.inspectorChanged.emit("")
