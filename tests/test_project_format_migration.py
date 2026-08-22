import os
import shutil
import zipfile

os.environ.setdefault("QT_QPA_PLATFORM","offscreen")

import pytest
from PIL import Image
from PySide6.QtWidgets import QFileDialog, QMessageBox

from app.main_window import MainWindow
from app.palette_system import PaletteColor, ReferencePalette
from app.pattern_model import PatternModel
from app.project_format import (PRIMARY_PROJECT_EXTENSION, PROJECT_OPEN_FILTER,
    PROJECT_SAVE_FILTER, is_legacy_project_path, is_project_path)
from app.project_io import load_project, save_project


def palette():
    return ReferencePalette("Test",[
        PaletteColor("310","Black",(0,0,0)),
        PaletteColor("B5200","Snow White",(255,255,255)),
    ])


def pattern():
    cells=(["310","310",None,"B5200","310","B5200","310","B5200","310","B5200"]*10)
    initial=list(cells);initial[1]="B5200"
    return PatternModel(10,10,cells,palette(),
        metadata={"preserve_transparency":True,"note":"edited"},
        initial_ids=initial)


def test_project_identity_and_dialog_filters_cover_native_and_legacy():
    assert PRIMARY_PROJECT_EXTENSION==".drillbit"
    assert is_project_path("art.drillbit") and is_project_path("old.DIAMOND")
    assert is_legacy_project_path("old.diamond") and not is_legacy_project_path("art.drillbit")
    assert "*.drillbit *.diamond" in PROJECT_OPEN_FILTER
    assert PROJECT_SAVE_FILTER=="Drillbit Project (*.drillbit)"


@pytest.mark.parametrize("requested",["new-project","new-project.diamond","new-project.anything"])
def test_save_always_uses_native_extension(tmp_path,requested):
    result=save_project(tmp_path/requested,pattern())
    assert result.suffix==".drillbit" and result.exists()
    assert not (tmp_path/"new-project.diamond").exists()


def test_native_and_legacy_round_trips_preserve_project_data(tmp_path):
    original=pattern();source=Image.new("RGBA",(8,6),(20,40,60,128))
    settings={"width":10,"height":10,"max_colors":16,"crop_box":[0,0,1,1],"brightness":2,"contrast":-3,"saturation":4,
              "drill_mm":2.5,"drill_shape":"Round","canvas_background":"Black","finished_preview_grid":True,
              "preserve_transparency":True,"only_use_owned_colors":True}
    editor={"selected_code":"310","show_source_overlay":True,"source_overlay_opacity":55}
    native=save_project(tmp_path/"sample",original,source,settings,editor)
    for path in (native,tmp_path/"sample.diamond"):
        if path!=native:shutil.copyfile(native,path)
        loaded,loaded_source,loaded_settings,loaded_editor=load_project(path,palette())
        assert loaded.cell_ids==original.cell_ids and loaded.initial_ids==original.initial_ids
        assert loaded.metadata==original.metadata and loaded_source.getpixel((0,0))==(20,40,60,128)
        assert loaded_settings==settings and loaded_editor==editor


def test_unknown_project_extension_is_rejected(tmp_path):
    bad=tmp_path/"sample.zip";bad.touch()
    with pytest.raises(ValueError,match="Unsupported project file extension"):
        load_project(bad,palette())


def test_unicode_and_space_project_path_round_trip(tmp_path):
    destination=tmp_path/"Mom's Räven (final)"
    saved=save_project(destination,pattern())
    loaded,*_=load_project(saved,palette())
    assert saved.name=="Mom's Räven (final).drillbit" and loaded.cell_ids==pattern().cell_ids


@pytest.mark.parametrize("contents",[b"",b"not a zip archive"])
def test_invalid_project_container_fails_cleanly_at_loader_boundary(tmp_path,contents):
    path=tmp_path/"broken.drillbit";path.write_bytes(contents)
    with pytest.raises(zipfile.BadZipFile):load_project(path,palette())


def test_corrupt_project_json_fails_cleanly_at_loader_boundary(tmp_path):
    path=tmp_path/"broken-json.drillbit"
    with zipfile.ZipFile(path,"w") as archive:archive.writestr("project.json","{not json")
    with pytest.raises(ValueError):load_project(path,palette())


@pytest.mark.parametrize("name",["native.drillbit","legacy.diamond"])
def test_drag_drop_accepts_and_routes_both_project_extensions(name):
    class Url:
        def toLocalFile(self):return name
    class Mime:
        def hasUrls(self):return True
        def urls(self):return [Url()]
    class Event:
        accepted=False
        def mimeData(self):return Mime()
        def acceptProposedAction(self):self.accepted=True
    event=Event();MainWindow.dragEnterEvent(object(),event);assert event.accepted
    class Window:
        def load_project_path(self,path):self.opened=path
    window=Window();MainWindow.load_path(window,name);assert window.opened==name


def test_normal_save_of_legacy_project_migrates_without_touching_original(tmp_path,monkeypatch):
    native=save_project(tmp_path/"legacy-source",pattern(),Image.new("RGBA",(2,2),(1,2,3,4)))
    legacy=tmp_path/"legacy-source.diamond";shutil.copyfile(native,legacy);before=legacy.read_bytes()
    class StatusBar:
        def showMessage(self,message):self.message=message
    class Canvas:selected_code="310"
    class Editor:
        canvas=Canvas()
        def source_overlay_state(self):return {"show_source_overlay":True}
    migrated_pattern=pattern()
    class Window:
        pattern=migrated_pattern;source=Image.new("RGBA",(2,2),(1,2,3,4));project_path=legacy;source_path=None;editor=Editor();dirty=True
        def _project_settings(self):return {"drill_mm":2.5}
        def _update_title(self):pass
        def statusBar(self):return status
    status=StatusBar();window=Window()
    destination=tmp_path/"migrated"
    monkeypatch.setattr(QMessageBox,"question",lambda *args,**kwargs:QMessageBox.StandardButton.Save)
    monkeypatch.setattr(QFileDialog,"getSaveFileName",lambda *args,**kwargs:(str(destination),PROJECT_SAVE_FILTER))
    assert MainWindow.save_current_project(window)
    assert window.project_path==destination.with_suffix(".drillbit") and window.project_path.exists()
    assert legacy.read_bytes()==before and status.message=="Saved migrated.drillbit"
