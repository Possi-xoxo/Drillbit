"""Cached finished-art raster rendering for square and round drill visualization."""
from time import perf_counter
import logging

import numpy as np
from PIL import Image,ImageDraw
from PySide6.QtCore import QPoint,QRectF,Qt,Signal
from PySide6.QtGui import QImage,QPainter
from PySide6.QtWidgets import QCheckBox,QComboBox,QHBoxLayout,QLabel,QPushButton,QVBoxLayout,QWidget
from PIL.ImageQt import ImageQt

from .physical import finished_size_mm,mm_to_inches

LOG=logging.getLogger(__name__)
ROUND_DRILL_DIAMETER_RATIO=.92
ROUND_SYMBOL_SCALE=.88
PREVIEW_MAX_DIMENSION=4096

def _circle_coverage(cell_pixels,ratio=ROUND_DRILL_DIAMETER_RATIO):
    scale=4;size=cell_pixels*scale;mask=Image.new("L",(size,size),0);draw=ImageDraw.Draw(mask);diameter=size*ratio;margin=(size-diameter)/2
    draw.ellipse((margin,margin,margin+diameter,margin+diameter),fill=255)
    return np.asarray(mask.resize((cell_pixels,cell_pixels),Image.Resampling.LANCZOS),dtype=np.uint8)

