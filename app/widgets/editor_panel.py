from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap, QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication,QButtonGroup,QCheckBox,QComboBox,QGroupBox,QHBoxLayout,QLabel,QLineEdit,QListWidget,QListWidgetItem,
    QMessageBox,QPushButton,QSizePolicy,QSplitter,QToolButton,QVBoxLayout,QWidget)
from .pattern_editor import PatternCanvas
from ..pattern_analysis import analyze_confetti,region_summary
from ..pattern_model import UndoStack

class EditorPanel(QWidget):
    changed=Signal()
    def __init__(self,parent=None):
        super().__init__(parent);self.pattern=None;self.owned_codes=set();self.confetti_analysis=None;self._confetti_selected_id=None;self.undo_stack=UndoStack();layout=QVBoxLayout(self);tools=QHBoxLayout()
        self.tool_group=QButtonGroup(self);self.tool_group.setExclusive(True);self.tool_buttons={}
        for name,tooltip in (("Pencil","Paint individual diamond cells"),("Eyedropper","Pick a color from the pattern"),("Flood Fill","Fill a connected area with the selected color"),("Eraser","Clear cells to transparent / no drill")):
            button=QToolButton();button.setText(name);button.setCheckable(True);button.setToolTip(tooltip);button.setAutoRaise(False)
            button.setStyleSheet("QToolButton { padding: 5px 10px; } QToolButton:checked { background-color: palette(highlight); color: palette(highlighted-text); font-weight: 600; }")
            self.tool_group.addButton(button);self.tool_buttons[name]=button
        self.tool_buttons["Pencil"].setChecked(True)
        self.undo=QPushButton("Undo");self.redo=QPushButton("Redo")
        self.undo_shortcut=QShortcut(QKeySequence("Ctrl+Z"),self);self.undo_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut);self.undo_shortcut.activated.connect(self._undo)
        self.redo_shortcut=QShortcut(QKeySequence("Ctrl+Y"),self);self.redo_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut);self.redo_shortcut.activated.connect(self._redo)
        self.redo_alt_shortcut=QShortcut(QKeySequence("Ctrl+Shift+Z"),self);self.redo_alt_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut);self.redo_alt_shortcut.activated.connect(self._redo)
        self.highlight=QCheckBox("Highlight Selected Color");self.highlight.setToolTip("Dim every cell except the selected DMC color.")
        self.before=QCheckBox("Show Original Conversion")
        tools.addWidget(QLabel("Tools"))
        for button in self.tool_buttons.values():tools.addWidget(button)
        for widget in (self.undo,self.redo,self.highlight,self.before):tools.addWidget(widget)
        tools.addStretch();layout.addLayout(tools);split=QSplitter();self.canvas=PatternCanvas();split.addWidget(self.canvas)
        side=QWidget();self.side_layout=QVBoxLayout(side);side_layout=self.side_layout;self.selected=QLabel("Selected: -");self.inspector=QLabel("Hover a cell to inspect it");self.inspector.setWordWrap(True)
        self.search=QLineEdit();self.search.setPlaceholderText("Search DMC code or color name...");self.search.setToolTip("Search the full DMC reference palette by number or name.")
        self.palette_list=QListWidget();self.used_list=QListWidget();self.replace=QPushButton("Replace Used Color…")
        self.used_list.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Expanding);self.palette_list.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Expanding)
        self.used_heading=QLabel("Used Colors");self.palette_heading=QLabel("DMC Palette");self.analysis=QLabel()
        side_layout.addWidget(self.selected);side_layout.addWidget(self.inspector);side_layout.addWidget(self.used_heading);side_layout.addWidget(self.used_list,3);side_layout.addWidget(self.replace)
        side_layout.addWidget(self.palette_heading);side_layout.addWidget(self.search);side_layout.addWidget(self.palette_list,1);side_layout.addWidget(self.analysis)
        self._build_confetti_inspector(side_layout)
        split.addWidget(side);split.setStretchFactor(0,1);layout.addWidget(split,1)
        self.tool_group.buttonClicked.connect(self._tool_selected);self.search.textChanged.connect(self._populate_palette)
        self.palette_list.itemClicked.connect(self._select_item);self.used_list.itemClicked.connect(self._select_item)
        self.highlight.toggled.connect(self._highlight);self.before.toggled.connect(self._before);self.undo.clicked.connect(self._undo);self.redo.clicked.connect(self._redo)
        self.replace.clicked.connect(self._replace);self.canvas.patternChanged.connect(self._pattern_changed);self.canvas.selectedColorChanged.connect(self.select_code);self.canvas.inspectorChanged.connect(self.inspector.setText)
        self.canvas.toolChanged.connect(self.select_tool)
        self.canvas.confettiRegionClicked.connect(self._select_confetti_id)
        self.confetti_escape=QShortcut(QKeySequence(Qt.Key.Key_Escape),self);self.confetti_escape.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut);self.confetti_escape.activated.connect(self._escape_confetti)

    def _build_confetti_inspector(self,side_layout):
        group=QGroupBox();box=QVBoxLayout(group);self.inspect_confetti=QPushButton("Confetti Inspector");self.inspect_confetti.setCheckable(True);self.inspect_confetti.setStyleSheet("QPushButton { padding: 5px 10px; } QPushButton:checked { background-color: palette(highlight); color: palette(highlighted-text); font-weight: 600; }");box.addWidget(self.inspect_confetti)
        self.confetti_content=QWidget();content=QVBoxLayout(self.confetti_content);content.setContentsMargins(0,0,0,0);self.highlight_confetti=QCheckBox("Highlight Confetti");content.addWidget(self.highlight_confetti)
        filters=QHBoxLayout();self.confetti_filter=QComboBox();self.confetti_filter.addItems(("High only","High + Medium","All suspects"));self.confetti_sort=QComboBox();self.confetti_sort.addItems(("Highest confidence","Region size"));filters.addWidget(self.confetti_filter);filters.addWidget(self.confetti_sort);content.addLayout(filters)
        self.confetti_status=QLabel("Activate the inspector to analyze suspicious small regions.");self.confetti_status.setWordWrap(True);content.addWidget(self.confetti_status)
        self.confetti_list=QListWidget();content.addWidget(self.confetti_list,1)
        navigation=QHBoxLayout();self.confetti_previous=QPushButton("Previous");self.confetti_next=QPushButton("Next");navigation.addWidget(self.confetti_previous);navigation.addWidget(self.confetti_next);content.addLayout(navigation)
        self.confetti_details=QLabel("Select a suspect region to inspect it.");self.confetti_details.setWordWrap(True);content.addWidget(self.confetti_details);box.addWidget(self.confetti_content);self.confetti_content.hide();side_layout.addWidget(group)
        self.inspect_confetti.toggled.connect(self._set_confetti_mode);self.highlight_confetti.toggled.connect(self._toggle_confetti_overlay);self.confetti_filter.currentIndexChanged.connect(lambda *_:self._refresh_confetti_list());self.confetti_sort.currentIndexChanged.connect(lambda *_:self._refresh_confetti_list())
        self.confetti_list.currentItemChanged.connect(self._confetti_item_changed);self.confetti_previous.clicked.connect(lambda:self._navigate_confetti(-1));self.confetti_next.clicked.connect(lambda:self._navigate_confetti(1))

    def set_pattern(self,pattern):
        self.inspect_confetti.setChecked(False);self.pattern=pattern;self.confetti_analysis=None;self._confetti_selected_id=None;self.undo_stack=UndoStack();self.undo_stack.add_listener(self._history_changed);self.canvas.set_pattern(pattern,self.undo_stack);self.canvas.set_confetti_analysis(None);self.canvas.set_inspection_mode(False);self.highlight_confetti.setChecked(True);self.confetti_status.setText("Activate the inspector to analyze suspicious small regions.");self.confetti_list.clear();self.confetti_details.setText("Select a suspect region to inspect it.");self.tool_buttons["Eraser"].setEnabled(pattern.supports_transparency);self.select_tool("Pencil");self._populate_palette();self._refresh_used()
        if pattern.usage:self.select_code(next(iter(pattern.usage)))

    def set_owned_codes(self,codes):self.owned_codes=set(codes);self._populate_palette()

    def _tool_selected(self,button):self.canvas.tool=button.text()
    def select_tool(self,name):
        button=self.tool_buttons[name];button.setChecked(True);self.canvas.tool=name

    def _icon(self,rgb):pix=QPixmap(18,18);pix.fill(QColor(*rgb));return QIcon(pix)
    def _populate_palette(self,*_):
        self.palette_list.clear()
        if not self.pattern:return
        query=self.search.text().strip().lower()
        for color in self.pattern.palette.colors:
            if query and query not in color.code.lower() and query not in color.name.lower():continue
            marker="✓ " if color.code in self.owned_codes else "";item=QListWidgetItem(f"{marker}DMC {color.code} - {color.name}");item.setData(Qt.ItemDataRole.UserRole,color.code);item.setIcon(self._icon(color.rgb));self.palette_list.addItem(item)

    def _refresh_used(self):
        self.used_list.clear();total=max(1,self.pattern.total_drills)
        for color,count in self.pattern.used_colors():
            item=QListWidgetItem(f"DMC {color.code} - {color.name} - {count:,} ({count/total:.1%})");item.setData(Qt.ItemDataRole.UserRole,color.code);item.setIcon(self._icon(color.rgb));self.used_list.addItem(item)
        summary=region_summary(self.pattern);self.analysis.setText(f"Drills: {self.pattern.total_drills:,} | Empty: {self.pattern.empty_cells:,}\nSingle-cell regions: {summary['single_cell_regions']:,} | Regions of 3 or less: {summary['regions_le_3']:,}")

    def _select_item(self,item):self.select_code(item.data(Qt.ItemDataRole.UserRole))
    def select_code(self,code):
        if not self.pattern or code not in self.pattern.palette.by_code:return
        self.canvas.selected_code=code;color=self.pattern.palette.by_code[code];self.selected.setText(f"Selected: DMC {code} - {color.name} - Used: {self.pattern.usage.get(code,0):,}")
        for widget in (self.used_list,self.palette_list):
            widget.blockSignals(True);match=next((row for row in range(widget.count()) if widget.item(row).data(Qt.ItemDataRole.UserRole)==code),-1);widget.setCurrentRow(match);widget.blockSignals(False)
        self.canvas.refresh()
    def _highlight(self,value):self.canvas.highlight=value;self.canvas.refresh()
    def _before(self,value):self.canvas.show_initial=value;self.canvas.refresh()
    def _pattern_changed(self):
        if self.confetti_analysis:
            self.confetti_analysis.stale=True;self.canvas.set_confetti_analysis(None);self.inspect_confetti.setChecked(False);self.confetti_status.setText("Pattern changed - activate the inspector to reanalyze confetti.")
        self._refresh_used();self.select_code(self.canvas.selected_code);self._buttons();self.changed.emit()
    def _history_changed(self,stack):
        self.undo.setEnabled(stack.can_undo);self.redo.setEnabled(stack.can_redo)
        self.undo.setText(f"Undo {stack.undo_text}" if stack.undo_text else "Undo")
        self.redo.setText(f"Redo {stack.redo_text}" if stack.redo_text else "Redo")
    def _buttons(self):self._history_changed(self.undo_stack)
    def _undo(self):
        if self.pattern and self.undo_stack.undo(self.pattern):self.canvas.refresh();self._pattern_changed()
    def _redo(self):
        if self.pattern and self.undo_stack.redo(self.pattern):self.canvas.refresh();self._pattern_changed()
    def _replace(self):
        item=self.used_list.currentItem()
        if not item:QMessageBox.information(self,"Choose a Used Color","Select the color to replace in the Used Colors list.");return
        old=item.data(Qt.ItemDataRole.UserRole);new=self.canvas.selected_code;count=self.pattern.usage.get(old,0)
        if old==new:return
        if QMessageBox.question(self,"Replace Color",f"Replace DMC {old} with DMC {new}?\n\n{count:,} cells will be changed.")!=QMessageBox.StandardButton.Yes:return
        changes=self.pattern.replace_color(old,new);self.undo_stack.push("Replace Color",changes);self.canvas.refresh();self._pattern_changed()

    def _confidence_filter(self):
        return ({"High"},{"High","Medium"},{"High","Medium","Low"})[self.confetti_filter.currentIndex()]

    def _escape_confetti(self):
        if self.inspect_confetti.isChecked():self.inspect_confetti.setChecked(False)

    def _set_confetti_mode(self,active):
        self.confetti_content.setVisible(active);self.canvas.set_inspection_mode(active)
        if not active:
            self._confetti_selected_id=self.canvas.selected_confetti_id;self.canvas.show_confetti=False;self.canvas.update();return
        if not self.pattern:return
        if not self.confetti_analysis or self.confetti_analysis.stale:self._analyze_confetti()
        else:
            self.canvas.set_confetti_analysis(self.confetti_analysis,self._confidence_filter());self.canvas.show_confetti=self.highlight_confetti.isChecked();self._refresh_confetti_list(self._confetti_selected_id);self.canvas.update()

    def _analyze_confetti(self):
        if not self.pattern:return
        self.confetti_status.setText("Analyzing pattern...");QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor);QApplication.processEvents()
        try:self.confetti_analysis=analyze_confetti(self.pattern)
        except Exception as exc:QMessageBox.critical(self,"Confetti Inspector",f"The pattern could not be analyzed.\n\n{exc}");self.inspect_confetti.setChecked(False);return
        finally:QApplication.restoreOverrideCursor()
        metrics=self.confetti_analysis.metrics;self.canvas.set_confetti_analysis(self.confetti_analysis,self._confidence_filter());self.canvas.show_confetti=self.inspect_confetti.isChecked() and self.highlight_confetti.isChecked()
        self.confetti_status.setText(f"Potential Confetti\nHigh confidence: {metrics['high_regions']} regions / {metrics['high_cells']} cells ({metrics['high_percentage']:.2f}% of drills)\nMedium confidence: {metrics['medium_regions']} regions\nLow confidence: {metrics['low_regions']} regions\nTotal regions: {metrics['regions']} | Single-cell: {metrics['single_cell_regions']} | 2-3 cell: {metrics['regions_2_to_3']}\nAffected cells: {metrics['affected_cells']}")
        self._refresh_confetti_list()

    def _visible_confetti_regions(self):
        if not self.confetti_analysis or self.confetti_analysis.stale:return []
        allowed=self._confidence_filter();regions=[region for region in self.confetti_analysis.suspects if region.confidence in allowed]
        rank={"High":0,"Medium":1,"Low":2}
        return sorted(regions,key=(lambda region:(rank[region.confidence],-region.score,region.size,region.region_id)) if self.confetti_sort.currentIndex()==0 else (lambda region:(region.size,rank[region.confidence],-region.score,region.region_id)))

    def _refresh_confetti_list(self,restore_id=None):
        current=self.confetti_list.currentItem();wanted=restore_id if restore_id is not None else current.data(Qt.ItemDataRole.UserRole) if current else self._confetti_selected_id
        regions=self._visible_confetti_regions();self.confetti_list.clear();target=-1
        for region in regions:
            item=QListWidgetItem(f"{region.confidence} - DMC {region.code} - {region.size} cell{'s' if region.size!=1 else ''}");item.setData(Qt.ItemDataRole.UserRole,region.region_id);self.confetti_list.addItem(item)
            if region.region_id==wanted:target=self.confetti_list.count()-1
        if self.confetti_analysis and not self.confetti_analysis.stale:self.canvas.set_confetti_filter(self._confidence_filter());self.canvas.show_confetti=self.inspect_confetti.isChecked() and self.highlight_confetti.isChecked();self.canvas.update()
        if self.confetti_list.count():self.confetti_list.setCurrentRow(target if target>=0 else 0)

    def _toggle_confetti_overlay(self,value):self.canvas.show_confetti=self.inspect_confetti.isChecked() and value;self.canvas.set_confetti_filter(self._confidence_filter());self.canvas.update()

    def _region_by_id(self,region_id):return next((region for region in self.confetti_analysis.regions if region.region_id==region_id),None) if self.confetti_analysis else None
    def _confetti_item_changed(self,item,*_):
        if item:self._show_confetti_region(self._region_by_id(item.data(Qt.ItemDataRole.UserRole)))
    def _select_confetti_id(self,region_id):
        for row in range(self.confetti_list.count()):
            if self.confetti_list.item(row).data(Qt.ItemDataRole.UserRole)==region_id:self.confetti_list.setCurrentRow(row);return
        self._show_confetti_region(self._region_by_id(region_id))
    def _show_confetti_region(self,region):
        if not region:return
        self._confetti_selected_id=region.region_id
        color=self.pattern.palette.by_code[region.code];neighbor=self.pattern.palette.by_code.get(region.dominant_neighbor);replacement=self.pattern.palette.by_code.get(region.suggested_replacement)
        lines=[f"DMC {region.code} - {color.name}",f"Region size: {region.size} cells",f"Confidence: {region.confidence}"]
        if neighbor:lines.extend((f"Dominant neighbor: DMC {neighbor.code} - {neighbor.name}",f"Boundary with dominant neighbor: {region.dominant_share:.0%}",f"Color difference: Delta E {region.dominant_delta_e:.1f}"))
        if replacement:lines.append(f"Suggested replacement: DMC {replacement.code} - {replacement.name}")
        self.confetti_details.setText("\n".join(lines));self.canvas.select_confetti_region(region.region_id);self.canvas.center_on_cell(region.cells[0])
    def _navigate_confetti(self,direction):
        count=self.confetti_list.count()
        if count:self.confetti_list.setCurrentRow((self.confetti_list.currentRow()+direction)%count)
