from dataclasses import dataclass
from enum import Enum

class FitMode(str, Enum):
    FIT = "Fit Entire Image"
    FILL = "Fill / Crop to Pattern"

class DitherMode(str, Enum):
    OFF = "Off"
    FLOYD_STEINBERG = "Floyd-Steinberg"

@dataclass(frozen=True)
class ConversionSettings:
    width: int = 100
    height: int = 100
    max_colors: int = 16
    fit_mode: FitMode = FitMode.FILL
    dither: DitherMode = DitherMode.OFF
    brightness: int = 0
    contrast: int = 0
    saturation: int = 0
    crop_box: tuple[float, float, float, float] | None = None

    def validate(self) -> None:
        if not 10 <= self.width <= 1000 or not 10 <= self.height <= 1000:
            raise ValueError("Pattern dimensions must be between 10 and 1000 diamonds.")
        if not 2 <= self.max_colors <= 256:
            raise ValueError("Maximum colors must be between 2 and 256.")
        for name in ("brightness", "contrast", "saturation"):
            if not -100 <= getattr(self, name) <= 100:
                raise ValueError(f"{name.title()} must be between -100 and 100.")

    @property
    def total_cells(self) -> int:
        return self.width * self.height

@dataclass(frozen=True)
class PaletteEntry:
    rgb: tuple[int, int, int]
    count: int

    @property
    def hex(self) -> str:
        return "#{:02X}{:02X}{:02X}".format(*self.rgb)
