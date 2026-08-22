import io
import json
import zipfile
from pathlib import Path
from PIL import Image
from .pattern_model import PatternModel
from .project_format import SUPPORTED_PROJECT_EXTENSIONS,native_project_path
from .symbols import ensure_pattern_symbols

PROJECT_VERSION=2

def save_project(path,pattern,source=None,settings=None,editor_state=None):
    ensure_pattern_symbols(pattern)
    destination=native_project_path(path)
    payload={"format":"Diamond Art Converter Project","version":PROJECT_VERSION,"palette":pattern.palette.name,
             "width":pattern.width,"height":pattern.height,"cell_ids":pattern.cell_ids,"initial_ids":pattern.initial_ids,
             "metadata":pattern.metadata,"settings":settings or {},"editor_state":editor_state or {},"source_embedded":source is not None}
    with zipfile.ZipFile(destination,"w",zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("project.json",json.dumps(payload,separators=(",",":")))
        if source is not None:
            buffer=io.BytesIO();source.save(buffer,"PNG");archive.writestr("source.png",buffer.getvalue())
    return destination

def load_project(path,palette):
    path=Path(path)
    if path.suffix.lower() not in SUPPORTED_PROJECT_EXTENSIONS:raise ValueError("Unsupported project file extension. Open a .drillbit project or legacy .diamond project.")
    with zipfile.ZipFile(path,"r") as archive:
        payload=json.loads(archive.read("project.json"))
        if payload.get("format")!="Diamond Art Converter Project" or payload.get("version") not in (1,PROJECT_VERSION):
            raise ValueError("Unsupported project format or version.")
        pattern=PatternModel(payload["width"],payload["height"],payload["cell_ids"],palette,payload.get("metadata"),payload.get("initial_ids"))
        source=Image.open(io.BytesIO(archive.read("source.png"))).convert("RGBA") if payload.get("source_embedded") else None
    return pattern,source,payload.get("settings",{}),payload.get("editor_state",{})
