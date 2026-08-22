import logging
from pathlib import Path
from PIL import Image, ImageDraw
from PySide6.QtCore import QStandardPaths, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QColor, QDesktopServices, QIcon, QPixmap
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFileDialog, QFormLayout, QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QMainWindow, QMessageBox, QPushButton, QScrollArea, QSlider, QSpinBox, QSplitter,
    QTabWidget, QVBoxLayout, QWidget)
from .exporter import export_png
from .pdf_exporter import export_pattern_pdf
from .image_processor import ImageLoadError, aspect_height, aspect_width, load_image, prepare_source_reference
from .inventory import OwnedColorInventory
from .models import ConversionSettings, DitherMode, FitMode
from .palette_system import load_dmc_palette
from .pattern_converter import convert_to_pattern
from .project_io import load_project, save_project
from .physical import Orientation, calculate_page_layout, drills_from_physical, finished_size_mm, mm_to_inches
from .single_instance import SUPPORTED_FILE_SUFFIXES,select_incoming_file
from .widgets.crop_view import CropView
from .widgets.editor_panel import EditorPanel
from .widgets.image_view import ImageView
from .widgets.inventory_dialog import InventoryDialog
from .finished_preview import FinishedPreviewPanel
from .logging_manager import diagnostic_summary,get_log_directory,get_log_path,record_action,set_diagnostic_context

LOG = logging.getLogger(__name__)

def _crash_dialog(report):
    box=QMessageBox(QMessageBox.Icon.Critical,"Unexpected Error","Drillbit encountered an unexpected error.\n\nDetails were written to the application log.",parent=QApplication.activeWindow())
    open_button=box.addButton("Open Log Folder",QMessageBox.ButtonRole.ActionRole);copy_button=box.addButton("Copy Error Details",QMessageBox.ButtonRole.ActionRole);box.addButton("Close",QMessageBox.ButtonRole.RejectRole);box.exec()
    if box.clickedButton()==open_button:QDesktopServices.openUrl(QUrl.fromLocalFile(str(get_log_directory())))
    elif box.clickedButton()==copy_button:QApplication.clipboard().setText(report)

class SliderRow(QWidget):
    def __init__(self):
        super().__init__(); layout = QHBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0)
        self.slider = QSlider(Qt.Orientation.Horizontal); self.slider.setRange(-100, 100)
        self.value = QLabel("0"); self.value.setFixedWidth(32); self.value.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.slider.valueChanged.connect(lambda n: self.value.setText(f"{n:+d}" if n else "0"))
        layout.addWidget(self.slider); layout.addWidget(self.value)

class ExportDialog(QDialog):
    def __init__(self, grid_default, parent=None):
        super().__init__(parent); self.setWindowTitle("Export Options"); form = QFormLayout(self)
        self.style = QComboBox(); self.style.addItems(["Large Reference Image", "Pattern Pixels (1 px per diamond)"])
        self.cell_size = QSpinBox(); self.cell_size.setRange(2, 50); self.cell_size.setValue(10)
        self.grid = QCheckBox("Include grid lines"); self.grid.setChecked(grid_default)
        self.style.currentIndexChanged.connect(lambda i: (self.cell_size.setEnabled(i == 0), self.grid.setEnabled(i == 0)))
        form.addRow("Export style", self.style); form.addRow("Cell size (pixels)", self.cell_size); form.addRow("", self.grid)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); form.addRow(buttons)

    def values(self):
        return (self.cell_size.value(), self.grid.isChecked()) if self.style.currentIndex() == 0 else (1, False)

