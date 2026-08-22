import json
import logging
import os
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")

import pytest
from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from app.inventory import INVENTORY_VERSION,OwnedColorInventory,inventory_path
from app.models import ConversionSettings
from app.palette_system import load_dmc_palette
from app.pattern_converter import convert_to_pattern
from app.widgets.inventory_dialog import InventoryDialog


@pytest.fixture(scope="module")
def palette():return load_dmc_palette()


def test_missing_inventory_loads_empty_without_creating_file(tmp_path,palette):
    path=tmp_path/"owned_colors.json";inventory=OwnedColorInventory(palette,path)
    assert inventory.owned==set() and not path.exists() and inventory.load_error is None


def test_save_reload_and_atomic_json(tmp_path,palette):
    path=tmp_path/"owned_colors.json";inventory=OwnedColorInventory(palette,path);expected={"310","550","823"};inventory.replace_owned(expected)
    payload=json.loads(path.read_text(encoding="utf-8"));reloaded=OwnedColorInventory(palette,path)
    assert payload=={"version":INVENTORY_VERSION,"owned_dmc_codes":["310","550","823"]}
    assert reloaded.owned==expected and not path.with_name(".owned_colors.json.tmp").exists()


def test_invalid_codes_are_ignored_and_valid_codes_remain(tmp_path,palette,caplog):
    path=tmp_path/"owned_colors.json";path.write_text(json.dumps({"version":1,"owned_dmc_codes":["310","NOT-DMC"]}),encoding="utf-8")
    with caplog.at_level(logging.WARNING):inventory=OwnedColorInventory(palette,path)
    assert inventory.owned=={"310"} and "invalid DMC" in caplog.text


def test_corrupt_json_falls_back_without_overwriting_source(tmp_path,palette,caplog):
    path=tmp_path/"owned_colors.json";corrupt="{ definitely broken";path.write_text(corrupt,encoding="utf-8")
    with caplog.at_level(logging.ERROR):inventory=OwnedColorInventory(palette,path)
    assert inventory.owned==set() and inventory.load_error and path.read_text(encoding="utf-8")==corrupt
    assert "could not be parsed" in caplog.text


def test_default_inventory_path_is_outside_install_tree(monkeypatch,tmp_path):
    monkeypatch.setenv("LOCALAPPDATA",str(tmp_path));assert inventory_path()==tmp_path/"Drillbit"/"owned_colors.json"


def striped_source(palette,codes):
    image=Image.new("RGB",(30,10));pixels=image.load()
    for y in range(10):
        for x in range(30):pixels[x,y]=palette.by_code[codes[x//10]].rgb
    return image


def test_owned_only_conversion_never_uses_unowned_codes(palette):
    owned={"310","550","823"};settings=ConversionSettings(width=30,height=10,max_colors=32,only_use_owned_colors=True)
    pattern=convert_to_pattern(striped_source(palette,["310","666","B5200"]),settings,palette,owned)
    assert set(pattern.cell_ids)<=owned and len(pattern.usage)<=3
    assert pattern.metadata["owned_colors_available"]==3 and pattern.metadata["effective_palette_limit"]==3
    assert len(pattern.palette.colors)==len(palette.colors)  # Manual editor remains unrestricted.


def test_restriction_disabled_ignores_owned_subset(palette):
    source=striped_source(palette,["310","666","B5200"]);settings=ConversionSettings(width=30,height=10,max_colors=3)
    pattern=convert_to_pattern(source,settings,palette,{"310"})
    assert set(pattern.usage)<=set(palette.by_code) and set(pattern.usage)!={"310"} and len(pattern.usage)==3


def test_empty_owned_inventory_is_blocked_cleanly(palette):
    settings=ConversionSettings(width=10,height=10,max_colors=8,only_use_owned_colors=True)
    with pytest.raises(ValueError,match="No owned DMC colors"):convert_to_pattern(Image.new("RGB",(10,10)),settings,palette,set())


def test_inventory_change_does_not_modify_existing_pattern(tmp_path,palette):
    settings=ConversionSettings(width=30,height=10,max_colors=3);pattern=convert_to_pattern(striped_source(palette,["310","666","B5200"]),settings,palette)
    before=list(pattern.cell_ids);inventory=OwnedColorInventory(palette,tmp_path/"owned.json");inventory.replace_owned({"310"})
    assert pattern.cell_ids==before and "666" in pattern.usage


def test_inventory_dialog_search_owned_filter_and_toggle_persistence(tmp_path,palette):
    app=QApplication.instance() or QApplication([]);inventory=OwnedColorInventory(palette,tmp_path/"owned.json");inventory.replace_owned({"310"})
    dialog=InventoryDialog(inventory);dialog.show();app.processEvents();dialog.search.setText("black");app.processEvents()
    assert dialog.proxy.rowCount()>=1
    dialog.search.setText("310");app.processEvents();assert dialog.proxy.rowCount()==1
    dialog.search.clear();dialog.owned_only.setChecked(True);app.processEvents();assert dialog.proxy.rowCount()==1
    source_index=dialog.proxy.mapToSource(dialog.proxy.index(0,0));dialog.model.item(source_index.row(),0).setCheckState(Qt.CheckState.Unchecked);app.processEvents()
    assert inventory.owned==set() and OwnedColorInventory(palette,inventory.path).owned==set();dialog.close()
