import json
import math
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class PaletteColor:
    code: str
    name: str
    rgb: tuple[int, int, int]

    @property
    def hex(self): return "#{:02X}{:02X}{:02X}".format(*self.rgb)

class ReferencePalette:
    def __init__(self, name, colors, source="", accuracy_note=""):
        self.name=name; self.colors=tuple(colors); self.source=source; self.accuracy_note=accuracy_note
        self.by_code={color.code:color for color in self.colors}
        self._labs={color.code:rgb_to_lab(color.rgb) for color in self.colors}

    @classmethod
    def load(cls, path):
        data=json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(data["name"],[PaletteColor(item["code"],item["name"],tuple(item["rgb"])) for item in data["colors"]],data.get("source",""),data.get("accuracy_note",""))

    def nearest(self, rgb):
        lab=rgb_to_lab(rgb)
        code=min(self._labs,key=lambda key: sum((a-b)**2 for a,b in zip(lab,self._labs[key])))
        return self.by_code[code]

    def subset(self,codes,name=None):
        allowed=set(codes);return ReferencePalette(name or self.name,[color for color in self.colors if color.code in allowed],self.source,self.accuracy_note)

def palette_path(filename="dmc.json"):
    import sys
    base=Path(getattr(sys,"_MEIPASS",Path(__file__).resolve().parent.parent))
    return base/"palettes"/filename

def load_dmc_palette(): return ReferencePalette.load(palette_path())

def rgb_to_lab(rgb):
    values=[]
    for value in rgb:
        channel=value/255.0
        values.append(channel/12.92 if channel<=0.04045 else ((channel+0.055)/1.055)**2.4)
    r,g,b=values
    x=(r*.4124564+g*.3575761+b*.1804375)/.95047
    y=(r*.2126729+g*.7151522+b*.0721750)
    z=(r*.0193339+g*.1191920+b*.9503041)/1.08883
    def f(value): return value**(1/3) if value>.008856 else 7.787*value+16/116
    fx,fy,fz=f(x),f(y),f(z)
    return (116*fy-16,500*(fx-fy),200*(fy-fz))
