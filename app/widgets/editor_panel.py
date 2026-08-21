from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap, QKeySequence, QShortcut
from PySide6.QtWidgets import (QButtonGroup,QCheckBox,QHBoxLayout,QLabel,QLineEdit,QListWidget,QListWidgetItem,
    QMessageBox,QPushButton,QSplitter,QToolButton,QVBoxLayout,QWidget)
from .pattern_editor import PatternCanvas
from ..pattern_analysis import region_summary
from ..pattern_model import UndoStack

class EditorPanel(QWidget):
    changed=Signal()
    def __init__(self,parent=None):
        super().__init__(parent);self.pattern=None;self.undo_stack=UndoStack();layout=QVBoxLayout(self);tools=QHBoxLayout()
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
        side=QWidget();side_layout=QVBoxLayout(side);self.selected=QLabel("Selected: -");self.inspector=QLabel("Hover a cell to inspect it");self.inspector.setWordWrap(True)
        self.search=QLineEdit();self.search.setPlaceholderText("Search DMC code or color name...");self.search.setToolTip("Search the full DMC reference palette by number or name.")
        self.palette_list=QListWidget();self.used_list=QListWidget();self.replace=QPushButton("Replace Used Color…")
        self.analysis=QLabel();side_layout.addWidget(self.selected);side_layout.addWidget(self.inspector);side_layout.addWidget(QLabel("DMC Palette"));side_layout.addWidget(self.search);side_layout.addWidget(self.palette_list,2)
        side_layout.addWidget(QLabel("Used Colors"));side_layout.addWidget(self.used_list,1);side_layout.addWidget(self.replace);side_layout.addWidget(self.analysis)
        split.addWidget(side);split.setStretchFactor(0,1);layout.addWidget(split,1)
        self.tool_group.buttonClicked.connect(self._tool_selected);self.search.textChanged.connect(self._populate_palette)
        self.palette_list.itemClicked.connect(self._select_item);self.used_list.itemClicked.connect(self._select_item)
        self.highlight.toggled.connect(self._highlight);self.before.toggled.connect(self._before);self.undo.clicked.connect(self._undo);self.redo.clicked.connect(self._redo)
        self.replace.clicked.connect(self._replace);self.canvas.patternChanged.connect(self._pattern_changed);self.canvas.selectedColorChanged.connect(self.select_code);self.canvas.inspectorChanged.connect(self.inspector.setText)
        self.canvas.toolChanged.connect(self.select_tool)

    def set_pattern(self,pattern):
        self.pattern=pattern;self.undo_stack=UndoStack();self.undo_stack.add_listener(self._history_changed);self.canvas.set_pattern(pattern,self.undo_stack);self.tool_buttons["Eraser"].setEnabled(pattern.supports_transparency);self.select_tool("Pencil");self._populate_palette();self._refresh_used()
        if pattern.usage:self.select_code(next(iter(pattern.usage)))

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
            item=QListWidgetItem(f"DMC {color.code} - {color.name}");item.setData(Qt.ItemDataRole.UserRole,color.code);item.setIcon(self._icon(color.rgb));self.palette_list.addItem(item)

    def _refresh_used(self):
        self.used_list.clear();total=max(1,self.pattern.total_drills)
        for color,count in self.pattern.used_colors():
            item=QListWidgetItem(f"DMC {color.code} - {color.name} - {count:,} ({count/total:.1%})");item.setData(Qt.ItemDataRole.UserRole,color.code);item.setIcon(self._icon(color.rgb));self.used_list.addItem(item)
        summary=region_summary(self.pattern);self.analysis.setText(f"Drills: {self.pattern.total_drills:,} | Empty: {self.pattern.empty_cells:,}\nSingle-cell regions: {summary['single_cell_regions']:,} | Regions of 3 or less: {summary['regions_le_3']:,}")

    def _select_item(self,item):self.select_code(item.data(Qt.ItemDataRole.UserRole))
    def select_code(self,code):
        if not self.pattern or code not in self.pattern.palette.by_code:return
        self.canvas.selected_code=code;color=self.pattern.palette.by_code[code];self.selected.setText(f"Selected: DMC {code} - {color.name} - Used: {self.pattern.usage.get(code,0):,}");self.canvas.refresh()
    def _highlight(self,value):self.canvas.highlight=value;self.canvas.refresh()
    def _before(self,value):self.canvas.show_initial=value;self.canvas.refresh()
    def _pattern_changed(self):self._refresh_used();self.select_code(self.canvas.selected_code);self._buttons();self.changed.emit()
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