def render_finished_preview(pattern,drill_shape="Square",background="White",show_grid=False,cell_pixels=None,max_dimension=PREVIEW_MAX_DIMENSION):
    """Rasterize current logical cells as finished square/round drills without editor layers."""
    if drill_shape not in ("Square","Round"):raise ValueError("Drill shape must be Square or Round.")
    if background not in ("White","Black"):raise ValueError("Canvas background must be White or Black.")
    if cell_pixels is None:cell_pixels=max(2,min(16,max_dimension//max(pattern.width,pattern.height)))
    cell_pixels=max(1,int(cell_pixels));background_rgb=np.array((255,255,255) if background=="White" else (0,0,0),dtype=np.uint8)
    opaque=np.fromiter((code is not None for code in pattern.cell_ids),dtype=bool,count=len(pattern.cell_ids)).reshape(pattern.height,pattern.width)
    colors=np.asarray([background_rgb if code is None else pattern.palette.by_code[code].rgb for code in pattern.cell_ids],dtype=np.uint8).reshape(pattern.height,pattern.width,3)
    expanded=np.repeat(np.repeat(colors,cell_pixels,axis=0),cell_pixels,axis=1);opaque_pixels=np.repeat(np.repeat(opaque,cell_pixels,axis=0),cell_pixels,axis=1)
    if drill_shape=="Square":result=np.where(opaque_pixels[...,None],expanded,background_rgb)
    else:
        coverage=np.tile(_circle_coverage(cell_pixels),(pattern.height,pattern.width));alpha=(coverage.astype(np.uint16)*opaque_pixels.astype(np.uint16))[...,None]
        result=((expanded.astype(np.uint16)*alpha+background_rgb.astype(np.uint16)*(255-alpha)+127)//255).astype(np.uint8)
    image=Image.fromarray(result,"RGB")
    if show_grid and cell_pixels>1:
        draw=ImageDraw.Draw(image);line=(90,90,90) if background=="White" else (150,150,150)
        for x in range(0,image.width,cell_pixels):draw.line((x,0,x,image.height-1),fill=line)
        for y in range(0,image.height,cell_pixels):draw.line((0,y,image.width-1,y),fill=line)
    return image

class FinishedPreviewCanvas(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent);self._image=QImage();self.scale=1.0;self.offset=QPoint();self._pan=None;self.setMinimumSize(400,350)
    def set_image(self,image):self._image=QImage(ImageQt(image)).copy();self.fit_to_window()
    def fit_to_window(self):
        if self._image.isNull():return
        self.scale=max(.01,min(self.width()/self._image.width(),self.height()/self._image.height())*.96);self.offset=QPoint(round((self.width()-self._image.width()*self.scale)/2),round((self.height()-self._image.height()*self.scale)/2));self.update()
    def paintEvent(self,_event):
        painter=QPainter(self);painter.fillRect(self.rect(),Qt.GlobalColor.darkGray)
        if not self._image.isNull():painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform,True);painter.drawImage(QRectF(self.offset.x(),self.offset.y(),self._image.width()*self.scale,self._image.height()*self.scale),self._image)
    def wheelEvent(self,event):
        if self._image.isNull():return
        old=self.scale;self.scale=max(.05,min(20.0,self.scale*(1.15 if event.angleDelta().y()>0 else 1/1.15)));pos=event.position();ratio=self.scale/old;self.offset=QPoint(round(pos.x()-(pos.x()-self.offset.x())*ratio),round(pos.y()-(pos.y()-self.offset.y())*ratio));self.update()
    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.MiddleButton:self._pan=event.position()
    def mouseMoveEvent(self,event):
        if self._pan is not None:
            delta=event.position()-self._pan;self.offset+=QPoint(round(delta.x()),round(delta.y()));self._pan=event.position();self.update()
    def mouseReleaseEvent(self,event):
        if event.button()==Qt.MouseButton.MiddleButton:self._pan=None

class FinishedPreviewPanel(QWidget):
    preferenceChanged=Signal()
    def __init__(self,parent=None):
        super().__init__(parent);self.pattern=None;self.drill_shape="Square";self.drill_pitch=2.5;self._dirty=False;layout=QVBoxLayout(self);tools=QHBoxLayout();self.info=QLabel("No pattern loaded");self.background=QComboBox();self.background.addItems(("White","Black"));self.show_grid=QCheckBox("Show Grid");self.fit=QPushButton("Fit to Window");self.fit.setToolTip("Fit the finished-art preview inside the available window.");tools.addWidget(self.info,1);tools.addWidget(QLabel("Canvas Background"));tools.addWidget(self.background);tools.addWidget(self.show_grid);tools.addWidget(self.fit);layout.addLayout(tools);self.canvas=FinishedPreviewCanvas();layout.addWidget(self.canvas,1)
        self.background.currentIndexChanged.connect(self._preference_changed);self.show_grid.toggled.connect(self._preference_changed);self.fit.clicked.connect(self.canvas.fit_to_window)
    def set_pattern(self,pattern,drill_shape="Square",drill_pitch=2.5,background=None,show_grid=None):
        self.pattern=pattern;self.drill_shape=drill_shape;self.drill_pitch=drill_pitch
        if background is not None:self.background.setCurrentText(background)
        if show_grid is not None:self.show_grid.setChecked(bool(show_grid))
        self._dirty=True;self._update_info()
        if self.isVisible():self.ensure_current()
    def invalidate(self):
        self._dirty=True
        if self.isVisible():self.ensure_current()
    def ensure_current(self):
        if self._dirty:self.rebuild()
    def rebuild(self):
        if not self.pattern:return
        started=perf_counter();image=render_finished_preview(self.pattern,self.drill_shape,self.background.currentText(),self.show_grid.isChecked());self.canvas.set_image(image);self._dirty=False;self._update_info();LOG.info("Finished preview cache rebuilt shape=%s background=%s size=%sx%s in %.3f s",self.drill_shape,self.background.currentText(),image.width,image.height,perf_counter()-started)
    def _update_info(self):
        if not self.pattern:return
        width_mm,height_mm=finished_size_mm(self.pattern.width,self.pattern.height,self.drill_pitch);self.info.setText(f"Pattern: {self.pattern.width} x {self.pattern.height} drills | Drill Shape: {self.drill_shape} | Drill Pitch: {self.drill_pitch:g} mm | Finished: {width_mm:g} x {height_mm:g} mm ({mm_to_inches(width_mm):.2f} x {mm_to_inches(height_mm):.2f} in)")
    def _preference_changed(self,*_):
        if self.pattern:
            self._dirty=True
            if self.isVisible():self.ensure_current()
        self.preferenceChanged.emit()
    def state(self):return {"canvas_background":self.background.currentText(),"finished_preview_grid":self.show_grid.isChecked()}
    def showEvent(self,event):super().showEvent(event);self.ensure_current()
