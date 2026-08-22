"""Persistent user-owned DMC color inventory."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

LOG=logging.getLogger(__name__)
INVENTORY_VERSION=1
INVENTORY_FILENAME="owned_colors.json"


def inventory_path(base_directory=None):
    if base_directory is not None:return Path(base_directory)/INVENTORY_FILENAME
    local=os.environ.get("LOCALAPPDATA")
    root=Path(local) if local else Path.home()/"AppData"/"Local"
    return root/"Drillbit"/INVENTORY_FILENAME


class OwnedColorInventory:
    def __init__(self,palette,path=None):
        self.palette=palette;self.path=Path(path) if path is not None else inventory_path();self.owned=set();self.load_error=None;self.load()

    @property
    def valid_codes(self):return set(self.palette.by_code)

    def load(self):
        self.owned=set();self.load_error=None
        if not self.path.exists():LOG.info("Loaded owned-color inventory: 0 colors");return self.owned
        try:
            payload=json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload,dict) or payload.get("version")!=INVENTORY_VERSION or not isinstance(payload.get("owned_dmc_codes"),list):
                raise ValueError("Unsupported owned-color inventory format.")
            raw={str(code) for code in payload["owned_dmc_codes"]};invalid=raw-self.valid_codes
            if invalid:LOG.warning("Ignored %s invalid DMC code(s) in owned-color inventory",len(invalid))
            self.owned=raw&self.valid_codes;LOG.info("Loaded owned-color inventory: %s colors",len(self.owned))
        except (OSError,UnicodeError,json.JSONDecodeError,ValueError,TypeError) as exc:
            self.load_error=str(exc);self.owned=set();LOG.exception("Owned inventory file could not be parsed; using an empty inventory")
        return set(self.owned)

    def save(self):
        self.path.parent.mkdir(parents=True,exist_ok=True);payload={"version":INVENTORY_VERSION,"owned_dmc_codes":sorted(self.owned,key=_code_key)}
        temporary=self.path.with_name(f".{self.path.name}.tmp")
        try:
            with temporary.open("w",encoding="utf-8",newline="\n") as stream:
                json.dump(payload,stream,indent=2);stream.write("\n");stream.flush();os.fsync(stream.fileno())
            os.replace(temporary,self.path)
        finally:
            try:temporary.unlink(missing_ok=True)
            except OSError:pass
        LOG.info("Owned-color inventory updated: %s colors",len(self.owned));return self.path

    def is_owned(self,code):return code in self.owned

    def set_owned(self,code,owned):
        if code not in self.valid_codes:raise ValueError(f"Unknown DMC code: {code}")
        before=len(self.owned)
        if owned:self.owned.add(code)
        else:self.owned.discard(code)
        if len(self.owned)!=before:self.save();return True
        return False

    def replace_owned(self,codes):
        updated={str(code) for code in codes}&self.valid_codes
        if updated==self.owned:return False
        self.owned=updated;self.save();return True

    def clear(self):return self.replace_owned(())


def _code_key(code):
    text=str(code);return (0,int(text)) if text.isdigit() else (1,text)
