from .image_processor import convert_image
from .pattern_model import PatternModel

def convert_to_pattern(source,settings,palette):
    intermediate,_=convert_image(source,settings)
    mapping={rgb:palette.nearest(rgb).code for _count,rgb in intermediate.getcolors(maxcolors=intermediate.width*intermediate.height)}
    ids=[mapping[rgb] for rgb in intermediate.get_flattened_data()]
    return PatternModel(intermediate.width,intermediate.height,ids,palette,metadata={"max_colors":settings.max_colors})
