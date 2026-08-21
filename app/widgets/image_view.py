from PIL.ImageQt import ImageQt
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout

class ImageView(QFrame):
    def __init__(self, title: str, placeholder: str, parent=None):
        super().__init__(parent)
        self._image = QImage()
        self._nearest = False
        self.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(self)
        heading = QLabel(title); heading.setObjectName("panelHeading")
        self.label = QLabel(placeholder)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setMinimumSize(280, 280); self.label.setWordWrap(True)
        layout.addWidget(heading); layout.addWidget(self.label, 1)

    def set_pil_image(self, image, nearest=False):
        self._image = QImage(ImageQt(image.convert("RGB"))).copy()
        self._nearest = nearest
        self._refresh()

    def resizeEvent(self, event):
        super().resizeEvent(event); self._refresh()

    def _refresh(self):
        if self._image.isNull(): return
        mode = Qt.TransformationMode.FastTransformation if self._nearest else Qt.TransformationMode.SmoothTransformation
        pixmap = QPixmap.fromImage(self._image).scaled(self.label.size(), Qt.AspectRatioMode.KeepAspectRatio, mode)
        self.label.setText(""); self.label.setPixmap(pixmap)
