"""Canonical Drillbit project-file identity, independent of archive schema version."""
from pathlib import Path
from .version import APP_NAME,PROJECT_DESCRIPTION,PROJECT_EXTENSION

APPLICATION_NAME=APP_NAME
PROJECT_FILE_TYPE_DESCRIPTION=PROJECT_DESCRIPTION
PRIMARY_PROJECT_EXTENSION=PROJECT_EXTENSION
LEGACY_PROJECT_EXTENSIONS=frozenset({".diamond"})
SUPPORTED_PROJECT_EXTENSIONS=frozenset({PRIMARY_PROJECT_EXTENSION,*LEGACY_PROJECT_EXTENSIONS})
PROJECT_OPEN_FILTER="All Drillbit Projects (*.drillbit *.diamond);;Drillbit Project (*.drillbit);;Legacy Drillbit Project (*.diamond)"
PROJECT_SAVE_FILTER="Drillbit Project (*.drillbit)"


def is_project_path(path):return Path(path).suffix.lower() in SUPPORTED_PROJECT_EXTENSIONS
def is_legacy_project_path(path):return Path(path).suffix.lower() in LEGACY_PROJECT_EXTENSIONS
def native_project_path(path):
    candidate=Path(path)
    return candidate if candidate.suffix.lower()==PRIMARY_PROJECT_EXTENSION else candidate.with_suffix(PRIMARY_PROJECT_EXTENSION)
