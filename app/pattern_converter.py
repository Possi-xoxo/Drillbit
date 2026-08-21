from .image_processor import prepare_logical_image
from .palette_fidelity import optimize_palette
from .pattern_model import PatternModel
from .logging_manager import log_timing
import logging

LOG=logging.getLogger(__name__)

def convert_to_pattern(source,settings,palette):
    LOG.info("Conversion input source=%sx%s mode=%s logical=%sx%s cells=%s max_colors=%s dither=%s transparency=%s brightness=%s contrast=%s saturation=%s",
             source.width,source.height,source.mode,settings.width,settings.height,settings.width*settings.height,settings.max_colors,settings.dither.value,
             settings.preserve_transparency,settings.brightness,settings.contrast,settings.saturation)
    with log_timing("logical resize",LOG):logical=prepare_logical_image(source,settings)
    mask=None
    if settings.preserve_transparency:
        mask=logical.getchannel("A").point(lambda value:255 if value>=settings.alpha_threshold else 0)
    with log_timing("palette optimization",LOG):ids,diagnostics=optimize_palette(logical.convert("RGB"),settings.max_colors,palette,settings.dither,opaque_mask=mask)
    metadata={"max_colors":settings.max_colors,"preserve_transparency":settings.preserve_transparency,
              "alpha_threshold":settings.alpha_threshold,**diagnostics}
    pattern=PatternModel(logical.width,logical.height,ids,palette,metadata=metadata)
    LOG.info("Conversion completed colors_used=%s drills=%s empty_cells=%s mean_delta_e=%.3f p90_delta_e=%.3f",len(pattern.usage),pattern.total_drills,pattern.empty_cells,diagnostics["mean_delta_e"],diagnostics["p90_delta_e"])
    return pattern
