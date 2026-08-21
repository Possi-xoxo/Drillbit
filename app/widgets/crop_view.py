from PIL.ImageQt import ImageQt
from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import QWidget

class CropView(QWidget):
    cropChanged = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent); self.setMinimumSize(300, 300); self.setMouseTracking(True)
        self._image = QImage(); self._source_size = (1, 1); self._crop = (0.0, 0.0, 1.0, 1.0)
        self._aspect = 1.0; self._drag_pos = None; self._display = QRectF()

    @property
    def crop_box(self): return self._crop

    def set_pil_image(self, image):
        self._image = QImage(ImageQt(image.convert("RGB"))).copy(); self._source_size = image.size
        self.reset_crop()

    def set_target_aspect(self, aspect):
        self._aspect = max(0.01, aspect); self.reset_crop()

    def reset_crop(self):
        source_aspect = self._source_size[0] / self._source_size[1]
        if source_aspect >= self._aspect:
            width = self._aspect / source_aspect; self._crop = ((1-width)/2, 0.0, (1+width)/2, 1.0)
        else:
            height = source_aspect / self._aspect; self._crop = (0.0, (1-height)/2, 1.0, (1+height)/2)
        self.update(); self.cropChanged.emit(self._crop)

    def set_crop_box(self,box):
        if box and len(box)==4:self._crop=tuple(float(value) for value in box);self.update();self.cropChanged.emit(self._crop)

    def paintEvent(self, _event):
        painter = QPainter(self); painter.fillRect(self.rect(), QColor(35, 35, 35))
        if self._image.isNull():
            painter.setPen(Qt.GlobalColor.white); painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Drop an image here\nor click Open Image"); return
        scaled = self._image.size().scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
        self._display = QRectF((self.width()-scaled.width())/2, (self.height()-scaled.height())/2, scaled.width(), scaled.height())
        painter.drawImage(self._display, self._image)
        crop = self._screen_crop(); painter.setBrush(QColor(0, 0, 0, 135)); painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(QRectF(self._display.left(), self._display.top(), self._display.width(), crop.top()-self._display.top()))
        painter.drawRect(QRectF(self._display.left(), crop.bottom(), self._display.width(), self._display.bottom()-crop.bottom()))
        painter.drawRect(QRectF(self._display.left(), crop.top(), crop.left()-self._display.left(), crop.height()))
        painter.drawRect(QRectF(crop.right(), crop.top(), self._display.right()-crop.right(), crop.height()))
        painter.setBrush(Qt.BrushStyle.NoBrush); painter.setPen(QPen(QColor(255,255,255), 2)); painter.drawRect(crop)
        painter.setPen(QPen(QColor(255,255,255,150), 1, Qt.PenStyle.DashLine))
        painter.drawLine(crop.left()+crop.width()/3, crop.top(), crop.left()+crop.width()/3, crop.bottom())
        painter.drawLine(crop.left()+2*crop.width()/3, crop.top(), crop.left()+2*crop.width()/3, crop.bottom())
        painter.drawLine(crop.left(), crop.top()+crop.height()/3, crop.right(), crop.top()+crop.height()/3)
        painter.drawLine(crop.left(), crop.top()+2*crop.height()/3, crop.right(), crop.top()+2*crop.height()/3)

    def _screen_crop(self):
        l,t,r,b = self._crop
        return QRectF(self._display.left()+l*self._display.width(), self._display.top()+t*self._display.height(),
                      (r-l)*self._display.width(), (b-t)*self._display.height())

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._screen_crop().contains(event.position()):
            self._drag_pos = event.position(); self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        if self._drag_pos is None: return
        dx = (event.position().x()-self._drag_pos.x())/self._display.width(); dy = (event.position().y()-self._drag_pos.y())/self._display.height()
        l,t,r,b = self._crop; w,h = r-l,b-t; l=max(0,min(1-w,l+dx)); t=max(0,min(1-h,t+dy)); self._crop=(l,t,l+w,t+h)
        self._drag_pos=event.position(); self.update(); self.cropChanged.emit(self._crop)

    def mouseReleaseEvent(self, _event): self._drag_pos=None; self.unsetCursor()

    def wheelEvent(self, event):
        if self._image.isNull(): return
        factor = 0.9 if event.angleDelta().y() > 0 else 1.1
        l,t,r,b=self._crop; cx=(l+r)/2; cy=(t+b)/2; w=min(1.0,(r-l)*factor); h=min(1.0,(b-t)*factor)
        source_aspect=self._source_size[0]/self._source_size[1]; h=w*source_aspect/self._aspect
        if h>1: h=1.0; w=h*self._aspect/source_aspect
        w=max(0.02,w); h=max(0.02,h); l=max(0,min(1-w,cx-w/2)); t=max(0,min(1-h,cy-h/2)); self._crop=(l,t,l+w,t+h)
        self.update(); self.cropChanged.emit(self._crop); event.accept()
