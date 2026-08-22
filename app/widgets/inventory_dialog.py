"""Searchable model/view editor for the global owned DMC inventory."""
from PySide6.QtCore import QSortFilterProxyModel,Qt
from PySide6.QtGui import QColor,QIcon,QPixmap,QStandardItem,QStandardItemModel
from PySide6.QtWidgets import (QCheckBox,QDialog,QDialogButtonBox,QHBoxLayout,QLabel,QLineEdit,QMessageBox,
    QPushButton,QTableView,QVBoxLayout)


class InventoryFilterModel(QSortFilterProxyModel):
    def __init__(self,parent=None):super().__init__(parent);self.query="";self.owned_only=False
    def set_query(self,text):self.query=text.strip().lower();self.invalidateFilter()
    def set_owned_only(self,value):self.owned_only=value;self.invalidateFilter()
    def filterAcceptsRow(self,row,parent):
        model=self.sourceModel();owned=model.item(row,0).checkState()==Qt.CheckState.Checked
        if self.owned_only and not owned:return False
        code=model.item(row,2).text().lower();name=model.item(row,3).text().lower()
        return not self.query or self.query in code or self.query in name


class InventoryDialog(QDialog):
    def __init__(self,inventory,parent=None):
        super().__init__(parent);self.inventory=inventory;self._bulk=False;self.setWindowTitle("Manage Colors I Own");self.resize(680,720)
        layout=QVBoxLayout(self);filters=QHBoxLayout();self.search=QLineEdit();self.search.setPlaceholderText("Search DMC code or color name...")
        self.owned_only=QCheckBox("Show Owned Only");filters.addWidget(self.search,1);filters.addWidget(self.owned_only);layout.addLayout(filters)
        self.model=QStandardItemModel(0,4,self);self.model.setHorizontalHeaderLabels(("Owned","Color","DMC","Name"));self._populate()
        self.proxy=InventoryFilterModel(self);self.proxy.setSourceModel(self.model);self.table=QTableView();self.table.setModel(self.proxy);self.table.setSortingEnabled(False)
        self.table.verticalHeader().setVisible(False);self.table.setAlternatingRowColors(True);self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.setColumnWidth(0,62);self.table.setColumnWidth(1,52);self.table.setColumnWidth(2,82);self.table.horizontalHeader().setStretchLastSection(True);layout.addWidget(self.table,1)
        actions=QHBoxLayout();self.count=QLabel();self.select_all=QPushButton("Select All");self.clear_all=QPushButton("Clear All")
        actions.addWidget(self.count);actions.addStretch();actions.addWidget(self.select_all);actions.addWidget(self.clear_all);layout.addLayout(actions)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Close);buttons.rejected.connect(self.reject);layout.addWidget(buttons)
        self.search.textChanged.connect(self.proxy.set_query);self.owned_only.toggled.connect(self.proxy.set_owned_only);self.model.itemChanged.connect(self._item_changed)
        self.select_all.clicked.connect(self._select_everything);self.clear_all.clicked.connect(self._clear_everything);self._update_count()

    def _populate(self):
        colors=sorted(self.inventory.palette.colors,key=lambda color:(0,int(color.code)) if color.code.isdigit() else (1,color.code))
        for color in colors:
            owned=QStandardItem();owned.setCheckable(True);owned.setEditable(False);owned.setCheckState(Qt.CheckState.Checked if color.code in self.inventory.owned else Qt.CheckState.Unchecked);owned.setData(color.code,Qt.ItemDataRole.UserRole)
            pixmap=QPixmap(24,18);pixmap.fill(QColor(*color.rgb));swatch=QStandardItem();swatch.setIcon(QIcon(pixmap));swatch.setEditable(False)
            code=QStandardItem(color.code);code.setEditable(False);name=QStandardItem(color.name);name.setEditable(False);self.model.appendRow((owned,swatch,code,name))

    def _item_changed(self,item):
        if self._bulk or item.column()!=0:return
        self.inventory.set_owned(item.data(Qt.ItemDataRole.UserRole),item.checkState()==Qt.CheckState.Checked);self._update_count();self.proxy.invalidateFilter()

    def _set_all(self,checked):
        self._bulk=True
        try:
            for row in range(self.model.rowCount()):self.model.item(row,0).setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        finally:self._bulk=False
        self.inventory.replace_owned(self.inventory.valid_codes if checked else ());self._update_count();self.proxy.invalidateFilter()

    def _select_everything(self):self._set_all(True)
    def _clear_everything(self):
        if not self.inventory.owned:return
        if QMessageBox.question(self,"Clear Owned Colors","Remove every color from Colors I Own?")==QMessageBox.StandardButton.Yes:self._set_all(False)
    def _update_count(self):self.count.setText(f"Owned Colors: {len(self.inventory.owned)}    Total DMC Colors: {len(self.inventory.palette.colors)}")
