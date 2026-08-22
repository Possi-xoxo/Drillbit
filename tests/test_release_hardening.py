import json
import os
from pathlib import Path

import pytest
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
from PySide6.QtWidgets import QApplication

from app import __version__
from app.main_window import MainWindow
from app.palette_system import PaletteColor,ReferencePalette,load_dmc_palette,palette_path
from app.project_format import APPLICATION_NAME,PRIMARY_PROJECT_EXTENSION,PROJECT_FILE_TYPE_DESCRIPTION
from app.version import APP_NAME,APP_VERSION,PROJECT_DESCRIPTION,PROJECT_EXTENSION,about_text


def test_release_identity_has_one_authoritative_version():
    assert APP_NAME==APPLICATION_NAME=="Drillbit"
    assert APP_VERSION==__version__=="1.0.0"
    assert PROJECT_EXTENSION==PRIMARY_PROJECT_EXTENSION==".drillbit"
    assert PROJECT_DESCRIPTION==PROJECT_FILE_TYPE_DESCRIPTION=="Drillbit Project"
    text=about_text();assert "Drillbit" in text and "Version 1.0.0" in text and ".drillbit" in text


def test_built_in_dmc_palette_is_complete_and_valid():
    palette=load_dmc_palette()
    assert len(palette.colors)==489 and len(palette.by_code)==489
    assert palette_path().is_file()


@pytest.mark.parametrize("colors,match",[
    ([PaletteColor("310","Black",(0,0,0)),PaletteColor("310","Duplicate",(1,2,3))],"Duplicate DMC code"),
    ([PaletteColor("","Missing code",(0,0,0))],"invalid DMC code"),
    ([PaletteColor("310","",(0,0,0))],"invalid name"),
    ([PaletteColor("310","Black",(0,0,256))],"invalid RGB"),
])
def test_palette_validation_fails_clearly(colors,match):
    with pytest.raises(ValueError,match=match):ReferencePalette("Invalid",colors)


def test_packaging_spec_has_release_branding_and_no_machine_path():
    root=Path(__file__).resolve().parents[1]
    spec=(root/"DiamondArtConverter.spec").read_text(encoding="utf-8")
    assert 'Path(SPECPATH)/"app"/"version.py"' in spec and 'icon="Drillbit.ico"' in spec and "version=version_info" in spec
    assert "H:\\" not in spec and ".venv" not in spec and "python313" not in spec
    assert json.loads((root/"palettes"/"dmc.json").read_text(encoding="utf-8"))["name"]=="DMC Reference Palette"


def test_finished_preview_view_preferences_do_not_dirty_project():
    app=QApplication.instance() or QApplication([]);window=MainWindow();window.dirty=False
    window.finished_preview.show_grid.setChecked(True);window.finished_preview.background.setCurrentText("Black")
    app.processEvents();assert not window.dirty
    window.close()
