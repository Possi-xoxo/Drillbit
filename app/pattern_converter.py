from .image_processor import prepare_logical_image
from .palette_optimizer import optimize_palette
from .pattern_model import PatternModel

def convert_to_pattern(source,settings,palette):
    logical=prepare_logical_image(source,settings)
    mask=None
    if settings.preserve_transparency:
        mask=logical.getchannel("A").point(lambda value:255 if value>=settings.alpha_threshold else 0)
    ids,diagnostics=optimize_palette(logical.convert("RGB"),settings.max_colors,palette,settings.dither,opaque_mask=mask)
    metadata={"max_colors":settings.max_colors,"preserve_transparency":settings.preserve_transparency,
              "alpha_threshold":settings.alpha_threshold,**diagnostics}
    return PatternModel(logical.width,logical.height,ids,palette,metadata=metadata)