class PrintDialog(QDialog):
    def __init__(self, width, height, drill_mm, parent=None):
        super().__init__(parent); self.setWindowTitle("Print Pattern PDF"); form = QFormLayout(self)
        self.orientation = QComboBox(); self.orientation.addItems([item.value for item in Orientation])
        self.margin = QDoubleSpinBox(); self.margin.setRange(0.1, 1.0); self.margin.setSingleStep(0.05); self.margin.setValue(0.25); self.margin.setSuffix(" in")
        self.overlap = QDoubleSpinBox(); self.overlap.setRange(0, 1.0); self.overlap.setSingleStep(0.05); self.overlap.setValue(0.25); self.overlap.setSuffix(" in")
        self.include_symbols=QCheckBox("Include Symbols");self.include_symbols.setChecked(True);self.include_legend=QCheckBox("Include Legend");self.include_legend.setChecked(True)
        self.summary = QLabel(); self.summary.setWordWrap(True)
        for control in (self.orientation, self.margin, self.overlap):
            signal = control.currentIndexChanged if isinstance(control, QComboBox) else control.valueChanged; signal.connect(lambda *_: self._refresh(width, height, drill_mm))
        form.addRow("Paper", QLabel("US Letter - 8.5 x 11 inches")); form.addRow("Orientation", self.orientation)
        form.addRow("Margins", self.margin); form.addRow("Page overlap", self.overlap);form.addRow("",self.include_symbols);form.addRow("",self.include_legend); form.addRow(self.summary)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); form.addRow(buttons); self._refresh(width,height,drill_mm)

    def _refresh(self, width, height, drill_mm):
        layout=calculate_page_layout(width,height,drill_mm,Orientation(self.orientation.currentText()),self.margin.value(),self.overlap.value())
        wmm,hmm=finished_size_mm(width,height,drill_mm)
        self.summary.setText(f"Finished Pattern: {mm_to_inches(wmm):.2f} x {mm_to_inches(hmm):.2f} in\n"
                             f"Chart Pages Required: {layout.tile_count}\nOrientation: {layout.orientation.value}\n\n"
                             "Print at 100% / Actual Size.")

    def values(self): return Orientation(self.orientation.currentText()), self.margin.value(), self.overlap.value(),self.include_symbols.isChecked(),self.include_legend.isChecked()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__(); self.source = self.logical = self.pattern = self.source_path = None; self._changing = False; self._syncing_physical = False
        self.palette=load_dmc_palette();self.inventory=OwnedColorInventory(self.palette);self.project_path=None;self.dirty=False;self.manual_edits=False
        self.setWindowTitle("Diamond Art Converter"); self.resize(1320, 820); self.setAcceptDrops(True)
        self._build_ui(); self._connect()
        self.timer = QTimer(self); self.timer.setSingleShot(True); self.timer.setInterval(180); self.timer.timeout.connect(self.refresh_preview)
        self._update_stats()
        self.editor.set_owned_codes(self.inventory.owned)
        if self.inventory.load_error:QTimer.singleShot(0,lambda:QMessageBox.warning(self,"Colors I Own","The owned-color inventory could not be read. Drillbit preserved the file and started with an empty inventory. See Diagnostics for details."))

    def _build_ui(self):
        diagnostics=self.menuBar().addMenu("Help").addMenu("Diagnostics")
        self.open_log_folder_action=QAction("Open Log Folder",self);self.open_latest_log_action=QAction("Open Latest Log",self);self.copy_diagnostic_action=QAction("Copy Diagnostic Summary",self)
        diagnostics.addActions((self.open_log_folder_action,self.open_latest_log_action,self.copy_diagnostic_action))
        root = QWidget(); outer = QVBoxLayout(root); toolbar = QHBoxLayout()
        self.open_button = QPushButton("Open Image…"); self.export_button = QPushButton("Export Image PNG…"); self.export_button.setEnabled(False)
        self.print_button = QPushButton("Print Pattern PDF…"); self.print_button.setEnabled(False)
        self.open_project_button=QPushButton("Open Project…");self.save_project_button=QPushButton("Save Project");self.save_project_as_button=QPushButton("Save As…")
        self.regenerate_button=QPushButton("Regenerate Pattern");self.regenerate_button.setToolTip("Rebuild the automatic DMC pattern from the current source settings.")
        self.finished_preview_button=QPushButton("Finished Preview");self.finished_preview_button.setToolTip("Preview the current pattern as completed square or round drills.");self.finished_preview_button.setEnabled(False);self.reset_button = QPushButton("Reset")
        for button in (self.open_button,self.open_project_button,self.save_project_button,self.save_project_as_button,self.regenerate_button,self.export_button,self.print_button,self.finished_preview_button,self.reset_button): toolbar.addWidget(button)
        toolbar.addStretch(); outer.addLayout(toolbar)
        splitter = QSplitter(); pictures = QWidget(); picture_layout = QHBoxLayout(pictures)
        original_panel=QWidget(); original_layout=QVBoxLayout(original_panel); original_heading=QLabel("Crop & Reposition"); original_heading.setObjectName("panelHeading")
        self.original_view = CropView(); original_hint=QLabel("Drag to reposition. Use the mouse wheel to zoom."); original_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        original_layout.addWidget(original_heading); original_layout.addWidget(self.original_view,1); original_layout.addWidget(original_hint)
        self.preview_view = ImageView("Diamond-Art Preview", "Your converted pattern will appear here")
        picture_layout.addWidget(original_panel, 1); picture_layout.addWidget(self.preview_view, 1)
        self.editor=EditorPanel();self.finished_preview=FinishedPreviewPanel();self.tabs=QTabWidget();self.tabs.addTab(pictures,"1. Image & Convert");self.tabs.addTab(self.editor,"2. Edit Pattern");self.tabs.addTab(self.finished_preview,"3. Finished Preview");splitter.addWidget(self.tabs)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setMinimumWidth(330); settings = QWidget(); form = QFormLayout(settings)
        self.width_box = QSpinBox(); self.width_box.setRange(10, 1000); self.width_box.setValue(100)
        self.height_box = QSpinBox(); self.height_box.setRange(10, 1000); self.height_box.setValue(100)
        self.lock_aspect = QCheckBox("Lock Aspect Ratio"); self.lock_aspect.setChecked(True)
        self.size_mode=QComboBox(); self.size_mode.addItems(["Diamonds", "Finished Size"])
        self.drill_size=QDoubleSpinBox(); self.drill_size.setRange(2.0,4.0); self.drill_size.setSingleStep(0.1); self.drill_size.setValue(2.5); self.drill_size.setSuffix(" mm");self.drill_size.setToolTip("Physical spacing from one drill position to the next. This determines the finished pattern size.")
        self.drill_shape=QComboBox();self.drill_shape.addItems(("Square","Round"));self.drill_shape.setToolTip("Changes how drills are visualized. It does not change the logical pattern.")
        self.physical_unit=QComboBox(); self.physical_unit.addItems(["in", "cm"])
        self.physical_width=QDoubleSpinBox(); self.physical_width.setRange(0.1,160); self.physical_width.setDecimals(2)
        self.physical_height=QDoubleSpinBox(); self.physical_height.setRange(0.1,160); self.physical_height.setDecimals(2)
        self.physical_width.setEnabled(False); self.physical_height.setEnabled(False); self.physical_unit.setEnabled(False)
        self.fit_mode = QComboBox(); self.fit_mode.addItems([m.value for m in FitMode]); self.fit_mode.setCurrentText(FitMode.FILL.value)
        self.colors = QComboBox(); self.colors.addItems([str(n) for n in (8, 12, 16, 24, 32, 48, 64)]); self.colors.setCurrentText("16")
        self.only_owned=QCheckBox("Only Use Colors I Own");self.only_owned.setToolTip("Restrict automatic conversion to DMC colors marked as owned in your inventory.")
        self.manage_owned=QPushButton("Manage Colors I Own");self.owned_summary=QLabel();self.owned_summary.setWordWrap(True)
        self.dither = QComboBox(); self.dither.addItems([m.value for m in DitherMode])
        self.dither.setToolTip("Floyd-Steinberg mixes neighboring colors; Off keeps cleaner solid regions.")
        self.colors.setToolTip("Limits the final pattern to this many DMC reference colors.")
        self.preserve_transparency=QCheckBox("Preserve Transparency");self.preserve_transparency.setToolTip("Keep transparent parts of the source image transparent instead of filling them with white.")
        self.brightness = SliderRow(); self.contrast = SliderRow(); self.saturation = SliderRow()
        self.reset_crop=QPushButton("Reset Crop"); self.reset_adjustments = QPushButton("Reset Adjustments"); self.show_grid = QCheckBox("Show Grid")
        self.pattern_label = QLabel(); self.total_label = QLabel(); self.color_label = QLabel("Colors Used: —")
        self.finished_label=QLabel(); self.finished_label.setStyleSheet("font-weight: 600; font-size: 13px;")
        self.palette_list = QListWidget(); self.palette_list.setMinimumHeight(200)
        rows = [("Active palette",QLabel("DMC Reference Palette")),("Size mode",self.size_mode),("Drill Pitch",self.drill_size),("Drill Shape",self.drill_shape),("Width (diamonds)", self.width_box), ("Height (diamonds)", self.height_box), ("", self.lock_aspect),
            ("Finished width",self.physical_width),("Finished height",self.physical_height),("Units",self.physical_unit),("",self.reset_crop),
            ("Image fit", self.fit_mode), ("Maximum colors", self.colors),("",self.only_owned),("",self.manage_owned),("",self.owned_summary), ("Dithering", self.dither),("",self.preserve_transparency),
            ("Brightness", self.brightness), ("Contrast", self.contrast), ("Saturation", self.saturation),
            ("", self.reset_adjustments), ("", self.show_grid)]
        for label, widget in rows: form.addRow(label, widget)
        line = QFrame(); line.setFrameShape(QFrame.Shape.HLine); form.addRow(line)
        form.addRow(self.pattern_label); form.addRow(self.finished_label); form.addRow(self.total_label); form.addRow(self.color_label); form.addRow("Palette usage", self.palette_list)
        scroll.setWidget(settings); splitter.addWidget(scroll); splitter.setStretchFactor(0, 1); outer.addWidget(splitter, 1)
        self.setCentralWidget(root); self.statusBar().showMessage("Ready — open or drop an image to begin")
        self.setStyleSheet("QLabel#panelHeading { font-size: 15px; font-weight: 600; } QPushButton { padding: 6px 12px; }")

    def _connect(self):
        self.open_button.clicked.connect(self.open_image_dialog); self.export_button.clicked.connect(self.export_dialog)
        self.open_log_folder_action.triggered.connect(self._open_log_folder);self.open_latest_log_action.triggered.connect(self._open_latest_log);self.copy_diagnostic_action.triggered.connect(self._copy_diagnostic_summary)
        self.print_button.clicked.connect(self.print_pdf_dialog)
        self.finished_preview_button.clicked.connect(self._open_finished_preview);self.tabs.currentChanged.connect(self._tab_changed);self.finished_preview.preferenceChanged.connect(self._finished_preference_changed);self.drill_shape.currentTextChanged.connect(self._drill_shape_changed)
        self.open_project_button.clicked.connect(self.open_project_dialog);self.save_project_button.clicked.connect(self.save_current_project);self.save_project_as_button.clicked.connect(lambda:self.save_current_project(True))
        self.regenerate_button.clicked.connect(self.regenerate_pattern);self.editor.changed.connect(self._editor_changed)
        self.reset_button.clicked.connect(self.reset_all); self.reset_adjustments.clicked.connect(self._reset_adjustments)
        self.reset_crop.clicked.connect(self.original_view.reset_crop); self.original_view.cropChanged.connect(self.schedule_preview)
        self.width_box.valueChanged.connect(self._width_changed); self.height_box.valueChanged.connect(self._height_changed)
        self.drill_size.valueChanged.connect(self._physical_settings_changed); self.size_mode.currentIndexChanged.connect(self._size_mode_changed)
        self.physical_unit.currentIndexChanged.connect(self._physical_settings_changed)
        self.physical_width.valueChanged.connect(lambda value: self._physical_input_changed(True, value))
        self.physical_height.valueChanged.connect(lambda value: self._physical_input_changed(False, value))
        for control in (self.fit_mode, self.colors, self.dither): control.currentIndexChanged.connect(self.schedule_preview)
        self.preserve_transparency.toggled.connect(self.schedule_preview)
        self.only_owned.toggled.connect(self.schedule_preview);self.manage_owned.clicked.connect(self.manage_owned_colors)
        for row in (self.brightness, self.contrast, self.saturation): row.slider.valueChanged.connect(self.schedule_preview)
        self.show_grid.toggled.connect(self._render_preview)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and len(event.mimeData().urls()) == 1: event.acceptProposedAction()

    def dropEvent(self, event):
        if self._confirm_discard():self.load_path(event.mimeData().urls()[0].toLocalFile())

    def open_image_dialog(self):
        if not self._confirm_discard():return
        path, _ = QFileDialog.getOpenFileName(self, "Open Image", "", "Images (*.jpg *.jpeg *.png *.webp *.bmp)")
        if path: self.load_path(path)

    def load_path(self, path):
        try:
            record_action("Opening image")
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor); self.source = load_image(path); self.source_path = Path(path)
            self.project_path=None;self.pattern=None;self.manual_edits=False
            self.original_view.set_pil_image(self.source)
            if self.lock_aspect.isChecked(): self._set_height(aspect_height(self.width_box.value(), *self.source.size))
            LOG.info("Image loaded width=%s height=%s mode=%s",self.source.width,self.source.height,self.source.mode);record_action("Image loaded")
            self.statusBar().showMessage(f"Loaded {self.source_path.name} — {self.source.width} × {self.source.height} px"); self.refresh_preview()
        except ImageLoadError as exc: QMessageBox.warning(self, "Could Not Open Image", str(exc))
        except Exception: LOG.exception("Image load failed"); QMessageBox.critical(self, "Could Not Open Image", "An unexpected error occurred.")
        finally: QApplication.restoreOverrideCursor()

    def _settings(self):
        return ConversionSettings(width=self.width_box.value(), height=self.height_box.value(), max_colors=int(self.colors.currentText()),
            fit_mode=FitMode(self.fit_mode.currentText()), dither=DitherMode(self.dither.currentText()), brightness=self.brightness.slider.value(),
            contrast=self.contrast.slider.value(), saturation=self.saturation.slider.value(), crop_box=self.original_view.crop_box,
            preserve_transparency=self.preserve_transparency.isChecked(),only_use_owned_colors=self.only_owned.isChecked())

    def schedule_preview(self, *_):
        self._update_stats()
        if self.source is not None:
            if self.manual_edits:
                self.statusBar().showMessage("Settings changed. Click Regenerate Pattern to apply them; manual edits are protected.")
            else:self.timer.start()

    def refresh_preview(self):
        if self.source is None: return
        if self.only_owned.isChecked() and not self.inventory.owned:self._show_empty_owned_inventory();return
        try:
            settings=self._settings();record_action("Conversion requested");set_diagnostic_context(pattern=f"{settings.width} x {settings.height}",max_colors=settings.max_colors,transparency=settings.preserve_transparency)
            overlay_state=self.editor.source_overlay_state();QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor);self.pattern=convert_to_pattern(self.source,settings,self.palette,self.inventory.owned);self.pattern.metadata["source_reference_settings"]=self._conversion_settings_payload(settings);self.logical=self.pattern.to_image();reference=prepare_source_reference(self.source,settings);LOG.debug("Source overlay cache rebuilt size=%sx%s",reference.width,reference.height)
            self.editor.set_pattern(self.pattern,reference,overlay_state);self._sync_finished_preview();self._render_preview();self._show_palette(self.pattern.used_colors());self._update_stats();self.export_button.setEnabled(True);self.print_button.setEnabled(True);self.finished_preview_button.setEnabled(True);self.dirty=True;self._update_title();self.statusBar().showMessage("DMC pattern updated")
        except Exception as exc: LOG.exception("Conversion failed"); QMessageBox.critical(self, "Conversion Failed", str(exc))
        finally: QApplication.restoreOverrideCursor()

    def _render_preview(self, *_):
        if self.logical is None: return
        preview = self.logical.resize((self.logical.width * 8, self.logical.height * 8))
        if preview.mode=="RGBA":
            checker=Image.new("RGB",preview.size,(225,225,225));checker_draw=ImageDraw.Draw(checker)
            for y in range(0,preview.height,16):
                for x in range(0,preview.width,16):
                    if (x//16+y//16)%2:checker_draw.rectangle((x,y,x+15,y+15),fill=(180,180,180))
            checker.paste(preview,mask=preview.getchannel("A"));preview=checker
        if self.show_grid.isChecked():
            draw = ImageDraw.Draw(preview)
            for x in range(0, preview.width, 8): draw.line((x, 0, x, preview.height - 1), fill=(70, 70, 70))
            for y in range(0, preview.height, 8): draw.line((0, y, preview.width - 1, y), fill=(70, 70, 70))
        self.preview_view.set_pil_image(preview, nearest=True)

    def _sync_finished_preview(self,state=None):
        if not self.pattern:return
        state=state or self.finished_preview.state();self.pattern.metadata["drill_shape"]=self.drill_shape.currentText();self.finished_preview.set_pattern(self.pattern,self.drill_shape.currentText(),self.drill_size.value(),state.get("canvas_background","White"),state.get("finished_preview_grid",False))

    def _open_finished_preview(self):
        if not self.pattern:return
        self.tabs.setCurrentIndex(2);self.finished_preview.ensure_current();LOG.info("Finished preview opened")

    def _tab_changed(self,index):
        if index==2 and self.pattern:self.finished_preview.ensure_current()

    def _drill_shape_changed(self,shape):
        if not self.pattern:return
        self.pattern.metadata["drill_shape"]=shape;self._sync_finished_preview();self.dirty=True;self._update_title();LOG.info("Drill shape changed to %s",shape)

    def _finished_preference_changed(self):
        if self.pattern:self.dirty=True;self._update_title()

    def _show_palette(self, palette):
        self.palette_list.clear()
        for item in palette:
            entry,count=(item if isinstance(item,tuple) else (item,item.count))
            pixmap = QPixmap(22, 22); pixmap.fill(QColor(*entry.rgb));label=f"DMC {entry.code} - {entry.name} - {count:,}" if hasattr(entry,"code") else f"{entry.hex} - {count:,}"
            item=QListWidgetItem(label)
            item.setIcon(QIcon(pixmap)); self.palette_list.addItem(item)
        requested=self.pattern.metadata.get("requested_colors",self.colors.currentText()) if self.pattern else self.colors.currentText()
        reason=self.pattern.metadata.get("utilization_reason","") if self.pattern else ""
        text=f"Requested maximum: {requested}\nColors used: {len(palette)} of {requested}"
        if self.pattern and self.pattern.metadata.get("only_use_owned_colors"):
            text+=f"\nOwned colors available: {self.pattern.metadata.get('owned_colors_available',0)}\nEffective palette limit: {self.pattern.metadata.get('effective_palette_limit',0)}"
        if reason:text+=f"\n{reason}"
        self.color_label.setText(text)

    def _update_stats(self):
        w,h=self.width_box.value(),self.height_box.value(); drill=self.drill_size.value(); wmm,hmm=finished_size_mm(w,h,drill)
        drills=self.pattern.total_drills if self.pattern else w*h;empty=w*h-drills
        self.pattern_label.setText(f"Pattern Grid: {w:,} × {h:,} cells"); self.total_label.setText(f"Total Drills: {drills:,}"+(f"\nEmpty Cells: {empty:,}" if empty else ""))
        self.finished_label.setText(f"Finished Size: {wmm:g} × {hmm:g} mm\n{mm_to_inches(wmm):.2f} × {mm_to_inches(hmm):.2f} in")
        self._syncing_physical=True; factor=25.4 if self.physical_unit.currentText()=="in" else 10.0
        self.physical_width.setValue(wmm/factor); self.physical_height.setValue(hmm/factor); self._syncing_physical=False
        self._update_owned_summary()

    def _update_owned_summary(self):
        count=len(self.inventory.owned);text=f"Owned colors available: {count}"
        if self.only_owned.isChecked():text+=f"\nEffective palette limit: {min(int(self.colors.currentText()),count) if count else 0}"
        self.owned_summary.setText(text)

    def manage_owned_colors(self):
        InventoryDialog(self.inventory,self).exec();self.editor.set_owned_codes(self.inventory.owned);self._update_owned_summary()
        if self.pattern:
            unowned=set(self.pattern.usage)-self.inventory.owned
            if self.only_owned.isChecked() and unowned:self.statusBar().showMessage(f"Current pattern uses {len(unowned)} colors not marked as owned. Regenerate to apply inventory changes.")

    def _show_empty_owned_inventory(self):
        box=QMessageBox(QMessageBox.Icon.Information,"Colors I Own","No owned DMC colors are selected.",parent=self)
        manage=box.addButton("Manage Colors I Own",QMessageBox.ButtonRole.ActionRole);box.addButton(QMessageBox.StandardButton.Cancel);box.exec()
        if box.clickedButton()==manage:self.manage_owned_colors()

    def _width_changed(self, value):
        if self.source is not None and self.lock_aspect.isChecked() and not self._changing: self._set_height(aspect_height(value, *self.source.size))
        self.original_view.set_target_aspect(self.width_box.value()/self.height_box.value()); self.schedule_preview()

    def _height_changed(self, value):
        if self.source is not None and self.lock_aspect.isChecked() and not self._changing:
            self._changing = True; self.width_box.setValue(aspect_width(value, *self.source.size)); self._changing = False
        self.original_view.set_target_aspect(self.width_box.value()/self.height_box.value()); self.schedule_preview()

    def _set_height(self, value): self._changing = True; self.height_box.setValue(value); self._changing = False
    def _reset_adjustments(self):
        for row in (self.brightness, self.contrast, self.saturation): row.slider.setValue(0)

    def reset_all(self):
        if self.manual_edits and QMessageBox.question(self,"Reset and Regenerate","Resetting will discard manual cell edits. Continue?")!=QMessageBox.StandardButton.Yes:return
        self.width_box.setValue(100); self.fit_mode.setCurrentText(FitMode.FILL.value); self.colors.setCurrentText("16")
        self.dither.setCurrentText(DitherMode.OFF.value);self.preserve_transparency.setChecked(False);self.only_owned.setChecked(False);self.show_grid.setChecked(False);self.lock_aspect.setChecked(True);self.drill_size.setValue(2.5);self.drill_shape.setCurrentText("Square");self.finished_preview.background.setCurrentText("White");self.finished_preview.show_grid.setChecked(False);self.size_mode.setCurrentIndex(0);self._reset_adjustments();self.original_view.reset_crop()
        if self.source is not None:self._set_height(aspect_height(100,*self.source.size));self.manual_edits=False;self.refresh_preview()

    def export_dialog(self):
        if self.logical is None: QMessageBox.information(self, "Nothing to Export", "Open an image and create a preview first."); return
        options = ExportDialog(self.show_grid.isChecked(), self)
        if options.exec() != QDialog.DialogCode.Accepted: return
        name = f"{self.source_path.stem}_diamond_art.png" if self.source_path else "diamond_art.png"
        path, _ = QFileDialog.getSaveFileName(self, "Export PNG", name, "PNG Image (*.png)")
        if not path: return
        try:
            size, grid = options.values();record_action("PNG export started");LOG.info("PNG export started cell_size=%s grid=%s",size,grid);saved = export_png(self.pattern, path, size, grid);LOG.info("PNG export completed");record_action("PNG export completed");self.statusBar().showMessage(f"Exported {saved}")
            QMessageBox.information(self, "Export Complete", f"Saved to:\n{saved}")
        except OSError: LOG.exception("Export failed"); QMessageBox.critical(self, "Export Failed", "The file could not be written.")

    def _size_mode_changed(self, index):
        finished=index==1; self.width_box.setEnabled(not finished); self.height_box.setEnabled(not finished)
        self.physical_width.setEnabled(finished); self.physical_height.setEnabled(finished); self.physical_unit.setEnabled(finished)

    def _physical_settings_changed(self, *_):
        self._update_stats()
        if self.pattern:self.finished_preview.drill_pitch=self.drill_size.value();self.finished_preview._update_info()
        self.schedule_preview()

    def _physical_input_changed(self, from_width, value):
        if self._syncing_physical or self.size_mode.currentIndex()!=1: return
        unit=self.physical_unit.currentText(); drill=self.drill_size.value()
        if self.lock_aspect.isChecked() and self.source is not None:
            if from_width:
                width,_=drills_from_physical(value,value,unit,drill); height=aspect_height(width,*self.source.size)
            else:
                _,height=drills_from_physical(value,value,unit,drill); width=aspect_width(height,*self.source.size)
        else:
            width,height=drills_from_physical(self.physical_width.value(),self.physical_height.value(),unit,drill)
        self._changing=True; self.width_box.setValue(max(10,min(1000,width))); self.height_box.setValue(max(10,min(1000,height))); self._changing=False
        self.original_view.set_target_aspect(self.width_box.value()/self.height_box.value()); self.schedule_preview()

    def print_pdf_dialog(self):
        if self.logical is None: QMessageBox.information(self,"Nothing to Print","Open an image and create a preview first."); return
        dialog=PrintDialog(self.logical.width,self.logical.height,self.drill_size.value(),self)
        if dialog.exec()!=QDialog.DialogCode.Accepted: return
        name=f"{self.source_path.stem}_printable_pattern.pdf" if self.source_path else "diamond_art_pattern.pdf"
        path,_=QFileDialog.getSaveFileName(self,"Save Printable Pattern",name,"PDF Document (*.pdf)")
        if not path: return
        try:
            orientation,margin,overlap,include_symbols,include_legend=dialog.values();record_action("PDF export started");LOG.info("PDF export started orientation=%s symbols=%s legend=%s",orientation.value,include_symbols,include_legend);saved,layout=export_pattern_pdf(self.pattern,path,self.drill_size.value(),orientation,margin,overlap,include_symbols,include_legend,drill_shape=self.drill_shape.currentText());LOG.info("PDF export completed pages=%s",layout.tile_count);record_action("PDF export completed")
            QMessageBox.information(self,"PDF Complete",f"Printable pattern saved to:\n{saved}\n\nChart pages: {layout.tile_count}\nPrint at 100% / Actual Size.")
        except Exception as exc: LOG.exception("PDF export failed"); QMessageBox.critical(self,"PDF Export Failed",f"The printable pattern could not be created.\n\n{exc}")

    def regenerate_pattern(self):
        if self.source is None:return
        if self.manual_edits and QMessageBox.question(self,"Regenerate Pattern","This will regenerate the pattern and discard manual cell edits. Continue?")!=QMessageBox.StandardButton.Yes:return
        record_action("Manual regeneration initiated");LOG.info("Pattern regeneration initiated");self.manual_edits=False;self.refresh_preview()

    def _editor_changed(self):
        if not self.pattern:return
        self.logical=self.pattern.to_image();self.manual_edits=True;self.dirty=True;self.finished_preview.invalidate();self._render_preview();self._show_palette(self.pattern.used_colors());self._update_stats();self._update_title()

    def _project_settings(self):
        settings=self._settings()
        return {"width":settings.width,"height":settings.height,"max_colors":settings.max_colors,"fit_mode":settings.fit_mode.value,
                "dither":settings.dither.value,"brightness":settings.brightness,"contrast":settings.contrast,"saturation":settings.saturation,
                "crop_box":list(settings.crop_box) if settings.crop_box else None,"drill_mm":self.drill_size.value(),"drill_shape":self.drill_shape.currentText(),**self.finished_preview.state(),
                "preserve_transparency":settings.preserve_transparency,"alpha_threshold":settings.alpha_threshold,"only_use_owned_colors":settings.only_use_owned_colors}

    def _conversion_settings_payload(self,settings):
        return {"width":settings.width,"height":settings.height,"max_colors":settings.max_colors,"fit_mode":settings.fit_mode.value,"dither":settings.dither.value,"brightness":settings.brightness,"contrast":settings.contrast,"saturation":settings.saturation,"crop_box":list(settings.crop_box) if settings.crop_box else None,"preserve_transparency":settings.preserve_transparency,"alpha_threshold":settings.alpha_threshold,"only_use_owned_colors":settings.only_use_owned_colors}

    def _reference_settings(self,data,pattern):
        return ConversionSettings(width=pattern.width,height=pattern.height,max_colors=int(data.get("max_colors",16)),fit_mode=FitMode(data.get("fit_mode",FitMode.FILL.value)),dither=DitherMode(data.get("dither",DitherMode.OFF.value)),brightness=int(data.get("brightness",0)),contrast=int(data.get("contrast",0)),saturation=int(data.get("saturation",0)),crop_box=tuple(data["crop_box"]) if data.get("crop_box") else None,preserve_transparency=bool(data.get("preserve_transparency",False)),alpha_threshold=int(data.get("alpha_threshold",128)),only_use_owned_colors=bool(data.get("only_use_owned_colors",False)))

    def save_current_project(self,save_as=False):
        if self.pattern is None:QMessageBox.information(self,"Nothing to Save","Open an image and create a pattern first.");return False
        path=self.project_path
        if save_as or not path:
            name=f"{self.source_path.stem}.diamond" if self.source_path else "diamond_art_project.diamond"
            path,_=QFileDialog.getSaveFileName(self,"Save Diamond Art Project",name,"Diamond Art Project (*.diamond)")
            if not path:return False
        try:
            self.project_path=save_project(path,self.pattern,self.source,self._project_settings(),{"selected_code":self.editor.canvas.selected_code,**self.editor.source_overlay_state()});LOG.info("Project saved");record_action("Project saved")
            self.dirty=False;self._update_title();self.statusBar().showMessage(f"Saved {self.project_path.name}");return True
        except Exception as exc:LOG.exception("Project save failed");QMessageBox.critical(self,"Save Failed",str(exc));return False

    def open_project_dialog(self):
        if not self._confirm_discard():return
        path,_=QFileDialog.getOpenFileName(self,"Open Diamond Art Project","","Diamond Art Project (*.diamond)")
        if not path:return
        self.load_project_path(path)

    def load_project_path(self,path):
        try:
            record_action("Opening project")
            pattern,source,settings,editor_state=load_project(path,self.palette);self.pattern=pattern;self.source=source;self.project_path=Path(path);self.source_path=None;self.manual_edits=True
            self._apply_project_settings(settings)
            if source is not None:self.original_view.set_pil_image(source);self.original_view.set_crop_box(settings.get("crop_box"))
            reference=None
            if source is not None:
                reference_data=pattern.metadata.get("source_reference_settings",settings);reference=prepare_source_reference(source,self._reference_settings(reference_data,pattern));LOG.debug("Source overlay cache rebuilt size=%sx%s",reference.width,reference.height)
            else:LOG.debug("Overlay source unavailable")
            self.logical=pattern.to_image();self.editor.set_pattern(pattern,reference,editor_state);self.editor.select_code(editor_state.get("selected_code",next(iter(pattern.usage),None)));self._sync_finished_preview(settings)
            self._render_preview();self._show_palette(pattern.used_colors());self.export_button.setEnabled(True);self.print_button.setEnabled(True);self.finished_preview_button.setEnabled(True);self.manual_edits=True;self.dirty=False;self._update_stats();self._update_title();self.tabs.setCurrentIndex(1)
            LOG.info("Project opened pattern=%sx%s colors=%s",pattern.width,pattern.height,len(pattern.usage));record_action("Project opened")
        except Exception as exc:LOG.exception("Project open failed");QMessageBox.critical(self,"Open Project Failed",str(exc))

    def activate_existing_window(self):
        if self.isMinimized():self.showNormal()
        elif self.isHidden():self.show()
        self.raise_();self.activateWindow()
        handle=self.windowHandle()
        if handle is not None:handle.requestActivate()
        QApplication.alert(self,1500);LOG.info("Existing window restored")

    def handle_activation_request(self,files):
        self.activate_existing_window()
        if not files:return
        selected=select_incoming_file(files)
        if selected is None:
            LOG.warning("No supported existing incoming file was provided")
            QMessageBox.warning(self,"Could Not Open File","No supported existing Drillbit file was provided.");return
        if len(files)>1:LOG.info("Multiple incoming files received; opening the first supported file only")
        if not self._confirm_discard():return
        if selected.suffix.lower()==".diamond":self.load_project_path(selected)
        else:self.load_path(selected)

    def _apply_project_settings(self,data):
        self._changing=True;self.width_box.setValue(data.get("width",100));self.height_box.setValue(data.get("height",100));self._changing=False
        self.colors.setCurrentText(str(data.get("max_colors",16)));self.fit_mode.setCurrentText(data.get("fit_mode",FitMode.FILL.value));self.dither.setCurrentText(data.get("dither",DitherMode.OFF.value))
        self.brightness.slider.setValue(data.get("brightness",0));self.contrast.slider.setValue(data.get("contrast",0));self.saturation.slider.setValue(data.get("saturation",0));self.drill_size.setValue(data.get("drill_mm",2.5));self.drill_shape.setCurrentText(data.get("drill_shape","Square"))
        self.preserve_transparency.setChecked(data.get("preserve_transparency",False))
        self.only_owned.setChecked(data.get("only_use_owned_colors",False))

    def _confirm_discard(self):
        if not self.dirty:return True
        result=QMessageBox.question(self,"Unsaved Changes","Save changes before continuing?",QMessageBox.StandardButton.Save|QMessageBox.StandardButton.Discard|QMessageBox.StandardButton.Cancel)
        if result==QMessageBox.StandardButton.Cancel:return False
        return self.save_current_project() if result==QMessageBox.StandardButton.Save else True

    def _update_title(self):
        name=self.project_path.name if self.project_path else (self.source_path.name if self.source_path else "Untitled")
        self.setWindowTitle(f"Diamond Art Converter - {name}{' *' if self.dirty else ''}")

    def closeEvent(self,event):
        if self._confirm_discard():LOG.info("Project close accepted");record_action("Application close accepted");event.accept()
        else:event.ignore()

    def _open_log_folder(self):
        get_log_directory().mkdir(parents=True,exist_ok=True)
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(get_log_directory()))):QMessageBox.warning(self,"Diagnostics","The log folder could not be opened.")
    def _open_latest_log(self):
        if not get_log_path().exists() or not QDesktopServices.openUrl(QUrl.fromLocalFile(str(get_log_path()))):QMessageBox.warning(self,"Diagnostics","The latest log could not be opened.")
    def _copy_diagnostic_summary(self):
        current={"Pattern":f"{self.pattern.width} x {self.pattern.height}" if self.pattern else "None","Maximum colors":self.colors.currentText(),"Colors used":len(self.pattern.usage) if self.pattern else 0,"Transparency":self.preserve_transparency.isChecked(),"Owned Color Inventory":str(self.inventory.path),"Owned colors":len(self.inventory.owned)}
        QApplication.clipboard().setText(diagnostic_summary(**current));self.statusBar().showMessage("Diagnostic summary copied")
