from .image_processor import prepare_logical_image
from .palette_fidelity import optimize_palette
from .pattern_model import PatternModel
from .logging_manager import log_timing
import logging

LOG=logging.getLogger(__name__)

def convert_to_pattern(source,settings,palette,eligible_codes=None):
    LOG.info("Conversion input source=%sx%s mode=%s logical=%sx%s cells=%s max_colors=%s dither=%s transparency=%s brightness=%s contrast=%s saturation=%s",
             source.width,source.height,source.mode,settings.width,settings.height,settings.width*settings.height,settings.max_colors,settings.dither.value,
             settings.preserve_transparency,settings.brightness,settings.contrast,settings.saturation)
    with log_timing("logical resize",LOG):logical=prepare_logical_image(source,settings)
    mask=None
    if settings.preserve_transparency:
        mask=logical.getchannel("A").point(lambda value:255 if value>=settings.alpha_threshold else 0)
    optimization_palette=palette;effective_max=settings.max_colors
    if settings.only_use_owned_colors:
        eligible=set(eligible_codes or ())&set(palette.by_code)
        if not eligible:raise ValueError("No owned DMC colors are selected.")
        optimization_palette=palette.subset(eligible,f"{palette.name} - Owned Colors");effective_max=min(settings.max_colors,len(optimization_palette.colors))
        LOG.info("Conversion restricted to %s owned DMC colors",len(optimization_palette.colors))
    with log_timing("palette optimization",LOG):ids,diagnostics=optimize_palette(logical.convert("RGB"),effective_max,optimization_palette,settings.dither,opaque_mask=mask)
    diagnostics["requested_colors"]=settings.max_colors
    metadata={"max_colors":settings.max_colors,"preserve_transparency":settings.preserve_transparency,
              "only_use_owned_colors":settings.only_use_owned_colors,"owned_colors_available":len(optimization_palette.colors) if settings.only_use_owned_colors else None,
              "effective_palette_limit":effective_max,
              "alpha_threshold":settings.alpha_threshold,**diagnostics}
    pattern=PatternModel(logical.width,logical.height,ids,palette,metadata=metadata)
    LOG.info("Conversion completed colors_used=%s drills=%s empty_cells=%s mean_delta_e=%.3f p90_delta_e=%.3f",len(pattern.usage),pattern.total_drills,pattern.empty_cells,diagnostics["mean_delta_e"],diagnostics["p90_delta_e"])
    return pattern
