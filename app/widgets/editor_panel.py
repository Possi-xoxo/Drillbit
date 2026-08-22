from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap, QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication,QButtonGroup,QCheckBox,QComboBox,QDialog,QDialogButtonBox,QGroupBox,QHBoxLayout,QLabel,QLineEdit,QListWidget,QListWidgetItem,
    QMessageBox,QPushButton,QScrollArea,QSizePolicy,QSlider,QSplitter,QToolButton,QVBoxLayout,QWidget)
import logging
from .pattern_editor import PatternCanvas
from ..pattern_analysis import analyze_confetti,region_summary
from ..pattern_model import UndoStack
from ..palette_optimizer import delta_e

LOG=logging.getLogger(__name__)

class EditorPanel(QWidget):
    changed=Signal()
    def __init__(self,parent=None):
        super().__init__(parent);self.pattern=None;self.pattern_clipboard=None;self.owned_codes=set();self.confetti_analysis=None;self._confetti_selected_id=None;self.undo_stack=UndoStack();layout=QVBoxLayout(self);tools=QHBoxLayout()
        self.tool_group=QButtonGroup(self);self.tool_group.setExclusive(True);self.tool_buttons={}
        for name,tooltip in (("Pencil","Paint individual diamond cells"),("Eyedropper","Pick a color from the pattern"),("Flood Fill","Fill a connected area with the selected color"),("Eraser","Clear cells to transparent / no drill"),("Select","Select and move a rectangular region of logical cells")):
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
        self.palette_list=QListWidget();self.used_list=QListWidget()
        self.used_list.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Expanding);self.palette_list.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Expanding)
        self.used_heading=QLabel("Used Colors");self.palette_heading=QLabel("DMC Palette");self.analysis=QLabel()
        side_layout.addWidget(self.selected);side_layout.addWidget(self.inspector);side_layout.addWidget(self.used_heading);side_layout.addWidget(self.used_list,3);self._build_global_replacement(side_layout)
        side_layout.addWidget(self.palette_heading);side_layout.addWidget(self.search);side_layout.addWidget(self.palette_list,1);side_layout.addWidget(self.analysis)
        self._build_source_overlay_controls(side_layout)
        self._build_selection_controls(side_layout)
        self._build_confetti_inspector(side_layout)
        split.addWidget(side);split.setStretchFactor(0,1);layout.addWidget(split,1)
        self.tool_group.buttonClicked.connect(self._tool_selected);self.search.textChanged.connect(self._populate_palette)
        self.palette_list.itemClicked.connect(self._select_item);self.used_list.itemClicked.connect(self._used_color_clicked)
        self.highlight.toggled.connect(self._highlight);self.before.toggled.connect(self._before);self.undo.clicked.connect(self._undo);self.redo.clicked.connect(self._redo)
        self.canvas.patternChanged.connect(self._pattern_changed);self.canvas.selectedColorChanged.connect(self.select_code);self.canvas.inspectorChanged.connect(self.inspector.setText)
        self.canvas.toolChanged.connect(self.select_tool)
        self.canvas.confettiRegionClicked.connect(self._select_confetti_id)
        self.canvas.selectionChanged.connect(self._selection_changed);self.canvas.moveSelectionRequested.connect(self._move_selection)
        self.confetti_escape=QShortcut(QKeySequence(Qt.Key.Key_Escape),self);self.confetti_escape.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut);self.confetti_escape.activated.connect(self._escape_confetti)
        self.select_all_shortcut=QShortcut(QKeySequence.StandardKey.SelectAll,self.canvas);self.select_all_shortcut.setContext(Qt.ShortcutContext.WidgetShortcut);self.select_all_shortcut.activated.connect(self.canvas.select_all)
        self.copy_shortcut=QShortcut(QKeySequence.StandardKey.Copy,self.canvas);self.copy_shortcut.setContext(Qt.ShortcutContext.WidgetShortcut);self.copy_shortcut.activated.connect(self._copy_selection)
        self.paste_shortcut=QShortcut(QKeySequence.StandardKey.Paste,self.canvas);self.paste_shortcut.setContext(Qt.ShortcutContext.WidgetShortcut);self.paste_shortcut.activated.connect(self._paste_selection)
        self.delete_shortcut=QShortcut(QKeySequence(Qt.Key.Key_Delete),self.canvas);self.delete_shortcut.setContext(Qt.ShortcutContext.WidgetShortcut);self.delete_shortcut.activated.connect(self._clear_selection_cells)

    def _build_global_replacement(self,side_layout):
        self.replacement_source_code=None;self.replacement_destination_code=None;self.replacement_group=QGroupBox("Replace Selected Used Color");panel=QVBoxLayout(self.replacement_group)
        source_row=QHBoxLayout();self.replacement_from_swatch=QLabel();self.replacement_from_swatch.setFixedSize(22,22);self.replacement_from=QLabel();self.replacement_from.setWordWrap(True);source_row.addWidget(self.replacement_from_swatch);source_row.addWidget(self.replacement_from,1);panel.addLayout(source_row)
        self.replacement_scope=QLabel();self.replacement_scope.setWordWrap(True);panel.addWidget(self.replacement_scope)
        panel.addWidget(QLabel("Suggested replacements"));self.replacement_suggestions=QListWidget();self.replacement_suggestions.setFixedHeight(112);panel.addWidget(self.replacement_suggestions)
        self.closest_owned=QLabel();self.closest_owned.setWordWrap(True);self.closest_owned.hide();panel.addWidget(self.closest_owned)
        self.replacement_search=QLineEdit();self.replacement_search.setPlaceholderText("Search replacement DMC code or color name...");panel.addWidget(self.replacement_search)
        self.replacement_owned_only=QCheckBox("Only Show Colors I Own");panel.addWidget(self.replacement_owned_only)
        self.replacement_candidates=QListWidget();self.replacement_candidates.setFixedHeight(142);panel.addWidget(self.replacement_candidates)
        self.replacement_destination=QLabel("Choose a destination color.");self.replacement_destination.setWordWrap(True);self.replacement_destination.setFixedHeight(self.replacement_destination.fontMetrics().lineSpacing()*3+4);self.replacement_destination.setAlignment(Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignTop);panel.addWidget(self.replacement_destination)
        self.replacement_warning=QLabel();self.replacement_warning.setWordWrap(True);self.replacement_warning.setStyleSheet("color: #d69a35;");self.replacement_warning.setFixedHeight(self.replacement_warning.fontMetrics().lineSpacing()*2+2);panel.addWidget(self.replacement_warning)
        self.replacement_preview=QCheckBox("Preview Replacement");self.replacement_preview.setChecked(True);self.replacement_preview.setToolTip("Preview every occurrence in the editor without changing the pattern or undo history.");panel.addWidget(self.replacement_preview)
        self.replacement_actions=QWidget();actions=QHBoxLayout(self.replacement_actions);actions.setContentsMargins(0,0,0,0);self.replacement_apply=QPushButton("Replace Drills");self.replacement_apply.setToolTip("Replaces every occurrence of the selected used DMC color in the current pattern.");self.replacement_cancel=QPushButton("Cancel");height=max(self.replacement_apply.sizeHint().height(),self.replacement_cancel.sizeHint().height());self.replacement_apply.setFixedHeight(height);self.replacement_cancel.setFixedHeight(height);self.replacement_apply.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed);self.replacement_cancel.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed);actions.addWidget(self.replacement_apply,1);actions.addWidget(self.replacement_cancel,1);self.replacement_actions.setFixedHeight(height);panel.addWidget(self.replacement_actions)
        self.replacement_group.hide();side_layout.addWidget(self.replacement_group)
        self.replacement_search.textChanged.connect(self._populate_replacement_candidates);self.replacement_owned_only.toggled.connect(self._replacement_filter_changed);self.replacement_candidates.itemClicked.connect(self._replacement_candidate_clicked);self.replacement_suggestions.itemClicked.connect(self._replacement_candidate_clicked);self.replacement_preview.toggled.connect(self._update_replacement_preview);self.replacement_apply.clicked.connect(self._apply_global_replacement);self.replacement_cancel.clicked.connect(self._cancel_global_replacement)

    def _build_source_overlay_controls(self,side_layout):
        self.reference_group=QGroupBox("Reference");box=QVBoxLayout(self.reference_group);self.show_source_overlay=QCheckBox("Show Source Overlay");self.show_source_overlay.setToolTip("Source image is not available for this project.");box.addWidget(self.show_source_overlay)
        self.source_opacity_row=QWidget();row=QHBoxLayout(self.source_opacity_row);row.setContentsMargins(0,0,0,0);row.addWidget(QLabel("Source Opacity"));self.source_opacity=QSlider(Qt.Orientation.Horizontal);self.source_opacity.setRange(0,100);self.source_opacity.setValue(40);self.source_opacity_value=QLabel("40%");row.addWidget(self.source_opacity,1);row.addWidget(self.source_opacity_value);box.addWidget(self.source_opacity_row);self.source_opacity_row.hide();side_layout.addWidget(self.reference_group)
        self.show_source_overlay.toggled.connect(self._toggle_source_overlay);self.source_opacity.valueChanged.connect(self._source_opacity_changed)

    def _toggle_source_overlay(self,enabled):
        active=bool(enabled and self.canvas.source_reference_available);self.canvas.show_source_overlay=active;self.source_opacity_row.setVisible(active);self.canvas.update();LOG.debug("Source overlay %s","enabled" if active else "disabled")

    def _source_opacity_changed(self,value):
        self.source_opacity_value.setText(f"{value}%");self.canvas.source_overlay_opacity=value/100;self.canvas.update()

    def source_overlay_state(self):return {"show_source_overlay":self.show_source_overlay.isChecked(),"source_overlay_opacity":self.source_opacity.value()}

    def _build_selection_controls(self,side_layout):
        self.selection_group=QGroupBox("Selection");box=QVBoxLayout(self.selection_group);self.selection_status=QLabel();self.selection_status.setWordWrap(True);box.addWidget(self.selection_status)
        first=QHBoxLayout();self.fill_selection=QPushButton("Fill");self.clear_selection_cells=QPushButton("Clear Cells");self.copy_selection=QPushButton("Copy");first.addWidget(self.fill_selection);first.addWidget(self.clear_selection_cells);first.addWidget(self.copy_selection);box.addLayout(first)
        second=QHBoxLayout();self.paste_selection=QPushButton("Paste");self.replace_selection=QPushButton("Replace Color...");self.clear_selection_outline=QPushButton("Deselect");second.addWidget(self.paste_selection);second.addWidget(self.replace_selection);second.addWidget(self.clear_selection_outline);box.addLayout(second)
        self.selection_group.hide();side_layout.addWidget(self.selection_group)
        self.fill_selection.clicked.connect(self._fill_selection);self.clear_selection_cells.clicked.connect(self._clear_selection_cells);self.copy_selection.clicked.connect(self._copy_selection);self.paste_selection.clicked.connect(self._paste_selection);self.replace_selection.clicked.connect(self._replace_in_selection);self.clear_selection_outline.clicked.connect(self.canvas.clear_selection)

    def _build_confetti_inspector(self,side_layout):
        group=QGroupBox();box=QVBoxLayout(group);self.inspect_confetti=QPushButton("Confetti Inspector");self.inspect_confetti.setCheckable(True);self.inspect_confetti.setStyleSheet("QPushButton { padding: 5px 10px; } QPushButton:checked { background-color: palette(highlight); color: palette(highlighted-text); font-weight: 600; }");box.addWidget(self.inspect_confetti)
        self.confetti_content=QWidget();content=QVBoxLayout(self.confetti_content);content.setContentsMargins(0,0,0,0);self.highlight_confetti=QCheckBox("Highlight Confetti");content.addWidget(self.highlight_confetti)
        filters=QHBoxLayout();self.confetti_filter=QComboBox();self.confetti_filter.addItems(("High only","High + Medium","All suspects"));self.confetti_sort=QComboBox();self.confetti_sort.addItems(("Highest confidence","Region size"));filters.addWidget(self.confetti_filter);filters.addWidget(self.confetti_sort);content.addLayout(filters)
        self.confetti_status=QLabel("Activate the inspector to analyze suspicious small regions.");self.confetti_status.setWordWrap(True);self.confetti_status.setAlignment(Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignTop);self.confetti_status.setFixedHeight(self.confetti_status.fontMetrics().lineSpacing()*7+4);content.addWidget(self.confetti_status)
        self.confetti_list=QListWidget();self.confetti_list.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed);self.confetti_list.setFixedHeight(128);content.addWidget(self.confetti_list)
        self.confetti_navigation=QWidget();navigation=QHBoxLayout(self.confetti_navigation);navigation.setContentsMargins(0,0,0,0);self.confetti_previous=QPushButton("Previous");self.confetti_next=QPushButton("Next");button_height=max(self.confetti_previous.sizeHint().height(),self.confetti_next.sizeHint().height());self.confetti_previous.setFixedHeight(button_height);self.confetti_next.setFixedHeight(button_height);self.confetti_previous.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed);self.confetti_next.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed);navigation.addWidget(self.confetti_previous,1);navigation.addWidget(self.confetti_next,1);self.confetti_navigation.setFixedHeight(button_height);content.addWidget(self.confetti_navigation)
        self.confetti_details_scroll=QScrollArea();self.confetti_details_scroll.setWidgetResizable(True);self.confetti_details_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff);self.confetti_details_scroll.setFixedHeight(142);self.confetti_details=QLabel("Select a suspect region to inspect it.");self.confetti_details.setWordWrap(True);self.confetti_details.setAlignment(Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignTop);self.confetti_details.setContentsMargins(6,6,6,6);self.confetti_details.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred);self.confetti_details_scroll.setWidget(self.confetti_details);content.addWidget(self.confetti_details_scroll);box.addWidget(self.confetti_content);self.confetti_content.hide();side_layout.addWidget(group)
        self.inspect_confetti.toggled.connect(self._set_confetti_mode);self.highlight_confetti.toggled.connect(self._toggle_confetti_overlay);self.confetti_filter.currentIndexChanged.connect(lambda *_:self._refresh_confetti_list());self.confetti_sort.currentIndexChanged.connect(lambda *_:self._refresh_confetti_list())
        self.confetti_list.currentItemChanged.connect(self._confetti_item_changed);self.confetti_previous.clicked.connect(lambda:self._navigate_confetti(-1));self.confetti_next.clicked.connect(lambda:self._navigate_confetti(1))

    def set_pattern(self,pattern,source_reference=None,overlay_state=None):
        self._cancel_global_replacement(log_event=False);self.inspect_confetti.setChecked(False);self.pattern=pattern;self.confetti_analysis=None;self._confetti_selected_id=None;self.undo_stack=UndoStack();self.undo_stack.add_listener(self._history_changed);self.canvas.set_pattern(pattern,self.undo_stack);self.canvas.set_source_reference(source_reference);self.canvas.allow_selection_move=pattern.supports_transparency;self.canvas.set_confetti_analysis(None);self.canvas.set_inspection_mode(False);self.highlight_confetti.setChecked(True);self.confetti_status.setText("Activate the inspector to analyze suspicious small regions.");self.confetti_list.clear();self.confetti_details.setText("Select a suspect region to inspect it.");self.tool_buttons["Eraser"].setEnabled(pattern.supports_transparency);self.select_tool("Pencil");self._populate_palette();self._refresh_used();self._selection_changed(None)
        state=overlay_state or {};opacity=max(0,min(100,int(state.get("source_overlay_opacity",40))));self.source_opacity.setValue(opacity);available=self.canvas.source_reference_available;self.show_source_overlay.setEnabled(available);self.show_source_overlay.setToolTip("Blend the adjusted cropped source over the logical pattern." if available else "Source image is not available for this project.");self.show_source_overlay.setChecked(available and bool(state.get("show_source_overlay",False)));self._toggle_source_overlay(self.show_source_overlay.isChecked())
        if pattern.usage:self.select_code(next(iter(pattern.usage)))

    def set_owned_codes(self,codes):
        self.owned_codes=set(codes);self._populate_palette()
        if self.replacement_group.isVisible():self._refresh_replacement_choices()

    def _tool_selected(self,button):
        if self.inspect_confetti.isChecked():self.inspect_confetti.setChecked(False)
        self.canvas.tool=button.text()
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
    def _used_color_clicked(self,item):
        code=item.data(Qt.ItemDataRole.UserRole);self.select_code(code);self._begin_global_replacement(code)
    def select_code(self,code):
        if not self.pattern or code not in self.pattern.palette.by_code:return
        self.canvas.selected_code=code;color=self.pattern.palette.by_code[code];self.selected.setText(f"Selected: DMC {code} - {color.name} - Used: {self.pattern.usage.get(code,0):,}")
        for widget in (self.used_list,self.palette_list):
            widget.blockSignals(True);match=next((row for row in range(widget.count()) if widget.item(row).data(Qt.ItemDataRole.UserRole)==code),-1);widget.setCurrentRow(match);widget.blockSignals(False)
        self.canvas.refresh()
    def _highlight(self,value):self.canvas.highlight=value;self.canvas.refresh()
    def _before(self,value):self.canvas.show_initial=value;self.canvas.refresh()
    def _pattern_changed(self):
        self._cancel_global_replacement(log_event=False)
        if self.confetti_analysis:
            self.confetti_analysis.stale=True;self.canvas.set_confetti_analysis(None);self.inspect_confetti.setChecked(False);self.confetti_status.setText("Pattern changed - activate the inspector to reanalyze confetti.")
        self._refresh_used();self.select_code(self.canvas.selected_code);self._selection_changed(self.canvas.selection);self._buttons();self.changed.emit()
    def _history_changed(self,stack):
        self.undo.setEnabled(stack.can_undo);self.redo.setEnabled(stack.can_redo)
        self.undo.setText(f"Undo {stack.undo_text}" if stack.undo_text else "Undo")
        self.redo.setText(f"Redo {stack.redo_text}" if stack.redo_text else "Redo")
    def _buttons(self):self._history_changed(self.undo_stack)
    def _undo(self):
        if self.pattern and self.undo_stack.undo(self.pattern):self.canvas.refresh();self._pattern_changed()
    def _redo(self):
        if self.pattern and self.undo_stack.redo(self.pattern):self.canvas.refresh();self._pattern_changed()
    def _replacement_distance(self,code):return delta_e(self.pattern.palette._labs[self.replacement_source_code],self.pattern.palette._labs[code])
    def _similarity_label(self,distance):return "Very close" if distance<8 else "Close" if distance<18 else "Moderate" if distance<30 else "Significant change"
    def _set_swatch(self,label,rgb):pix=QPixmap(22,22);pix.fill(QColor(*rgb));label.setPixmap(pix)
    def _begin_global_replacement(self,code):
        if not self.pattern or code not in self.pattern.usage:return
        self.canvas.set_replacement_preview();self.replacement_source_code=code;self.replacement_destination_code=None;color=self.pattern.palette.by_code[code];count=self.pattern.usage[code];percentage=count/max(1,self.pattern.total_drills)
        self._set_swatch(self.replacement_from_swatch,color.rgb);self.replacement_from.setText(f"From: DMC {code} - {color.name}");self.replacement_scope.setText(f"{count:,} drills ({percentage:.1%})\nReplaces every occurrence of this DMC color in the current pattern.");self.replacement_search.clear();self.replacement_owned_only.setChecked(False);self.replacement_destination.setText("Choose a destination color.");self.replacement_warning.clear();self.replacement_group.show();self._refresh_replacement_choices();self._update_replacement_controls()
        if self.replacement_suggestions.count():self._select_replacement_code(self.replacement_suggestions.item(0).data(Qt.ItemDataRole.UserRole))

    def _replacement_codes(self):
        if not self.pattern or not self.replacement_source_code:return []
        query=self.replacement_search.text().strip().lower();owned_only=self.replacement_owned_only.isChecked()
        return [color.code for color in self.pattern.palette.colors if color.code!=self.replacement_source_code and (not owned_only or color.code in self.owned_codes) and (not query or query in color.code.lower() or query in color.name.lower())]

    def _refresh_replacement_choices(self):
        if not self.replacement_source_code:return
        eligible=[color.code for color in self.pattern.palette.colors if color.code!=self.replacement_source_code and (not self.replacement_owned_only.isChecked() or color.code in self.owned_codes)];suggested=sorted(eligible,key=lambda code:(self._replacement_distance(code),code))[:8]
        self.replacement_suggestions.clear()
        for code in suggested:
            color=self.pattern.palette.by_code[code];distance=self._replacement_distance(code);item=QListWidgetItem(f"{'✓ ' if code in self.owned_codes else ''}DMC {code} - {color.name} - {self._similarity_label(distance)}");item.setData(Qt.ItemDataRole.UserRole,code);item.setIcon(self._icon(color.rgb));item.setToolTip(f"Source-to-destination Delta E: {distance:.1f}");self.replacement_suggestions.addItem(item)
        owned=[code for code in self.owned_codes if code in self.pattern.palette.by_code and code!=self.replacement_source_code]
        if owned:
            closest=min(owned,key=lambda code:(self._replacement_distance(code),code));color=self.pattern.palette.by_code[closest];self.closest_owned.setText(f"Closest owned alternative: DMC {closest} - {color.name} (Delta E {self._replacement_distance(closest):.1f})");self.closest_owned.show()
        else:self.closest_owned.hide()
        self._populate_replacement_candidates()

    def _populate_replacement_candidates(self,*_):
        current=self.replacement_destination_code;self.replacement_candidates.clear()
        for code in sorted(self._replacement_codes(),key=lambda item:(self._replacement_distance(item),item not in self.owned_codes,item)):
            color=self.pattern.palette.by_code[code];item=QListWidgetItem(f"{'✓ ' if code in self.owned_codes else ''}DMC {code} - {color.name}");item.setData(Qt.ItemDataRole.UserRole,code);item.setIcon(self._icon(color.rgb));item.setToolTip(f"Source-to-destination Delta E: {self._replacement_distance(code):.1f}");self.replacement_candidates.addItem(item)
            if code==current:self.replacement_candidates.setCurrentItem(item)

    def _replacement_filter_changed(self,*_):
        if self.replacement_destination_code and self.replacement_owned_only.isChecked() and self.replacement_destination_code not in self.owned_codes:self.replacement_destination_code=None;self.canvas.set_replacement_preview();self.replacement_destination.setText("Choose a destination color.");self.replacement_warning.clear()
        self._refresh_replacement_choices();self._update_replacement_controls()

    def _replacement_candidate_clicked(self,item):self._select_replacement_code(item.data(Qt.ItemDataRole.UserRole))
    def _select_replacement_code(self,code):
        if not self.replacement_source_code or code==self.replacement_source_code or code not in self.pattern.palette.by_code:return
        self.replacement_destination_code=code;color=self.pattern.palette.by_code[code];distance=self._replacement_distance(code);count=self.pattern.usage.get(self.replacement_source_code,0)
        self.replacement_destination.setText(f"To: DMC {code} - {color.name}\n{self.replacement_source_code} -> {code} | Delta E {distance:.1f}\n{count:,} drills will change")
        self.replacement_warning.setText("This replacement is substantially different from the current color." if distance>=30 else "");self._update_replacement_controls();LOG.info("Replacement preview selected: DMC %s -> DMC %s",self.replacement_source_code,code)

    def _update_replacement_controls(self):
        count=self.pattern.usage.get(self.replacement_source_code,0) if self.pattern and self.replacement_source_code else 0;valid=bool(count and self.replacement_destination_code and self.replacement_destination_code!=self.replacement_source_code);self.replacement_apply.setEnabled(valid);self.replacement_apply.setText(f"Replace {count:,} Drills" if count else "Replace Drills");self._update_replacement_preview()

    def _update_replacement_preview(self,*_):
        enabled=self.replacement_preview.isChecked() and self.replacement_group.isVisible() and self.replacement_destination_code and self.replacement_destination_code!=self.replacement_source_code;self.canvas.set_replacement_preview(self.replacement_source_code,self.replacement_destination_code) if enabled else self.canvas.set_replacement_preview()

    def _cancel_global_replacement(self,*_,log_event=True):
        active=self.replacement_group.isVisible();self.canvas.set_replacement_preview();self.replacement_group.hide();self.replacement_source_code=None;self.replacement_destination_code=None
        if active and log_event:LOG.info("Global color replacement canceled")

    def _apply_global_replacement(self):
        old=self.replacement_source_code;new=self.replacement_destination_code
        if not self.pattern or not old or not new or old==new:return
        count=self.pattern.usage.get(old,0);changes=self.pattern.replace_color(old,new)
        if not self.undo_stack.push(f"Replace All DMC {old}",changes):return
        self._cancel_global_replacement(log_event=False);LOG.info("Global color replacement applied: DMC %s -> DMC %s, %s cells",old,new,count);self.canvas.selected_code=new;self.canvas.refresh();self._pattern_changed();self.select_code(new)

    def _selection_changed(self,bounds):
        self.selection_group.setVisible(bounds is not None)
        if not bounds:return
        left,top,right,bottom=bounds;width=right-left;height=bottom-top;drills=sum(value is not None for row in self.pattern.region_cells(bounds) for value in row)
        self.selection_status.setText(f"Selection: {width} x {height} cells\n{width*height:,} cells selected | Drills: {drills:,}")
        can_clear=self.pattern.supports_transparency;self.clear_selection_cells.setEnabled(can_clear);self.clear_selection_cells.setToolTip("Set selected cells to transparent / no drill." if can_clear else "Clear and Move require a transparency-enabled pattern.")
        self.paste_selection.setEnabled(self._clipboard_compatible())

    def _clipboard_compatible(self):
        if not self.pattern_clipboard or not self.pattern:return False
        if any(code is not None and code not in self.pattern.palette.by_code for code in self.pattern_clipboard.cells):return False
        return self.pattern.supports_transparency or all(code is not None for code in self.pattern_clipboard.cells)

    def _commit_region(self,label,changes,log_message):
        if not self.undo_stack.push(label,changes):return False
        LOG.info("%s: %s cells",log_message,len(changes));self.canvas.refresh();self._pattern_changed();return True

    def _fill_selection(self):
        if self.canvas.selection and self.canvas.selected_code:self._commit_region("Fill Selection",self.pattern.fill_region(self.canvas.selection,self.canvas.selected_code),"Selection filled")

    def _clear_selection_cells(self):
        if not self.canvas.selection:return
        if not self.pattern.supports_transparency:QMessageBox.information(self,"Clear Selection","This pattern does not support transparent/no-drill cells. Clear Selection is available only for transparency-enabled patterns.");return
        self._commit_region("Clear Selection",self.pattern.fill_region(self.canvas.selection,None),"Selection cleared")

    def _copy_selection(self):
        if not self.canvas.selection:return
        self.pattern_clipboard=self.pattern.copy_region(self.canvas.selection);LOG.info("Selection copied: %sx%s",self.pattern_clipboard.width,self.pattern_clipboard.height);self._selection_changed(self.canvas.selection)

    def _paste_selection(self):
        clip=self.pattern_clipboard
        if not clip or not self._clipboard_compatible():return
        if self.canvas.selection:left,top=self.canvas.selection[:2]
        elif self.canvas.last_mouse_cell:left,top=self.canvas.last_mouse_cell
        else:
            center=self.canvas.view_center_cell();left=center[0]-clip.width//2;top=center[1]-clip.height//2
        left=max(0,min(self.pattern.width-clip.width,left));top=max(0,min(self.pattern.height-clip.height,top))
        if clip.width>self.pattern.width or clip.height>self.pattern.height:QMessageBox.information(self,"Paste Selection","The copied region is larger than this pattern.");return
        changes=self.pattern.paste_region(clip,left,top)
        if self._commit_region("Paste Selection",changes,"Paste committed"):self.canvas.set_selection((left,top,left+clip.width,top+clip.height))

    def _move_selection(self,bounds,destination):
        if not self.pattern.supports_transparency:return
        left,top=destination;width=bounds[2]-bounds[0];height=bounds[3]-bounds[1];changes=self.pattern.move_region(bounds,left,top)
        if self._commit_region("Move Selection",changes,f"Selection moved {width}x{height}"):self.canvas.set_selection((left,top,left+width,top+height))

    def _replace_in_selection(self):
        bounds=self.canvas.selection
        if not bounds:return
        counts={}
        for row in self.pattern.region_cells(bounds):
            for code in row:
                if code is not None:counts[code]=counts.get(code,0)+1
        if not counts:QMessageBox.information(self,"Replace Color in Selection","The selection contains no DMC colors to replace.");return
        dialog=QDialog(self);dialog.setWindowTitle("Replace Color in Selection");layout=QVBoxLayout(dialog);source=QComboBox();destination=QComboBox();affected=QLabel()
        for code in sorted(counts,key=lambda item:(-counts[item],item)):
            color=self.pattern.palette.by_code[code];source.addItem(f"DMC {code} - {color.name}",code)
        for color in self.pattern.palette.colors:destination.addItem(f"DMC {color.code} - {color.name}",color.code)
        if self.canvas.selected_code:
            index=destination.findData(self.canvas.selected_code)
            if index>=0:destination.setCurrentIndex(index)
        def update_count(*_):affected.setText(f"{counts.get(source.currentData(),0):,} cells in the current selection will change.")
        source.currentIndexChanged.connect(update_count);layout.addWidget(QLabel("Source color"));layout.addWidget(source);layout.addWidget(QLabel("Destination color"));layout.addWidget(destination);layout.addWidget(affected);update_count()
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel);buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);layout.addWidget(buttons)
        if dialog.exec()!=QDialog.DialogCode.Accepted:return
        old=source.currentData();new=destination.currentData()
        if old==new:return
        self._commit_region("Replace Color in Selection",self.pattern.replace_color_in_region(bounds,old,new),"Selection color replaced")

    def _confidence_filter(self):
        return ({"High"},{"High","Medium"},{"High","Medium","Low"})[self.confetti_filter.currentIndex()]

    def _escape_confetti(self):
        if self.replacement_group.isVisible():self._cancel_global_replacement()
        elif self.inspect_confetti.isChecked():self.inspect_confetti.setChecked(False)
        elif self.canvas.selection:self.canvas.clear_selection()

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
